"""Exact source/compiled case/phase admission for the buffered RVV packet."""
import sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'benchmarks/rvv_hart2_only_v1'
def _load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
_saved={k:sys.modules.get(k)for k in('cases','build','validate')}
try:
 sys.modules['cases']=_load('_rvv_tk_cases',BENCH/'cases.py')
 sys.modules['build']=_load('_rvv_tk_build',BENCH/'build.py')
 val=_load('_rvv_tk_validate',BENCH/'validate.py');sys.modules['validate']=val
 proof=_load('_rvv_tk_qualification',BENCH/'qualify.py')
finally:
 for _name,_module in _saved.items():
  if _module is None:sys.modules.pop(_name,None)
  else:sys.modules[_name]=_module
ELF='52ab5cf8515989d2dfddf79c89e7c4802abf6344f2d21c41b9c9cfa46cfad8c3'
ROLE='rvv_hart2_only_588_scalar_JSON_v1'
inspect=proof.inspect;flatten=proof.flatten;inspect_clint_window=proof.clint_proof
def validator():return val

scalar_wire_proof=proof.scalar_wire_proof

def validate_sections(text,c,partial=False):
 import json
 want=val.canonical(c);rows=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_REGION ')]
 if len(rows)>len(want):raise ValueError('Excess observed prefix')
 for r,w in zip(rows,want):
  if not all(type(r.get(k))is type(v)and r[k]==v for k,v in w.items()):raise ValueError('Observed prefix role/golden mismatch')
 if not partial:val.validate(text,c)
 return dict(regions=len(rows),partial_scope=partial,normal_completion_claimed=not partial)
def expand(text,c,partial=False):return text
