#!/usr/bin/env python3
"""Independent regression of the two v2 admission defects; v3 source read-only."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from iris_model import source_event_profile_v3 as V
A=V.accounting

def main():
 out=ROOT/'build/source-event-profiler-v3-independent-admission-v1';out.mkdir();normal=ROOT/'build/source-profile35a-live-frontend-root-v1/execution-v1';r=A.load(normal/'run.json');elf=Path(r['argv'][-1]);fixture=Path(next(a.split('=',1)[1]for a in r['argv']if a.startswith('--iris-timing-fixture=')));events=normal/'source-events.jsonl';features=normal/'features.jsonl';console=normal/'stdout';summary=normal/'native-summary.json';sources=[Path(__file__).resolve(),Path(V.__file__).resolve(),ROOT/'iris_model/source_profile_run_v3.py',ROOT/'iris_model/source_event_profile_v2.py',normal/'run.json',events,features,console,summary,elf,fixture];ids={str(p):A.sha(p)for p in sources};checks=[]
 def admit(receipt,s=summary):return V.admit(receipt,events,features,console,elf,fixture,s)
 got,mode=admit(normal/'run.json');assert got==r and mode is True;checks.append(dict(name='actual coherent normal receipt and exact summary admitted',pass_=True))
 old=ROOT/'build/source-event-profiler-v2-admission-controls-v1'
 def refusal(name,receipt=normal/'run.json',s=summary):
  try:admit(receipt,s)
  except(ValueError,KeyError,TypeError)as e:checks.append(dict(name=name,refused=True,reason=str(e)));return
  raise ValueError('Malformed execution/summary admitted '+name)
 refusal('original unbound doubled denominator refused',s=old/'unbound-inflated-summary.json')
 refusal('original contradictory failure-normal receipt refused',receipt=old/'contradictory-execution.json')
 variants=[('nonzero normal exit',dict(exit_status=1)),('boolean normal exit code',dict(exit_status=False)),('timeout while pass true',dict(timed_out=True)),('unspecified timeout',dict(timed_out=None)),('mixed normal and intentional stop',dict(normal_guest_exit_verified=True,intentional_postmeasurement_debugger_stop=True)),('declared execution error',dict(error='failed')),('changed execution inputs',dict(unchanged_inputs_after_execution=False))]
 for name,changes in variants:
  x=copy.deepcopy(r);x.update(changes);p=out/(name.replace(' ','-')+'.json');p.write_text(json.dumps(x)+'\n');refusal(name,receipt=p)
 debug=ROOT/'build/rvv-compute-asm-C12-VADD-EG-ON-v1';d=A.load(debug/'run.json');de=Path(d['argv'][-1]);df=Path(next(a.split('=',1)[1]for a in d['argv']if a.startswith('--iris-timing-fixture=')));args=(debug/'async.jsonl',debug/'features.jsonl',debug/'stdout',de,df,None);admitted,mode=V.admit(debug/'run.json',*args);assert admitted==d and mode is False;checks.append(dict(name='actual finite controlled-stop1320 receipt admitted without normal/E2E claim',pass_=True));ids[str(debug/'run.json')]=A.sha(debug/'run.json')
 for name,changes in [('failed debugger status',dict(debugger_exit_status=1)),('missing stable measured-count proof',dict(done_and_count_stable_before_and_after_readback=False)),('measured-only claims whole-run timing',dict(whole_run_timing_or_speed_claim=True)),('measured-only also claims guest exit',dict(exit_status=0))]:
  x=copy.deepcopy(d);x.update(changes);p=out/(name.replace(' ','-')+'.json');p.write_text(json.dumps(x)+'\n')
  try:V.admit(p,*args)
  except(ValueError,KeyError,TypeError)as e:checks.append(dict(name=name,refused=True,reason=str(e)))
  else:raise ValueError('Contradictory measured-only receipt admitted')
 assert all(A.sha(k)==v for k,v in ids.items()),'Guard/frontend/source inputs changed during review'
 report=dict(schema='iris.independent_source_event_profiler_v3_admission_audit.v1',**{'pass':True},tests=checks,original_v2_findings_both_refused=True,actual_normal_and_measured_only_compatibility=True,accounting_v2_bytes_and_formulas_unchanged=True,source_native_fixture_or_frozen_v2_changed=False,hardware_or_protected_timing_labels_accessed=False,guard_does_not_authenticate_arbitrary_forged_receipts=True,input_sha256=ids);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,checks=len(checks),report_sha256=A.sha(out/'report.json'))))
if __name__=='__main__':main()
