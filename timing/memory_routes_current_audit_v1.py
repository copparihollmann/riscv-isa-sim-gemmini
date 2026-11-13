#!/usr/bin/env python3
"""Independent exact-ELF memory corpus/golden/geometry audit; no timing labels."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
REGIONS={'tcm0':0x70000000,'tcm1':0x70020000,'scratchpad':0x580000000,'dram':0x84000000}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Elf:
    def __init__(self,path):
        self.raw=Path(path).read_bytes();r=self.raw
        def u(fmt,off):
            if off<0 or off+struct.calcsize(fmt)>len(r):raise ValueError('Truncated ELF structure')
            return struct.unpack_from(fmt,r,off)
        h=u('<16sHHIQQQIHHHHHH',0)
        if h[0][:7]!=b'\x7fELF\x02\x01\x01'or h[1:4]!=(2,243,1)or h[8]!=64 or h[9]!=56 or h[11]!=64:
            raise ValueError('Static RV64 little-endian ELF required')
        self.loads=[]
        for i in range(h[10]):
            typ,flags,pos,va,pa,fs,ms,align=u('<IIQQQQQQ',h[5]+i*56)
            if typ==1:
                if va!=pa or fs>ms or pos+fs>len(r):raise ValueError('ELF physical load bounds')
                self.loads.append((pa,pos,fs,ms,flags))
        sections=[u('<IIQQQQIIQQ',h[6]+i*64)for i in range(h[12])];self.symbols={}
        for section in sections:
            if section[1]!=2:continue
            if section[9]!=24 or section[5]%24 or section[6]>=len(sections):raise ValueError('ELF symtab geometry')
            names=sections[section[6]];strings=r[names[4]:names[4]+names[5]]
            for pos in range(section[4],section[4]+section[5],24):
                n,info,other,index,value,size=u('<IBBHQQ',pos)
                if not index or not n or info&15 not in (0,1,2):continue
                end=strings.find(b'\0',n)
                if end<0:raise ValueError('ELF unterminated symbol')
                name=strings[n:end].decode()
                self.symbols.setdefault(name,[]).append((value,size))
    def symbol(self,name):
        values=self.symbols.get(name,[])
        if len(values)!=1:raise ValueError('Unique ELF object required: '+name)
        return values[0]
    def read(self,address,n):
        for base,pos,fs,ms,flags in self.loads:
            if base<=address and address+n<=base+fs:return self.raw[pos+address-base:pos+address-base+n]
        raise ValueError('Required bytes not file-backed')
    def string(self,address):
        value=bytearray()
        for i in range(256):
            c=self.read(address+i,1)
            if c==b'\0':return value.decode()
            value.extend(c)
        raise ValueError('Bounded compiled string required')


def golden(case,hart):
    start=case['base']+hart*32768+(64*(hart%2)if case['spread']else 0)
    if case['kind']=='chase':return start+((case['n']*13)%64)*case['stride']
    if case['kind']=='read':return case['n']*(64*(4096+256*hart)+2016)
    if case['kind']=='write':return 64*(case['n']*256+hart)
    raise ValueError('Unknown kernel')


def rows_check(rows,corpus):
    expected=[(i,h)for i,c in enumerate(corpus['cases'])for h in range(3)if c['mask']&(1<<h)]
    if len(rows)!=len(expected):raise ValueError('Incomplete exact region coverage')
    previous={}
    for row,(i,h)in zip(rows,expected):
        case=corpus['cases'][i]
        if any(type(row.get(k))is not int for k in ('hart','start_cycle','end_cycle','instret_delta','checksum','expected_checksum')):
            raise ValueError('Exact integer region fields required')
        if any(row.get(k)!=case[k]for k in ('case_id','parent_case_id','trial_id','suite'))or row['hart']!=h or row.get('region')!='kernel':
            raise ValueError('Wrong record ordering/case/hart identity')
        if not 0<=row['start_cycle']<row['end_cycle']<2**64 or row['instret_delta']<=0 or row['start_cycle']<=previous.get(h,-1):
            raise ValueError('Invalid region times/retirement ordering')
        previous[h]=row['end_cycle']
        if row['checksum']!=golden(case,h)or row['expected_checksum']!=golden(case,h)or row.get('pass')is not True:
            raise ValueError('Independent memory value/pointer golden mismatch')
    return len(rows)


def audit(build):
    build=Path(build).resolve();ready=json.loads((build/'ready.json').read_text());corpus=json.loads((build/'corpus.json').read_text())
    layout=json.loads((build/'readback-layout.json').read_text());split=json.loads((build/'split.json').read_text());elf=Elf(build/'memory-routes.elf')
    if sha(build/'ready.json')!='9fd265b7abe38e0d0bc2b2020730f9e07a7f524e1ca475c89590b439bb034b2c':raise ValueError('Frozen readiness identity changed')
    if sha(build/'memory-routes.elf')!='bc35d90129829608f681a9451502806d54dcbf331d5e30b8e4bb70749148d268':raise ValueError('Exact ELF changed')
    if ready['elf_sha256']!=sha(build/'memory-routes.elf')or ready['corpus_sha256']!=sha(build/'corpus.json'):raise ValueError('Ready identities differ')
    if corpus.get('fitting_only')is not True or corpus.get('global_heldout')is not False or len(corpus['cases'])!=1512:raise ValueError('Fitting-only complete corpus required')
    expected=[]
    for target,base in REGIONS.items():
        for pattern,stride,spread in [('bank0',128,0),('hart-banks',128,1),('alternating',64,0)]:
            for kind,counts in [('chase',(33,257)),('read',(1,16)),('write',(1,16))]:
                for n in counts:
                    for mask in range(1,8):
                        parent=f'memroute.{target}.{pattern}.{kind}.{n}.mask{mask}';semantic=f'memroute.{target}.{pattern}.{kind}.mask{mask}'
                        partition='internal_validation'if int(hashlib.sha256(semantic.encode()).hexdigest()[:8],16)%5==0 else'train'
                        if split['split'].get(semantic)!=partition:raise ValueError('Frozen N/trial/hart-group split differs')
                        for trial in range(3):expected.append({'base':base,'target_region':target,'stride':stride,'spread':spread,'kind':kind,'n':n,'mask':mask,'parent_case_id':parent,'semantic_parent_case_id':semantic,'trial_id':trial,'suite':'memory_routes_current','case_id':'memroute.current.v1.'+parent+'.r'+str(trial)})
    table,sz=elf.symbol('experiments');parents,psz=elf.symbol('parent_ids');trials,tsz=elf.symbol('trial_ids')
    if(sz,psz,tsz)!=(1512*64,1512*8,1512*4):raise ValueError('Compiled table extent mismatch')
    for i,(case,canonical)in enumerate(zip(corpus['cases'],expected)):
        if any(type(case.get(k))is not type(v)or case.get(k)!=v for k,v in canonical.items()):raise ValueError('Canonical case/order differs')
        pointers=[case['base']+h*32768+(64*(h%2)if case['spread']else 0)for h in range(3)]
        values=[golden(case,h)for h in range(3)]
        if case['addresses_by_hart']!=pointers or case['expected_checksums']!=values:raise ValueError('Address/value goldens differ')
        if any(not case['base']+h*32768<=a or a+63*case['stride']+8>case['base']+(h+1)*32768 for h,a in enumerate(pointers)):
            raise ValueError('Hart memory windows overlap or overflow')
        if case['bank_bit6_sequence_by_hart']!=[[((a+i*case['stride'])>>6)&1 for i in range(64)]for a in pointers]:raise ValueError('Bank address-bit pattern differs')
        row=struct.unpack('<QQIIIII4xQQQ',elf.read(table+i*64,64));kind=('chase','read','write').index(case['kind'])
        if elf.string(row[0])!=case['case_id']or row[1:7]!=(case['base'],kind,case['stride'],case['spread'],case['n'],case['mask'])or list(row[7:])!=values:
            raise ValueError('Compiled payload/table/golden differs')
        if elf.string(struct.unpack('<Q',elf.read(parents+i*8,8))[0])!=case['parent_case_id']or struct.unpack('<I',elf.read(trials+i*4,4))[0]!=case['trial_id']:
            raise ValueError('Compiled parent/trial tables differ')
    for name,entry in layout['objects'].items():
        if elf.symbol(name)!=(entry['address'],entry['size']):raise ValueError('Readback layout object differs')
    if layout['record_bytes']!=64 or layout['records']!=2592 or layout['objects']['buffered_records']['size']!=2592*64:
        raise ValueError('Readback record extent')
    if int.from_bytes(elf.read(layout['objects']['buffered_measurements_done']['address'],8),'little')!=2**64-1:raise ValueError('Known file-backed completion sentinel required')
    for base,pos,fs,ms,flags in elf.loads:
        if any(max(base,a)<min(base+ms,a+0x20000)for a in REGIONS.values()):raise ValueError('ELF target windows overlap')
    built=json.loads((build/'build.json').read_text());original=ROOT/'benchmarks/memory_routes/guest.c'
    a=original.read_text();b=(build/'guest.c').read_text();start='static uintptr_t address(';end='  if(h==0) for(unsigned i=0;i<3;++i) if(c->mask&(1U<<i)) {'
    old=a[a.index(start):a.index(end)];new=b[b.index(start):b.index('  if(h==0) {\n    const uint64_t case_index')]
    if old!=new:raise ValueError('Preparation and measured source window changed')
    prior=ROOT/'build/memory-routes-fit-v1-final/memory-routes.elf';prior_sha=built['input_sha256'][str(prior)]
    snapshot=build/'inputs'/prior_sha
    if sha(snapshot)!=prior_sha:raise ValueError('Original compiled kernel source snapshot changed')
    previous=Elf(snapshot);address,n=elf.symbol('kernel');pa,pn=previous.symbol('kernel')
    if n!=160 or n!=pn or elf.read(address,n)!=previous.read(pa,pn):raise ValueError('Compiled scalar kernel changed')
    return corpus,layout,{'compiled_cases':1512,'compiled_goldens_checked':4536,'regions':2592,'base_parent_cases':504,'semantic_split_groups':252,'compiled_kernel_bytes':160,
        'kernel_preparation_and_measured_source_unchanged':True,'normal_exit_functional_seeds':[0,17],
        'identifiability_scope':['Only scalar64-bit LD/SD, pointer-dependence and effective target-route/contention service. No RVV/VME/FP service inference.',
            'Preparation/fence/barrier establishes values, not a measured physical hit/cold/cache state; DRAM address probes may hit private L1.',
            'Source bit6 selects TCM/scratch banks; it does not identify DRAM device banks.',
            'Only small64-line footprints, two repetition counts, masks1..7 and three repeats; separate physical cache/NoC/serial service remains unidentifiable without further observations.'],
        'old_timing_labels_applicable':False,'hardware_contacted':False,'timing_labels_read':False,'global_heldout_timings_consumed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    corpus,layout,result=audit(args.build);out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result.update(schema='iris.memory_routes_current_independent_native_audit.v1',pass_=True)
    result['pass']=result.pop('pass_');paths=[Path(__file__).resolve(),*[args.build.resolve()/n for n in ('ready.json','build.json','corpus.json','split.json','readback-layout.json','guest.c','memory-routes.elf')],ROOT/'benchmarks/memory_routes/guest.c',ROOT/'firesim/prepare_memory_routes_current.py',ROOT/'firesim/analyze_memory_routes_current.py']
    result['input_sha256']={str(f):sha(f)for f in paths};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
