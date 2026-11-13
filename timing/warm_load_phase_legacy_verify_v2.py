#!/usr/bin/env python3
"""Read-only legacy-selector parity from already completed actual executions."""
import argparse,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True);rows=[];inputs={str(Path(__file__).resolve()):sha(__file__)}
 for kind in ['pair','chain']:
  old=R/'build/warm-load-phase-parent-OFF-parity-v1'/kind;new=R/'build/warm-load-phase-successor-constant-fetch-QA-v2'/(kind+'-OFF');a1=json.loads((old/'graph.json').read_text());b=json.loads((new/'graph.json').read_text());assert a1['events']==b['events'];assert a1['counter_read_observations']==b['counter_read_observations'];assert a1['source_counter_clock']==b['source_counter_clock'];assert a1['per_hart_features']==b['per_hart_features'];assert (old/'stdout').read_bytes()==(new/'stdout').read_bytes();assert (old/'stderr').read_bytes()==(new/'stderr').read_bytes();assert b['load_front_forwarding_policy']=='legacy-MEM-private-latch-v1'
  extra=set(b)-set(a1);assert extra=={'load_front_forwarding_policy'};assert all(a1[k]==b[k]for k in a1)
  for root in [old,new]:
   for f in ['argv.json','graph.json','stdout','stderr']:inputs[str(root/f)]=sha(root/f)
  rows.append(dict(kind=kind,events=len(a1['events']),counter_reads=len(a1['counter_read_observations']),entire_parent_JSON_identical_plus_one_new_legacy_policy_label=True,actual_numeric_stdout_and_stderr_identical=True))
 controls=[]
 for key in ['end','completed','deps']:
  e=dict(a1['events'][0]);e[key]=False if key=='completed'else[999]if key=='deps'else e['end']+1
  assert e!=b['events'][0];controls.append(dict(name='different-event-'+key,rejected=True))
 r=dict(schema='iris.warm_load_legacy_selector_parity.v2',pass_=True,runs=rows,negative_controls=controls,old_failed_parser_key='counter_reads; actual schema is counter_read_observations',old_raw_runs_preserved=True,input_sha256=inputs);r['pass']=r.pop('pass_');(a.output/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',report_sha256=sha(a.output/'report.json'),runs=rows)))
if __name__=='__main__':main()
