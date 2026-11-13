"""Exact source/compiled case/phase admission for the buffered RVV packet."""
import sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'benchmarks/rvv_identify_diag_v1'
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
ELF='778c83844116bf64afbf61ca020a1b72c05c5cb75049b5dbe1f0ec8d8e6a8b8d'
ROLE='rvv_identify_TK_diagnostic_progress_v1'
inspect=proof.inspect;flatten=proof.flatten;inspect_clint_window=proof.clint_proof
def validator():return val


def progress_prefix(text,corpus):
 import json
 seen=set();boot=set();active={};last=None;markers=0
 for line in text.splitlines():
  if not line.startswith('IRIS_RVV_DIAG '):continue
  r=json.loads(line.split(' ',1)[1])
  if set(r)!={'hart','case_index','stage'}or type(r['hart'])is not int or type(r['case_index'])is not int or type(r['stage'])is not str:raise ValueError('Typed diagnostic progress')
  h,i,stage=r['hart'],r['case_index'],r['stage'];key=(h,i,stage)
  if h not in(0,1,2)or key in seen:raise ValueError('Duplicate or wrong diagnostic hart')
  seen.add(key);markers+=1;last=r
  if stage=='BOOT':
   if i!=1920:raise ValueError('Diagnostic BOOT sentinel')
   boot.add(h);continue
  if h not in boot or not 0<=i<1920:raise ValueError('Diagnostic before own BOOT or wrong case')
  c=corpus['cases'][i]
  if stage=='WAIT':
   if i>=8 or h==c['hart']:raise ValueError('Diagnostic inactive WAIT role')
   continue
  if h!=c['hart']:raise ValueError('Diagnostic active role')
  seq=active.setdefault(i,[]);seq.append(stage);want=['START','ACK','SETUP','KERNEL_DRAIN','CHECK','DONE']if i<8 else ['START','DONE']
  if seq!=want[:len(seq)]:raise ValueError('Diagnostic stage prefix')
 return dict(schema='iris.rvv_identify_diagnostic_progress.v1',markers=markers,boot_harts=sorted(boot),last_marker=last,active_cases_started=len(active),active_cases_done=sum(v[-1]=='DONE'for v in active.values()),incomplete_cases=[dict(case_index=i,hart=corpus['cases'][i]['hart'],case_id=corpus['cases'][i]['case_id'],last_stage=v[-1])for i,v in active.items()if v[-1]!='DONE'],calibration_usable=False,proof_scope='ObservedserializedUARTprogressonly;notphysicalcauseorcalibration')
