#!/usr/bin/env python3
"""Cross-check retained operation goldens with Merlin's public integer epilogue."""
import hashlib,json,struct
from pathlib import Path
from merlin.runtime.tensor import Tensor
import merlin.runtime.tensor as reference
ROOT=Path(__file__).resolve().parents[1]
count=0;receipts=[]
for op in ['gemm','conv2d']:
 for workers in [1,2]:
  root=ROOT/f'build/zephyr-mlir-final/{op}-h{workers}'
  receipt=json.loads((root/'results.json').read_text())
  if not receipt['pass'] or not receipt['real_merlin_mlir_executed']:raise ValueError('unqualified operation run')
  cases=json.loads((root/'generated/golden.json').read_text())
  for case in cases:
   raw=case['accumulator_u32'];signed=[v-(1<<32) if v&(1<<31) else v for v in raw]
   expected=Tensor((64,64),signed,'i32').requant(10).to_i8().data
   words=[struct.unpack('<I',struct.pack('<f',x))[0] for x in expected]
   if words!=case['w8a8_f32_words']:raise ValueError('public Merlin integer epilogue differs from executed golden')
   count+=len(words)
  receipts.append({'path':str(root/'results.json'),'sha256':hashlib.sha256((root/'results.json').read_bytes()).hexdigest()})
proof={'schema':'iris.merlin_epilogue_crosscheck.v1','pass':True,'golden_values':count,'executed_image_values':count*2,
 'policy':'Merlin Tensor.requant(shift=10).to_i8(): integer half-up arithmetic shift then signed8 saturation; not float acc_scale/RNE',
 'reference_source':str(Path(reference.__file__)),'reference_source_sha256':hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest(),
 'receipts':receipts,'full_model_qualified':False,'timing_calibrated':False}
(ROOT/'build/merlin-epilogue-crosscheck.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'pass':True,'executed_values':count*2}))
