#!/usr/bin/env python3
from pathlib import Path
import random,json,hashlib
from generate_native_fp8_cases import native
HERE=Path(__file__).resolve().parent
NAMES=['vfadd.vv','vfadd.vf','vfsub.vv','vfsub.vf','vfrsub.vf','vfmul.vv','vfmul.vf','vfmacc.vv','vfmacc.vf','vfnmacc.vv','vfnmacc.vf','vfmsac.vv','vfmsac.vf','vfnmsac.vv','vfnmsac.vf','vfmadd.vv','vfmadd.vf','vfnmadd.vv','vfnmadd.vf','vfmsub.vv','vfmsub.vf','vfnmsub.vv','vfnmsub.vf']
def operation(name,a,b,c,fmt):
 op=name.split('.')[0]
 if op in ['vfadd','vfsub','vfrsub']:return a,0x3c if fmt else 0x38,b,{'vfadd':0,'vfsub':1,'vfrsub':2}[op]
 if op=='vfmul':return a,b,(a^b)&128,0
 cmd={'vfmacc':0,'vfnmacc':3,'vfmsac':1,'vfnmsac':2,'vfmadd':0,'vfnmadd':3,'vfmsub':1,'vfnmsub':2}[op]
 return (c,b,a,cmd) if op in ['vfmadd','vfnmadd','vfmsub','vfnmsub'] else (a,b,c,cmd)
def main():
 rng=random.Random(0x4e475545);rows=[]
 for fmt in range(2):
  for rm in range(5):
   for code,name in enumerate(NAMES):
    a=[rng.randrange(256) for _ in range(256)];b=[rng.randrange(256) for _ in range(256)];c=[rng.randrange(256) for _ in range(256)]
    a[:8]=[0,128,1,0x7d,0x7c,0xff,0xfb,0x7e]
    if name.endswith('.vf'):b=[b[0]]*256
    out=[];flags=[]
    for lane in range(256):
     aa,bb,cc,cmd=operation(name,a[lane],b[lane],c[lane],fmt)
     value,exc=native(aa,bb,cc,fmt,rm,cmd,lane)
     out.append(value);flags.append(exc)
    rows.append((code,fmt,rm,a,b,c,out,flags))
 h='// Generated independent native FP8 golden vectors; arbitrary-precision oracle.\nstruct NativeGuest {unsigned char code,fmt,rm,a[256],b[256],c[256],out[256],flags[256];};\nstatic const struct NativeGuest native_guests[]={\n'
 for code,fmt,rm,*arrays in rows:h+='{'+f'{code},{fmt},{rm},'+','.join('{'+','.join(str(v) for v in arr)+'}' for arr in arrays)+'},\n'
 h+='};\n#define NATIVE_GUEST_COUNT '+str(len(rows))+'\n'
 (HERE/'native_guest_cases.h').write_text(h)
 (HERE/'native-guest-oracle.json').write_text(json.dumps({'cases':len(rows),'operations':NAMES,'header_sha256':hashlib.sha256(h.encode()).hexdigest(),'host_float_used':False,'rtl_executed':False},indent=2)+'\n')
 switch='\n'.join(f'case {i}: __asm__ volatile("{name} v24, '+('v8, f3' if name.endswith('.vf') else 'v8, v16')+'" ::: "memory");break;' for i,name in enumerate(NAMES))
 # Fused VF assembler order is scalar first, vs2 last; VV also rs1 then vs2.
 for i,name in enumerate(NAMES):
  if name.split('.')[0] in ['vfmacc','vfnmacc','vfmsac','vfnmsac','vfmadd','vfnmadd','vfmsub','vfnmsub']:
   old=f'{name} v24, '+('v8, f3' if name.endswith('.vf') else 'v8, v16')
   new=f'{name} v24, '+('f3, v8' if name.endswith('.vf') else 'v16, v8')
   switch=switch.replace(old,new)
 (HERE/'native_guest_switch.h').write_text(switch+'\n')
 (HERE/'native_guest_masked_switch.h').write_text(switch.replace('" :::',', v0.t" :::')+'\n')
if __name__=='__main__':main()
