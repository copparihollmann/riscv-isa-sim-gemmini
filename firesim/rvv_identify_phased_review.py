"""Exact source/compiled case/phase admission for the buffered RVV packet."""
import sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'benchmarks/rvv_identify_phased_v1'
def _load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
_saved={k:sys.modules.get(k)for k in('cases','build','validate','protocol')}
try:
 sys.modules['cases']=_load('_rvv_tk_cases',BENCH/'cases.py')
 sys.modules['build']=_load('_rvv_tk_build',BENCH/'build.py')
 val=_load('_rvv_tk_validate',BENCH/'validate.py');sys.modules['validate']=val
 sys.modules['protocol']=_load('_rvv_phase_protocol',BENCH/'protocol.py')
 proof=_load('_rvv_tk_qualification',BENCH/'qualify.py')
finally:
 for _name,_module in _saved.items():
  if _module is None:sys.modules.pop(_name,None)
  else:sys.modules[_name]=_module
ELF='9a8f09be93998c6669c0d83563500df889b7ce6ab54f8ecb32aebdc1469ee9c6'
ROLE='rvv_identify_1908_hart_grouped_two_wakeups_v1'
inspect=proof.inspect;flatten=proof.flatten;inspect_clint_window=proof.clint_proof
def validator():return val

validate_sections=val.validate_sections
