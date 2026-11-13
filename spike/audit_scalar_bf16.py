#!/usr/bin/env python3
"""Prove advertised scalar BF16 opcodes miss every pinned Rocket BitPat."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def main():
 source=ROOT/'third_party/rocket-chip/src/main/scala/rocket/Instructions.scala'
 custom=ROOT/'third_party/rocket-chip/src/main/scala/rocket/CustomInstructions.scala'
 rows=[]
 counts={}
 for path,expected in [(source,807),(custom,28)]:
  found=re.findall(r'def\s+(\w+)\s*=\s*BitPat\("b([01?]{32})"\)',path.read_text())
  if len(found)!=expected:raise SystemExit('Pinned decoder pattern count changed; reaudit required: '+str(path))
  counts[path.name]=len(found)
  for name,bits in found:
   mask=int(''.join('0' if b=='?' else '1' for b in bits),2);value=int(bits.replace('?','0'),2);rows.append((name,value,mask))
 result=[]
 for name,value,mask in [('fcvt.bf16.s',0x44800053,0xfff0007f),('fcvt.s.bf16',0x40600053,0xfff0007f)]:
  intersections=[n for n,v,m in rows if not((v^value)&m&mask)]
  if intersections:raise SystemExit('Scalar BF16 decode overlap: '+repr(intersections))
  result.append({'instruction':name,'value':hex(value),'mask':hex(mask),'intersections':intersections,'result':'architectural-illegal-no-decoder-entry'})
 inputs=[source,custom,ROOT/'third_party/rocket-chip/src/main/scala/rocket/IDecode.scala',ROOT/'third_party/rocket-chip/src/main/scala/tile/FPU.scala',ROOT/'third_party/shuttle/src/main/scala/exu/Core.scala',ROOT/'third_party/saturn/src/main/scala/frontend/EarlyDecode.scala']
 receipt={'all_instruction_patterns':len(rows),'pattern_counts':counts,'proof':'No fixed-bit intersection with any of the 807 Rocket Instructions.scala or 28 CustomInstructions.scala patterns, including patterns not enabled by Iris. The inspected scalar integer/control and FPU decode tables select these definitions; Saturn EarlyDecode opcode alternatives exclude scalar FP opcode0x53. This proves source decoder absence, not deployed-image equivalence.','rtl_executed':False,'cases':result,'source_inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
 (HERE/'scalar-bf16-decoder-proof.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('scalar_bf16_decoder_patterns='+str(len(rows))+' normal=807 custom=28 both_opcodes_disjoint pass')
if __name__=='__main__':main()
