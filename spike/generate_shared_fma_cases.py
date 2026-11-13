#!/usr/bin/env python3
"""Independent integer oracle for Iris hart2's shared scalar-FPU execution."""
from pathlib import Path
import hashlib,json,random
from generate_native_fp8_cases import ieee
from generate_ieee_fma_cases import FORMATS,NAMES,ORDINARY,edges,number
HERE=Path(__file__).resolve().parent

def exact(a,b,c,kind,rm,cmd):
    sa,ma,ea,ta,qa=a;sb,mb,eb,tb,qb=b;sc,mc,ec,tc,qc=c
    product_sign=sa^sb^bool(cmd&2);addend_sign=sc^bool(cmd&1)
    invalid=qa or qb or qc
    invalid|=ta=='inf' and tb is None and not mb or tb=='inf' and ta is None and not ma
    invalid|=ta!='nan' and tb!='nan' and (ta=='inf' or tb=='inf') and tc=='inf' and product_sign!=addend_sign
    special='nan' if 'nan' in (ta,tb,tc) else 'inf' if 'inf' in (ta,tb,tc) else None
    integer=power=zero_sign=0
    if special is None and not invalid:
        power=min(ea+eb,ec);product=ma*mb
        integer=((-1 if product_sign else 1)*product<<(ea+eb-power))+((-1 if addend_sign else 1)*mc<<(ec-power))
        zero_sign=product_sign if not product and not mc and product_sign==addend_sign else rm==2
    return ieee(integer,power,zero_sign,*FORMATS[kind],rm,special,product_sign if ta=='inf' or tb=='inf' else addend_sign,invalid)

def operation(code,kind,a,b,c,rm):
    name=NAMES[code];wide=code>=len(ORDINARY);out=(3 if kind==2 else 2) if wide else kind
    atype=out if '.w' in name else kind
    # RecFNToRecFN quiets sNaNs when widening; its NV output is unconnected.
    aa=number(a,atype,FORMATS[out][0]);bb=number(b,kind,FORMATS[out][0]);cc=number(c,out,FORMATS[out][0])
    one=(0,1,0,None,False);op=name.split('.')[0]
    if op in ['vfadd','vfwadd']:return exact(aa,one,bb,out,rm,0)
    if op in ['vfsub','vfwsub']:return exact(aa,one,bb,out,rm,1)
    if op=='vfrsub':return exact(aa,one,bb,out,rm,2)
    if op in ['vfmul','vfwmul']:return exact(aa,bb,(aa[0]^bb[0],0,0,None,False),out,rm,0)
    cmd=3 if op in ['vfnmacc','vfwnmacc','vfnmadd'] else 1 if op in ['vfmsac','vfwmsac','vfmsub'] else 2 if op in ['vfnmsac','vfwnmsac','vfnmsub'] else 0
    if op in ['vfmadd','vfnmadd','vfmsub','vfnmsub']:aa,cc=cc,aa
    return exact(aa,bb,cc,out,rm,cmd)

def reduction(kind,rm,wide,values,mask,seed):
    out=(3 if kind==2 else 2) if wide else kind;acc=seed;flags=0
    def add(a,b,narrow):
        return exact(number(a,out,FORMATS[out][0]),(0,1,0,None,False),
                     number(b,kind if narrow else out,FORMATS[out][0]),out,rm,0)
    for i,value in enumerate(values):
        result,exception=add(acc,value,True);flags|=exception
        if mask[i//8]&(1<<(i%8)):acc=result
    acc,exception=add(acc,0,False);flags|=exception
    return acc,flags

def main():
    rng=random.Random(0x53465055);rows=[];reductions=[]
    for code,name in enumerate(NAMES):
        for kind in ([0,2] if code>=23 else [0,2,3]):
            out=(3 if kind==2 else 2) if code>=23 else kind;atype=out if '.w' in name else kind
            for rm in range(5):
                for case in range(40):
                    a=edges(atype)[case%15] if case<30 else rng.getrandbits(sum(FORMATS[atype])+1)
                    b=edges(kind)[(case*7+4)%15] if case<30 else rng.getrandbits(sum(FORMATS[kind])+1)
                    c=edges(out)[(case*11+2)%15] if case<30 else rng.getrandbits(sum(FORMATS[out])+1)
                    result,flags=operation(code,kind,a,b,c,rm)
                    vl=0 if case%13==0 else 1;active=case%3!=1
                    lmul=([0,1,2,3] if kind==3 else [7,0,1,2])[case%4]
                    rows.append((code,kind,rm,lmul,vl,active,a,b,c,result if vl and active else c,flags if vl else 0))
    for kind in [0,2,3]:
        for wide in range(1 if kind==3 else 2):
            out=(3 if kind==2 else 2) if wide else kind
            for ordered in range(2):
                for rm in range(5):
                    for case in range(24):
                        lmul=([0,1,2,3] if kind==3 else [7,0,1,2])[case%4]
                        vmax=int((256//(sum(FORMATS[kind])+1))*(0.5 if lmul==7 else 1<<lmul));vl=[0,1,min(vmax,64),min(vmax,64)-1][case%4]
                        values=[rng.getrandbits(sum(FORMATS[kind])+1) for _ in range(64)]
                        if case%4==3:values=[edges(kind)[i%15] for i in range(64)]
                        mask=[255]*8 if case%3==0 else [0]*8 if case%3==1 else [rng.randrange(256) for _ in range(8)]
                        seed=edges(out)[case%15]
                        result,flags=reduction(kind,rm,wide,values[:vl],mask,seed) if vl else (0xa5a5a5a5a5a5a5a5&((1<<(sum(FORMATS[out])+1))-1),0)
                        reductions.append((kind,rm,wide,ordered,lmul,vl,seed,result,flags,values,mask))
    header='// Integer-only shared-scalar-FPU oracle, source masked-exception policy.\nstruct SharedCase {uint8_t code,kind,rm,lmul,vl,active;uint64_t a,b,c,out;uint8_t flags;};\nstatic const struct SharedCase shared_cases[]={\n'
    for code,kind,rm,lmul,vl,active,a,b,c,out,flags in rows:
        header+='{'+','.join(map(str,[code,kind,rm,lmul,vl,int(active)]))+','+','.join(str(v)+'ULL' for v in [a,b,c,out])+','+str(flags)+'},\n'
    header+='};\nstruct SharedReduction {uint8_t kind,rm,wide,ordered,lmul,vl;uint64_t seed,out;uint8_t flags;uint64_t data[64];uint8_t mask[8];};\nstatic const struct SharedReduction shared_reductions[]={\n'
    for kind,rm,wide,ordered,lmul,vl,seed,out,flags,values,mask in reductions:
        header+='{'+','.join(map(str,[kind,rm,wide,ordered,lmul,vl]))+','+str(seed)+'ULL,'+str(out)+'ULL,'+str(flags)+',{'+','.join(str(v)+'ULL' for v in values)+'},{'+','.join(map(str,mask))+'}},\n'
    header+='};\n';(HERE/'shared_fma_cases.hpp').write_text(header)
    receipt={'operation_cases':len(rows),'reduction_cases':len(reductions),'forms':45,'formats':['FP16','FP32','FP64'],
             'rounding_modes':5,'seed':0x53465055,'host_float_used':False,'rtl_executed':False,
             'header_sha256':hashlib.sha256(header.encode()).hexdigest(),
             'policy':'full IEEE flags including masked elements; ignored widening-converter flags; scalar ascending reduction plus final+0 for both opcodes'}
    (HERE/'shared-fma-oracle.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))

if __name__=='__main__':main()
