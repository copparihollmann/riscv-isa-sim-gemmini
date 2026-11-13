#!/usr/bin/env python3
"""Join actual576 UART regions to modeled CSR observations and FADD feature counts."""
import collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 d=ROOT/'build/pow2-scalar-e8ed-source-FADD-ON-v1';out=ROOT/'build/pow2-scalar-e8ed-source-FADD-qualification-v2';out.mkdir();run=json.loads((d/'run.json').read_text());assert run['pass']is True and run['exit_status']==0 and run['normal_guest_exit_verified']is True and run['timed_out']is False
 for p,h in run['input_sha256'].items():assert sha(p)==h
 c=json.loads((ROOT/'build/pow2-scalar-fit-v1/corpus.json').read_text());rows=[json.loads(s.split(' ',1)[1])for s in(d/'stdout').read_text().splitlines()if s.startswith('IRIS_REGION ')];assert len(rows)==len(c['cases'])==576
 prefixes=[json.loads(s)for s in(d/'features.jsonl').read_text().splitlines()];index=collections.defaultdict(list)
 for x in prefixes:
  if x['csr']==0xb00:index[x['hart'],x['value']].append(x)
 joins=[]
 for spec,row in zip(c['cases'],rows):
  h=spec['hart'];before=index[h,row['start_cycle']];after=index[h,row['end_cycle']];assert len(before)==len(after)==1;before,after=before[0],after[0];expected=0 if spec['kind'].startswith('integer')else spec['n']*(4 if spec['kind'].endswith('independent4')else 1)
  actual={width:after['features'].get('scalar.fadd.fp'+str(width),{}).get('instructions',0)-before['features'].get('scalar.fadd.fp'+str(width),{}).get('instructions',0)for width in(16,32,64)}
  wanted={w:expected if spec['kind'].startswith('fp'+str(w))else 0 for w in(16,32,64)};assert actual==wanted
  assert all(before['scalar_fadd_pending'][k]==after['scalar_fadd_pending'][k]==0 for k in['accepted_live','front_queued'])
  joins.append(dict(case_id=spec['id'],hart=h,kind=spec['kind'],n=spec['n'],trial=spec['trial_id'],model_cycles=row['end_cycle']-row['start_cycle'],instret=row['instret_delta'],FADD_counts=actual,begin_pc=before['pc'],begin_raw=before['raw'],end_pc=after['pc'],end_raw=after['raw']))
 s=json.loads((d/'native-summary.json').read_text());assert'finite-source-HSD'in s['scalar_fadd_scope'];assert s['fast_source_frontend_enabled']in(False,[False,False,False])
 metrics=s['scalar_fadd_metrics'];assert len(metrics)==3 and all(x['accepted']==x['published']==183600 and not x['pending']for x in metrics)and[x['peak']for x in metrics]==[4,4,3]
 (out/'model-regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in joins));paths=[Path(__file__).resolve(),d/'run.json',d/'native-summary.json',d/'features.jsonl',d/'stdout',d/'stderr',ROOT/'build/pow2-scalar-fit-v1/corpus.json',ROOT/'build/scalar-FADD-e8ed-activation-QA-closure-v1/report.json'];report=dict(schema='iris.pow2_scalar_FADD_exact_native_qualification.v1',status='passed',all_regions=576,numerical_words=2304,actual_cycle_CSR_endpoint_joins=1152,per_region_FADD_family_counts_verified=True,accepted_and_published_FADDs=550800,per_hart_FADD_metrics=metrics,actual_scalar_frontend_enabled=False,program_visible_counters_from_model=True,all_rois_have_drained_FADDs_at_both_CSR_boundaries=True,source_depths=[4,4,3],parameters_changed=False,native_source_changed=False,hardware_contacted=False,reserved_hardware_timing_labels_consumed=False,full_2percent_claimed=False,whole_kernel_timing_qualified=False,host_seconds=run['host_seconds'],simulated_retired_instructions=s['retired_instructions'],simulated_MIPS_including_UART_polling=sum(s['retired_instructions'])/run['host_seconds']/1e6,source_image_association_verified=False,input_sha256={str(p):sha(p)for p in paths},model_regions_sha256=sha(out/'model-regions.jsonl'));(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='passed',report_sha256=sha(out/'report.json'),FADDs=550800)))
if __name__=='__main__':main()
