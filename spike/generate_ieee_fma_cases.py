#!/usr/bin/env python3
"""Independent integer oracle for compute segmented IEEE/BF16 FMA and graph reductions."""
from pathlib import Path
import random,json,hashlib
from generate_native_fp8_cases import ieee
HERE=Path(__file__).resolve().parent
# kind H,BF16,S,D. Form names supply independent mathematical equations.
FORMATS=[(5,10),(8,7),(8,23),(11,52)]
ORDINARY=['vfadd.vv','vfadd.vf','vfsub.vv','vfsub.vf','vfrsub.vf','vfmul.vv','vfmul.vf','vfmacc.vv','vfmacc.vf','vfnmacc.vv','vfnmacc.vf','vfmsac.vv','vfmsac.vf','vfnmsac.vv','vfnmsac.vf','vfmadd.vv','vfmadd.vf','vfnmadd.vv','vfnmadd.vf','vfmsub.vv','vfmsub.vf','vfnmsub.vv','vfnmsub.vf']
WIDE=['vfwadd.vv','vfwadd.vf','vfwsub.vv','vfwsub.vf','vfwadd.wv','vfwadd.wf','vfwsub.wv','vfwsub.wf','vfwmul.vv','vfwmul.vf','vfwmacc.vv','vfwmacc.vf','vfwnmacc.vv','vfwnmacc.vf','vfwmsac.vv','vfwmsac.vf','vfwnmsac.vv','vfwnmsac.vf']
NAMES=ORDINARY+WIDE

def number(raw,kind,physical_exp):
 eb,mb=FORMATS[kind];exp=(raw>>mb)&((1<<eb)-1);fraction=raw&((1<<mb)-1);sign=raw>>(eb+mb)&1
 special='nan' if exp==(1<<eb)-1 and fraction else 'inf' if exp==(1<<eb)-1 else None
 signaling=special=='nan' and not fraction&(1<<(mb-1)) and eb==physical_exp
 return sign,(1<<mb)|fraction if exp else fraction,(exp if exp else 1)-((1<<(eb-1))-1)-mb,special,signaling

def physical_exp(kind,lane):
 if kind==3:return 11
 if kind==2:return 8 if lane%2 else 11
 return [11,FORMATS[kind][0],8,FORMATS[kind][0]][lane%4]

def exact(a,b,c,kind,rm,cmd):
 sa,ma,ea,ta,qa=a;sb,mb,eb,tb,qb=b;sc,mc,ec,tc,qc=c
 ps=sa^sb^bool(cmd&2);cs=sc^bool(cmd&1)
 invalid=qa or qb or qc
 invalid|=ta=='inf' and tb is None and not mb or tb=='inf' and ta is None and not ma
 invalid|=ta!='nan' and tb!='nan' and (ta=='inf' or tb=='inf') and tc=='inf' and ps!=cs
 special='nan' if 'nan' in (ta,tb,tc) else 'inf' if 'inf' in (ta,tb,tc) else None
 n=q=zs=0
 if special is None and not invalid:
  q=min(ea+eb,ec);product=ma*mb
  n=((-1 if ps else 1)*product<<(ea+eb-q))+((-1 if cs else 1)*mc<<(ec-q))
  zs=ps if not product and not mc and ps==cs else rm==2
 bits,unused=ieee(n,q,zs,*FORMATS[kind],rm,special,ps if ta=='inf' or tb=='inf' else cs,invalid)
 return bits,int(bool(invalid))

def operation(code,kind,a,b,c,rm,lane):
 name=NAMES[code];wide=code>=len(ORDINARY);out=(3 if kind==2 else 2) if wide else kind
 atype=out if '.w' in name else kind
 pa=physical_exp(out,lane);aa=number(a,atype,pa);bb=number(b,kind,pa);cc=number(c,out,pa)
 one=(0,1,0,None,False);zero=(0,0,0,None,False)
 op=name.split('.')[0]
 if op in ['vfadd','vfwadd']:return exact(aa,one,bb,out,rm,0)
 if op in ['vfsub','vfwsub']:return exact(aa,one,bb,out,rm,1)
 if op=='vfrsub':return exact(aa,one,bb,out,rm,2)
 if op in ['vfmul','vfwmul']:
  zero=(aa[0]^bb[0],0,0,None,False);return exact(aa,bb,zero,out,rm,0)
 cmd=3 if op in ['vfnmacc','vfwnmacc','vfnmadd'] else 1 if op in ['vfmsac','vfwmsac','vfmsub'] else 2 if op in ['vfnmsac','vfwnmsac','vfnmsub'] else 0
 if op in ['vfmadd','vfnmadd','vfmsub','vfnmsub']:aa,cc=cc,aa
 return exact(aa,bb,cc,out,rm,cmd)

def edges(kind):
 eb,mb=FORMATS[kind];inf=((1<<eb)-1)<<mb;one=((1<<(eb-1))-1)<<mb;sign=1<<(eb+mb)
 return [0,sign,1,sign|1,(1<<mb)-1,1<<mb,one,one+1,one-1,inf-1,inf,inf|sign,inf+1,inf+(1<<(mb-1)),inf+(1<<(mb-1))+1]

