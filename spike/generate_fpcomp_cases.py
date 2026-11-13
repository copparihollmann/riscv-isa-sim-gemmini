#!/usr/bin/env python3
"""Independent integer oracle of pinned Saturn FPComp behavior; no model imports."""
from pathlib import Path
import json,random,hashlib
HERE=Path(__file__).resolve().parent
NAMES=['vfmin.vv','vfmin.vf','vfmax.vv','vfmax.vf','vfsgnj.vv','vfsgnj.vf','vfsgnjn.vv','vfsgnjn.vf','vfsgnjx.vv','vfsgnjx.vf','vmfeq.vv','vmfeq.vf','vmfne.vv','vmfne.vf','vmflt.vv','vmflt.vf','vmfle.vv','vmfle.vf','vmfgt.vf','vmfge.vf','vfredmin.vs','vfredmax.vs']
def params(width):return {16:(5,10),32:(8,23),64:(11,52)}[width]
def classify(raw,width):
 e,m=params(width);exponent=raw>>m&((1<<e)-1);fraction=raw&((1<<m)-1)
 return bool(exponent==(1<<e)-1 and fraction)
def infinity(width):
 e,m=params(width);return ((1<<e)-1)<<m
def ordered_key(raw,width):
 sign=1<<(width-1);return (~raw&((1<<width)-1)) if raw&sign else raw|sign
def operation(a,b,width,name):
 an,bn=classify(a,width),classify(b,width);eq=a==b or not(a&((1<<(width-1))-1) or b&((1<<(width-1))-1));lt=not eq and ordered_key(a,width)<ordered_key(b,width)
 op=name.split('.')[0]
 if op in ['vfmin','vfmax','vfredmin','vfredmax']:
  if an and bn:return infinity(width)|(1<<(params(width)[1]-1))
  if an:return b
  if bn:return a
  return a if (lt if op in ['vfmin','vfredmin'] else not lt and not eq) else b
 if op.startswith('vfsgnj'):
  sb=(b>>(width-1))&1;sa=(a>>(width-1))&1
  sign=not sb if op=='vfsgnjn' else sa^sb if op=='vfsgnjx' else sb
  return (a&((1<<(width-1))-1))|(int(sign)<<(width-1))
 if op=='vmfne':return int(an or bn or not eq)
 if an or bn:return 0
 return int({'vmfeq':eq,'vmflt':lt,'vmfle':lt or eq,'vmfgt':not lt and not eq,'vmfge':not lt}[op])
def flags(a,b,width):
 fw=32 if width==64 else 16;bitmask=(1<<fw)-1
 return 16 if any(classify((v>>shift)&bitmask,fw) for data in [a,b] for v in data for shift in range(0,width,fw)) else 0
