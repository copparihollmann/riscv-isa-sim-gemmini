#!/usr/bin/env python3
"""Additive receipt/summary boundary controls on actual normal software output."""
import copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from iris_model import source_event_profile_v2 as P

def main():
 out=ROOT/'build/source-event-profiler-v2-admission-controls-v1';out.mkdir();run=ROOT/'build/source-profile35a-live-frontend-root-v1/execution-v1';r=P.load(run/'run.json');elf=Path(r['argv'][-1]);fixture=Path(next(a.split('=',1)[1]for a in r['argv']if a.startswith('--iris-timing-fixture=')));rom=Path(next(a.split('=',1)[1]for a in r['argv']if a.startswith('--iris-bootrom=')));nm=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm');raw_events=run/'source-events.jsonl';features=run/'features.jsonl';console=run/'stdout';summary=run/'native-summary.json';ids={str(p):P.sha(p)for p in(Path(__file__).resolve(),Path(P.__file__).resolve(),run/'run.json',raw_events,features,console,summary,elf,fixture,rom,nm)}
 def render(name,s=summary,receipt=run/'run.json'):
  return P.profile(raw_events,features,console,s,elf,rom,out/name,nm,None,'iris-json',True,fixture,receipt)
 normal=render('baseline');findings=[]
 inflated=P.load(summary);inflated['cycles']*=2;copy_summary=out/'unbound-inflated-summary.json';copy_summary.write_text(json.dumps(inflated)+'\n');need_not_bound=str(copy_summary.resolve())not in r['output_sha256'];assert need_not_bound
 try:
  accepted=render('unbound-summary-accepted',copy_summary)
 except(ValueError,KeyError,TypeError)as e:
  summary_result=dict(refused=True,reason=str(e))
 else:
  assert accepted['whole_program_model_cycles']==2*normal['whole_program_model_cycles']
  assert all(abs(a['fraction_of_conditional_source_ceiling']*2-b['fraction_of_conditional_source_ceiling'])<1e-14 for a,b in zip(accepted['whole_program'],normal['whole_program']))
  summary_result=dict(refused=False,unbound_summary_admitted=True,actual_cycles=normal['whole_program_model_cycles'],reported_cycles=accepted['whole_program_model_cycles'],whole_program_conditional_fractions_halved=True,unchanged_event_feature_console_and_execution_receipt=True)
  findings.append(dict(id='offline-native-summary-not-bound-to-execution',severity='admission metadata/rate integrity',current_frozen_profile_numbers_affected=False,frontend_uses_correct_own_summary=True,evidence=summary_result))
 inconsistent=copy.deepcopy(r);inconsistent.update(exit_status=1,timed_out=True,status='failed_guest_exit');bad_receipt=out/'contradictory-execution.json';bad_receipt.write_text(json.dumps(inconsistent)+'\n')
 try:
  accepted=render('contradictory-normal-claim',summary,bad_receipt)
 except(ValueError,KeyError,TypeError)as e:
  receipt_result=dict(refused=True,reason=str(e))
 else:
  assert accepted['normal_execution_complete']is True
  receipt_result=dict(refused=False,normal_execution_complete=True,receipt_exit_status=1,receipt_timed_out=True,receipt_pass_flag_unchanged=True)
  findings.append(dict(id='contradictory-normal-completion-fields-admitted',severity='receipt metadata consistency',current_frozen_normal_receipts_affected=False,frontend_generated_normal_receipts_are_consistent=True,evidence=receipt_result))
 # Independent negative source-work controls on a small complete actual-owner subset.
 source=ROOT/'build/source-event-profile-v2-controls-v7/complete-real-owners.jsonl';events=[json.loads(x)for x in source.read_text().splitlines()];code=P.Instructions(ROOT/'build/rvv-compute-asm-v5/guest.elf',rom);checks=[]
 def reject(name,edit):
  rows=copy.deepcopy(events);edit(rows);p=out/(name+'.jsonl');p.write_text(''.join(json.dumps(x)+'\n'for x in rows))
  try:P.parse_journal(p,code,[1,1,1])
  except(ValueError,KeyError,TypeError)as e:checks.append(dict(name=name,refused=True,reason=str(e)));return
  raise ValueError('Source work corruption admitted '+name)
 def idx(rows,event):return next(i for i,e in enumerate(rows)if e['event']==event)
 reject('duplicate-EG-credit',lambda e:e.append(copy.deepcopy(e[idx(e,'fadd_EG_physical_write')])))
 reject('missing-actual-K-write',lambda e:e.pop(idx(e,'opu_K_write_owner')))
 reject('reserved-MACs-not-completion',lambda e:e.pop(idx(e,'opu_K_completion')))
 reject('final-projection-missing',lambda e:e.pop(idx(e,'opu_entry_publish')))
 reject('wrong-VADD-source-valid-depth',lambda e:e[idx(e,'vadd_EG_physical_write')].update(cycle=e[idx(e,'vadd_EG_physical_write')]['cycle']+1))
 reject('intermediate-K-projects-final-MRF',lambda e:next(x for x in e if x['event']=='opu_K_write_owner'and not x['last_k']).update(projected_MRF_published=True))
 assert all(P.sha(k)==v for k,v in ids.items()),'Frozen consumer or actual inputs changed'
 report=dict(schema='iris.independent_source_event_profiler_v2_admission_controls.v1',**{'pass':True},meaning='Controls completed; findings are explicitly recorded, not a blanket admission PASS',actual_frozen_demonstration_numbers_changed=False,normal_summary_control=summary_result,contradictory_receipt_control=receipt_result,source_work_negative_controls=checks,findings=findings,no_native_provider_consumer_edits_or_hardware_or_protected_labels=True,input_sha256=ids)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(controls_completed=True,findings=len(findings),source_refusals=len(checks),report_sha256=P.sha(out/'report.json'))))
if __name__=='__main__':main()
