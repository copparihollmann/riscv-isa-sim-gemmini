#!/usr/bin/env python3
"""Explicitly resolve only reviewed additive composition conflicts."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1];S=R/'pipeline/riscv-isa-sim-C12-composite-v1';O=R/'build/C12-composite-preparation-v1'
def parse(lines,i=0,stop=()):
 out=[]
 while i<len(lines):
  line=lines[i]
  if any(line.startswith(x)for x in stop):return out,i
  if line.startswith('<<<<<<< '):
   left,j=parse(lines,i+1,('||||||| ','=======\n'));base=[]
   if lines[j].startswith('||||||| '):base,j=parse(lines,j+1,('=======\n',))
   right,j=parse(lines,j+1,('>>>>>>> ',));assert lines[j].startswith('>>>>>>> ')
   # All cc conflicts are additions against an empty common base.
   assert not ''.join(base).strip(),''.join(base)
   out+=left+right;i=j+1
  else:out.append(line);i+=1
 return out,i
p=S/'riscv/iris_timing_adapter.cc';ls=p.read_text().splitlines(True);resolved,_=parse(ls);p.write_text(''.join(resolved))
p=S/'riscv/iris_timing_adapter.h';text=p.read_text();first=text.index('<<<<<<< ');last=text.rindex('>>>>>>> ');last=text.index('\n',last)+1
# Only the single same-line profile declaration conflicts. Union all explicit
# false defaults into the wake declaration; do not import lateALU.
wake=(R/'pipeline/riscv-isa-sim-C12-async-RRD-wake-v2/riscv/iris_timing_adapter.h').read_text();line=next(x for x in wake.splitlines(True)if 'bool keep_history='in x)
for flag in ('empirical_pending_base_retry','empirical_fadd_eg','empirical_opu_fence'):
 assert flag+'='not in line;line=line.replace(';std::string empirical_identity;',','+flag+'=false;std::string empirical_identity;')
text=text[:first]+line+text[last:];p.write_text(text)
for p in S.joinpath('riscv').glob('*'):
 if p.is_file():assert b'<<<<<<< 'not in p.read_bytes(),str(p)
r=dict(schema='iris.C12_composite_merge_resolution.v1',**{'pass':True},native_source=str(S),resolutions=['profile flags: explicit union of wake/pending-base/FADD/FENCE, all defaultOFF','parser and validation: union of independent additions','constructor: retain diagnostics plus FADD and FENCE state initialization'],late_ALU_included=False,source_timing_behavior_changed_by_resolution=False,hardware_contacted=False)
(O/'resolution.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