def words(raw,width):return [int.from_bytes(raw[i:i+width//8],'little') for i in range(0,len(raw),width//8)]
def pack(raw,i,width,value):raw[i*width//8:(i+1)*width//8]=value.to_bytes(width//8,'little')
def oracle(code,hart,width,vl,vm,mask,a,b,scalar,seed):
 name=NAMES[code];lanes=(256 if hart==2 else 128)//width;aa=words(a,width);bb=words(b,width);out=bytearray([165]*256);exception=0
 if not vl:return out,exception
 count=(vl+lanes-1)//lanes*lanes
 if name.endswith('.vf'):bb=[scalar&((1<<width)-1)]*len(bb)
 if code>=20:
  initial=infinity(width)|(1<<(width-1) if code==21 else 0);acc=[initial]*lanes;acc[0]=seed
  for base in range(0,count,lanes):
   source=aa[base:base+lanes];exception|=flags(source,acc,width)
   acc=[operation(source[lane],value,width,name) if base+lane<vl and (vm or mask[(base+lane)//8]&(1<<((base+lane)%8))) else value for lane,value in enumerate(acc)]
  for stage in range(lanes.bit_length()-2,-1,-1):
   offset=1<<stage;other=acc[offset:2*offset]+[0]*(lanes-offset);exception|=flags(acc,other,width)
   acc=[operation(value,other[lane],width,name) if offset>1 or lane==0 else value for lane,value in enumerate(acc)]
  pack(out,0,width,acc[0])
 else:
  exception|=flags(aa[:count],bb[:count],width)
  for i in range(vl):
   if not(vm or mask[i//8]&(1<<(i%8))):continue
   value=operation(aa[i],bb[i],width,name)
   if code>=10:out[i//8]=(out[i//8]&~(1<<(i%8)))|(value<<(i%8))
   else:pack(out,i,width,value)
 return out,exception

def main():
 rng=random.Random(0x4650434d50);rows=[]
 for hart in [0,2]:
  for width,alt in [(w,alt) for w in [16,32,64] for alt in [0,1]]:
   e,m=params(width);sign=1<<(width-1);inf=infinity(width);edge=[0,sign,1,sign|1,inf,inf|sign,inf|(1<<(m-1)),inf|1,inf-1,sign|(inf-1),1<<m,sign|(1<<m)]
   for code,name in enumerate(NAMES):
    for case in range(32):
     lmul=([0,1,2,3] if width==64 else [7,0,1,2,3])[case%(4 if width==64 else 5)];vmax=int(256//width*(0.5 if lmul==7 else 1<<lmul));lanes=(256 if hart==2 else 128)//width
     vl=[0,1,vmax-1,vmax,min(vmax,lanes+1),max(1,min(vmax,lanes-1))][case%6];vm=case%4==0
     a=bytearray(rng.getrandbits(8) for _ in range(256));b=bytearray(rng.getrandbits(8) for _ in range(256));mask=bytearray(rng.randrange(256) for _ in range(16))
     for i in range(256//width*8):
      if case<16:pack(a,i,width,edge[(case+i)%len(edge)]);pack(b,i,width,edge[(case*3+i+1)%len(edge)])
     if case in [1,2]:pack(a,0,width,sign if case==2 else 0);pack(b,0,width,0 if case==2 else sign);mask[0]=255
     if case%7==4:mask=bytearray(16)
     if case==13:
      a=bytearray(256);b=bytearray(256);mask=bytearray(16)
      pack(a,lanes-1,width,0x7fc00000 if width==64 else 0x7e00)
     if case==14:
      a=bytearray(256);b=bytearray(256);pack(a,0,width,inf)
     scalar=words(b,width)[0]|((~((1<<width)-1)&((1<<64)-1)) if width<64 and case%2 else 0);seed=(inf|(1<<(m-1))) if case==11 else edge[case%len(edge)]
     out,exception=oracle(code,hart,width,vl,vm,mask,a,b,scalar,seed)
     rows.append((code,hart,width,alt,lmul,vl,vm,exception,scalar,seed,a,b,mask,out))
 header='// Independent integer-only Saturn FPComp oracle.\n#include <stdint.h>\nstruct CmpCase {uint8_t code,hart,width,alt,lmul,vl,vm,flags;uint64_t scalar,seed;uint8_t a[256],b[256],mask[16],out[256];};\nstatic const struct CmpCase cmp_cases[]={\n'
 for row in rows:
  first=','.join(str(int(v)) for v in row[:8])+','+str(row[8])+'ULL,'+str(row[9])+'ULL,'
  header+='{'+first+','.join('{'+','.join(map(str,v))+'}' for v in row[10:])+'},\n'
 header+='};\n';(HERE/'fpcomp_cases.hpp').write_text(header)
 receipt={'cases':len(rows),'forms':22,'seed':0x4650434d50,'host_float_used':False,'rtl_executed':False,'source_image_association_verified':False,'header_sha256':hashlib.sha256(header.encode()).hexdigest(),'policy':'flags H chunks except S chunks at SEW64; full unmasked physical EG incl tail; min/max ties vs1; altfmt accepted and ignored at H/S/D widths on all harts; reductions DLEN-dependent per-lane plus halving fold'}
 (HERE/'fpcomp-oracle.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
