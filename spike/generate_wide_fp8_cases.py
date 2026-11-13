#!/usr/bin/env python3
"""Integer oracle for FP8->BF16 arithmetic and source-defined exception wiring."""
from pathlib import Path
import random,json,hashlib
from generate_fp8_cases import decode8
from generate_native_fp8_cases import ieee
HERE=Path(__file__).resolve().parent
NAMES=['vfwadd.vv','vfwadd.vf','vfwsub.vv','vfwsub.vf','vfwadd.wv','vfwadd.wf','vfwsub.wv','vfwsub.wf','vfwmul.vv','vfwmul.vf','vfwmacc.vv','vfwmacc.vf','vfwnmacc.vv','vfwnmacc.vf','vfwmsac.vv','vfwmsac.vf','vfwnmsac.vv','vfwnmsac.vf']
def bf(raw):
 s=raw>>15;e=(raw>>7)&255;m=raw&127
 return s,m+(128 if e else 0),(e if e else 1)-127-7,'nan' if e==255 and m else 'inf' if e==255 else 'finite',bool(e==255 and m and not m&64)
def wide(name,aa,bb,cc,fmt,rm,lane):
 def narrow(x):return (*decode8(x,fmt),False)
 a=bf(aa) if name.endswith(('.wv','.wf')) else narrow(aa)
 b=narrow(bb);c=bf(cc)
 if name.startswith(('vfwadd','vfwsub')):c=b;b=(0,1,0,'finite',False);cmd=1 if name.startswith('vfwsub') else 0
 elif name.startswith('vfwmul'):c=(a[0]^b[0],0,0,'finite',False);cmd=0
 else:cmd=3 if name.startswith('vfwnmacc') else 1 if name.startswith('vfwmsac') else 2 if name.startswith('vfwnmsac') else 0
 sa,ma,ea,ta,qa=a;sb,mb,eb,tb,qb=b;sc,mc,ec,tc,qc=c
 ps=sa^sb^bool(cmd&2);cs=sc^bool(cmd&1)
 invalid=bool(lane&3) and (qa or qb or qc)
 invalid|=(ta=='inf' and tb=='finite' and mb==0) or (tb=='inf' and ta=='finite' and ma==0)
 invalid|=ta!='nan' and tb!='nan' and (ta=='inf' or tb=='inf') and tc=='inf' and ps!=cs
 special='nan' if 'nan' in (ta,tb,tc) else 'inf' if 'inf' in (ta,tb,tc) else None
 n=q=zs=0
 if special is None and not invalid:
  q=min(ea+eb,ec);prod=ma*mb;n=((-1 if ps else 1)*prod<<(ea+eb-q))+((-1 if cs else 1)*mc<<(ec-q));zs=ps if not prod and not mc and ps==cs else rm==2
 out,_=ieee(n,q,zs,8,7,rm,special,ps if ta=='inf' or tb=='inf' else cs,invalid)
 return out,int(bool(invalid))
def main():
 rng=random.Random(0x57465038);rows=[]
 for fmt in range(2):
  for rm in range(5):
   for code,name in enumerate(NAMES):
    for i in range(64):
     a=rng.randrange(65536) if name.endswith(('.wv','.wf')) else rng.randrange(256)
     b=rng.randrange(256);c=[rng.randrange(65536),0x7f81,0xff80,0x7f80,0x7f7f,0x0001,0x8000,0][i%8]
     out,flags=wide(name,a,b,c,fmt,rm,i%4);rows.append((a,b,c,fmt,rm,code,i%4,out,flags))
 h='// Independent integer oracle, including source Bool-to-flags wiring.\nstruct WideCase {uint16_t a,c,out;uint8_t b,fmt,rm,code,lane,flags;};\nstatic const struct WideCase wide_cases[]={\n'
 for a,b,c,f,r,code,lane,out,flags in rows:h+='{'+','.join(str(x) for x in [a,c,out,b,f,r,code,lane,flags])+'},\n'
 h+='};\n';(HERE/'wide_fp8_cases.hpp').write_text(h)
 (HERE/'wide-fp8-oracle.json').write_text(json.dumps({'cases':len(rows),'operations':NAMES,'header_sha256':hashlib.sha256(h.encode()).hexdigest(),'host_float_used':False,'rtl_executed':False,'exception_policy':'Only FMA invalid is wired, as flags bit0; lane-dependent same-exp signalingness'},indent=2)+'\n')
if __name__=='__main__':main()
