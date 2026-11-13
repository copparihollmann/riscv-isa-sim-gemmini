"""New protected validation repeats, public geometry only; no timing labels."""
import copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'build/rvv-compute-asm-v5/corpus.json'
def generate():
 out=copy.deepcopy(json.loads(PARENT.read_text())['cases'])
 for case in out:
  old_id=case['case_id'];case['n']=({1:3,4:12,16:48,64:192}if case['kind']=='rowmove'else{16:96,64:384})[case['n']]
  stem=f"rvv.compute.heldout2.asm.v1.{case['kind']}.e{case['sew']}.m{case['lmul']}.mode{case['mode']}.n{case['n']}.b{case['bytes']}"
  case['semantic_parent_case_id']=stem;case['parent_case_id']=stem+f".hart{case['hart']}";case['case_id']=case['parent_case_id']+f".trial{case['trial_id']}"
  case['internal_split']='reserved_holdout';case['validation_role']='protected_validation_only';case['source_case_id']=old_id;case.pop('expected_checksum',None)
 return out
def golden(case):
 from validate import checksum
 return checksum(case)
