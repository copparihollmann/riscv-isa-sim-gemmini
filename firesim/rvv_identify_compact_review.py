"""Exact source/compiled case/phase admission for the buffered RVV packet."""
import sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'benchmarks/rvv_identify_compact_v1'
def _load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
_saved={k:sys.modules.get(k)for k in('cases','build','validate','protocol','codec')}
try:
 sys.modules['cases']=_load('_rvv_tk_cases',BENCH/'cases.py')
 sys.modules['build']=_load('_rvv_tk_build',BENCH/'build.py')
 sys.modules['codec']=_load('_rvv_compact_codec',BENCH/'codec.py')
 val=_load('_rvv_tk_validate',BENCH/'validate.py');sys.modules['validate']=val
 sys.modules['protocol']=_load('_rvv_phase_protocol',BENCH/'protocol.py')
 proof=_load('_rvv_tk_qualification',BENCH/'qualify.py')
finally:
 for _name,_module in _saved.items():
  if _module is None:sys.modules.pop(_name,None)
  else:sys.modules[_name]=_module
ELF='99a2decd1846c41b16e1133f5e5d99cc9546e52f25670f7a49e6894e5923464c'
ROLE='rvv_identify_1908_compact_two_wakeups_v1'
inspect=proof.inspect;flatten=proof.flatten;inspect_clint_window=proof.clint_proof
def validator():return val

validate_sections=val.validate_sections

expand=val.expand
