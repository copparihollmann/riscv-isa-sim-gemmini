"""Exact source/compiled case/phase admission for the buffered RVV packet."""
import sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'benchmarks/rvv_identify_1908_v1'
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
ELF='a20cbb0eeac78f85c69f4cdba592e17308d077f2f74f3d77f51857bc97724049'
ROLE='rvv_identify_1908_hart2_LSU256_unqualified_v1'
inspect=proof.inspect;flatten=proof.flatten;inspect_clint_window=proof.clint_proof
def validator():return val
