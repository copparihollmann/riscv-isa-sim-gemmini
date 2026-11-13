"""Exact source/compiled case/phase admission for the buffered RVV packet."""
import sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'benchmarks/rvv_identify_tk_v3'
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
ELF='ee233bd28a95c6af2961d857a13cde4640619bfe0f3bafdb5a4aae77a3c68fa2'
ROLE='rvv_identify_TK_single_hart_train_reserved_v2'
inspect=proof.inspect;flatten=proof.flatten;inspect_clint_window=proof.clint_proof
def validator():return val