def reduction(kind,rm,wide,ordered,values,mask,seed):
 out=(3 if kind==2 else 2) if wide else kind;lanes=128//(sum(FORMATS[out])+1);acc=[seed]+[0]*(lanes-1);flags=0
 def add(a,b,lane,narrow):
  nonlocal flags
  pa=physical_exp(out,lane);aa=number(a,out,pa);bb=number(b,kind if narrow else out,pa)
  bits,exc=exact(aa,(0,1,0,None,False),bb,out,rm,0);flags|=exc;return bits
 for i,value in enumerate(values):
  if mask[i//8]&(1<<(i%8)):
   lane=0 if ordered else i%lanes;acc[lane]=add(acc[lane],value,lane,True)
 if ordered:acc[0]=add(acc[0],0,0,False)
 else:
  offset=lanes//2
  while offset:
   for lane in range(1 if offset==1 else lanes):acc[lane]=add(acc[lane],acc[lane+offset] if lane<offset else 0,lane,False)
   offset//=2
 return acc[0],flags

def main():
 rng=random.Random(0x49454545);rows=[];reds=[]
 for code,name in enumerate(NAMES):
  for kind in range(3 if code>=23 else 4):
   out=(3 if kind==2 else 2) if code>=23 else kind;atype=out if '.w' in name else kind
   for rm in range(5):
    for case in range(32):
     ak,bk,ck=edges(atype),edges(kind),edges(out)
     a=ak[case%len(ak)] if case<24 else rng.getrandbits(sum(FORMATS[atype])+1)
     b=bk[(case*7+4)%len(bk)] if case<24 else rng.getrandbits(sum(FORMATS[kind])+1)
     c=ck[(case*11+2)%len(ck)] if case<24 else rng.getrandbits(sum(FORMATS[out])+1)
     lane=case%(64//(sum(FORMATS[out])+1));result,flags=operation(code,kind,a,b,c,rm,lane)
     rows.append((code,kind,rm,lane,a,b,c,result,flags))
 for kind in range(4):
  for wide in range(1 if kind==3 else 2):
   out=(3 if kind==2 else 2) if wide else kind
   for ordered in range(2):
    for rm in range(5):
     for case in range(16):
      lmul=([0,1,2,3] if kind==3 else [7,0,1,2])[case%4];vmax=(256//(sum(FORMATS[kind])+1))*(0.5 if lmul==7 else 1<<lmul);vmax=int(vmax)
      vl=[0,1,vmax,vmax-1][case%4];values=[rng.getrandbits(sum(FORMATS[kind])+1) for _ in range(64)];mask=[rng.randrange(256) for _ in range(8)]
      if case%3==0:mask=[255]*8
      if case%3==1:mask=[0]*8
      if case%4==3:values=[edges(kind)[i%len(edges(kind))] for i in range(64)]
      seed=edges(out)[case%len(edges(out))]
      result,flags=reduction(kind,rm,wide,ordered,values[:vl],mask,seed) if vl else (0xa5a5a5a5a5a5a5a5&((1<<(sum(FORMATS[out])+1))-1),0)
      reds.append((kind,rm,wide,ordered,lmul,vl,seed,result,flags,values,mask))
 header='// Independent arbitrary-precision IEEE/BF16 source oracle; no host FP.\nstruct IeeeCase {uint8_t code,kind,rm,lane;uint64_t a,b,c,out;uint8_t flags;};\nstatic const struct IeeeCase ieee_cases[]={\n'
 for code,kind,rm,lane,a,b,c,out,flags in rows:header+='{'+','.join(map(str,[code,kind,rm,lane]))+','+','.join(str(v)+'ULL' for v in [a,b,c,out])+','+str(flags)+'},\n'
 header+='};\nstruct IeeeReduction {uint8_t kind,rm,wide,ordered,lmul,vl;uint64_t seed,out;uint8_t flags;uint64_t data[64];uint8_t mask[8];};\nstatic const struct IeeeReduction ieee_reductions[]={\n'
 for kind,rm,wide,ordered,lmul,vl,seed,out,flags,values,mask in reds:header+='{'+','.join(map(str,[kind,rm,wide,ordered,lmul,vl]))+','+str(seed)+'ULL,'+str(out)+'ULL,'+str(flags)+',{'+','.join(str(v)+'ULL' for v in values)+'},{'+','.join(map(str,mask))+'}},\n'
 header+='};\n';(HERE/'ieee_fma_cases.hpp').write_text(header)
 (HERE/'ieee-fma-oracle.json').write_text(json.dumps({'cases':len(rows),'reduction_cases':len(reds),'forms':45,'formats':['FP16','BF16','FP32','FP64'],'rounding_modes':5,'seed':0x49454545,'header_sha256':hashlib.sha256(header.encode()).hexdigest(),'host_float_used':False,'rtl_executed':False,'source_semantics':'compute segmented unrounded FMA; input signalingness depends physical exponent; only invalid maps to flagsbit0; DLEN128 reduction graph'},indent=2)+'\n')
 print('ieee_fma_integer_oracle',len(rows),'reductions',len(reds))
if __name__=='__main__':main()
