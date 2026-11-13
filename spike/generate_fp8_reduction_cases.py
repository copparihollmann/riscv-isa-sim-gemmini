#!/usr/bin/env python3
from pathlib import Path
import random,json,hashlib
from generate_native_fp8_cases import native,ieee
from generate_wide_fp8_cases import wide,bf
HERE=Path(__file__).resolve().parent

def bfadd(a,b,rm,lane):
 sa,ma,ea,ta,qa=bf(a);sb,mb,eb,tb,qb=bf(b)
 invalid=bool(lane&3) and (qa or qb)
 invalid|=ta=='inf' and tb=='inf' and sa!=sb
 special='nan' if 'nan' in (ta,tb) else 'inf' if 'inf' in (ta,tb) else None
 n=q=zs=0
 if special is None and not invalid:
  q=min(ea,eb);n=((-1 if sa else 1)*ma<<(ea-q))+((-1 if sb else 1)*mb<<(eb-q));zs=sa if not ma and not mb and sa==sb else rm==2
 out,_=ieee(n,q,zs,8,7,rm,special,sa if ta=='inf' else sb,invalid)
 return out,int(bool(invalid))
def reduce(values,mask,seed,fmt,rm,widen,ordered):
 lanes=8 if widen else 16;acc=[seed]+[0]*(lanes-1);flags=0
 def add(a,b,lane,narrow):
  nonlocal flags
  if not widen:result,exc=native(a,0x3c if fmt else 0x38,b,fmt,rm,0,lane%8)
  elif narrow:result,exc=wide('vfwadd.wv',a,b,0,fmt,rm,lane)
  else:result,exc=bfadd(a,b,rm,lane)
  flags|=exc;return result
 for i,val in enumerate(values):
  if mask[i//8]&(1<<(i%8)):
   lane=0 if ordered else i%lanes;acc[lane]=add(acc[lane],val,lane,True)
 if ordered:acc[0]=add(acc[0],0,0,False)
 else:
  offset=lanes//2
  while offset:
   for lane in range(1 if offset==1 else lanes):acc[lane]=add(acc[lane],acc[lane+offset] if lane<offset else 0,lane,False)
   offset//=2
 return acc[0],flags

def main():
 rng=random.Random(0x52465038);rows=[]
 for fmt in range(2):
  for rm in range(5):
   for widen in range(2):
    for ordered in range(2):
     for case in range(16):
      lmul=[7,0,1,2,3][case%5];maxvl=16 if lmul==7 else 32<<lmul;vl=[0,1,maxvl,maxvl-3,rng.randrange(maxvl+1)][case%5]
      values=[rng.randrange(256) for _ in range(256)];mask=[rng.randrange(256) for _ in range(32)]
      if case%4==0:mask=[255]*32
      elif case%4==1:mask=[0]*32
      if case%2==0:values=[v&0xbf for v in values]
      if case==3:values=[0x7b if fmt else 0x7e]*256
      if case==7:values=[(0x7b if fmt else 0x7e)|(128 if i&1 else 0) for i in range(256)]
      seed=rng.randrange(65536 if widen else 256)
      if case in [3,7]:seed=0
      if case==1:seed=0x8000 if widen else 0x80
      if case%4==2:seed=0x7f81 if widen else 0x7d
      out,flags=reduce(values[:vl],mask,seed,fmt,rm,widen,ordered) if vl else (0xa5a5 if widen else 0xa5,0)
      rows.append((fmt,rm,widen,ordered,lmul,vl,seed,out,flags,values,mask))
 h='// Independent integer reduction graph oracle for audited DLEN128 source.\nstruct ReductionCase {uint8_t fmt,rm,wide,ordered,lmul;uint16_t vl,seed,out;uint8_t flags,data[256],mask[32];};\nstatic const struct ReductionCase reduction_cases[]={\n'
 for f,r,w,o,l,v,s,out,flags,data,mask in rows:h+='{'+','.join(str(x) for x in [f,r,w,o,l,v,s,out,flags])+',{'+','.join(str(x) for x in data)+'},{'+','.join(str(x) for x in mask)+'}},\n'
 h+='};\n';(HERE/'fp8_reduction_cases.hpp').write_text(h)
 (HERE/'fp8-reduction-oracle.json').write_text(json.dumps({'cases':len(rows),'header_sha256':hashlib.sha256(h.encode()).hexdigest(),'source_order':'DLEN128 lane accumulation and halving fold, ordered final+0','host_float_used':False,'rtl_executed':False},indent=2)+'\n')
if __name__=='__main__':main()
