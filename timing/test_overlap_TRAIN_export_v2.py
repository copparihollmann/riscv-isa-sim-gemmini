#!/usr/bin/env python3
"""TRAIN-only join test; reserved reference rows are synthetic, never observed."""
from pathlib import Path
import copy,json,sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'timing'));import compare_overlap_completion_v3 as v

def main():
 o=R/'build/overlap-comparison-TRAIN-qualification-v2';o.mkdir(exist_ok=False);train=R/'build/overlap-HARDWARE-TRAIN-v1';receipt=v.load(train/'report.json');v.need(receipt['schema']=='iris.source_overlap_TRAIN_only_export.v1'and receipt['status']=='passed'and receipt['regions']==114 and receipt['reserved_timing_labels_excluded']is True and receipt['absolute_timestamps_removed_to_hide_reserved_gaps']is True and receipt['regions_sha256']==v.sha(train/'regions.jsonl'),'Exact protected TRAIN-only packet')
 actual=[json.loads(s)for s in(train/'regions.jsonl').read_text().splitlines()];corpus=v.load(R/'build/overlap-completion-console-guest-v1/corpus.json');expected={c['id']for c in corpus['cases']if c['edge']!=(64 if c['hart']==2 else 16)};ids=[int(x['case_id'].rsplit('.',1)[1])for x in actual];v.need(len(actual)==len(set(ids))==114 and set(ids)==expected,'ExactTRAIN rows, no reserved shapes')
 for row in actual:
  c=corpus['cases'][int(row['case_id'].rsplit('.',1)[1])];v.need(row['internal_split']=='train'and row['semantic_source_case_id']==c['case_id'],'Frozen semantic join')
  v.need(not any(k in row for k in v.HW_FIELDS),'No absolute timestamps/reserved-gap leak')
  for key in ['hart','edge','count','rotate','fp8','trial']:v.need(v.integer(row[key])==c[key],'Typed canonical metadata')
  v.need(v.integer(row['checksum'])==sum(v.golden(c))and row['independent_checksum_validated']is True and v.integer(row['failed_elements'])==0,'Independent actualTRAIN numeric qualification')
  durations=[v.integer(row[k])for k in ['issue_window_cycles','fence_window_cycles','dependent_readout_window_cycles']];v.need(all(x>0 for x in durations)and sum(durations)==v.integer(row['cycles']),'Exact three-window partition of total')
 rows,scope,rr=v.native(R/'build/overlap-completion-console-selected7bd5-baseline-v1',corpus,R/'build/overlap-completion-console-guest-v1/overlap.elf');reference=[];byid=dict(zip(ids,actual))
 for i,(s,c)in enumerate(zip(rows,corpus['cases'])):
  live=byid.get(i);d=[live[k]for k in['issue_window_cycles','fence_window_cycles','dependent_readout_window_cycles']]if live else[s['issue_end']-s['start']+1,s['fence_end']-s['issue_end']+2,s['drain_end']-s['fence_end']+3];b=100+i*100000000
  if live:
   row=dict(live) # Preserve EVERY real analyzer-derived field; do not add pass.
   row.update(start_cycle=b,issue_end_cycle=b+d[0],fence_end_cycle=b+d[0]+d[1],end_cycle=b+sum(d))
   assert set(row)-set(live)==set(v.HW_FIELDS)and all(row[k]==value for k,value in live.items())and 'pass'not in row
  else:
   row=dict(case_id='overlap.v1.case.'+str(i),hart=c['hart'],fp8=c['fp8'],edge=c['edge'],count=c['count'],rotate=c['rotate'],trial=c['trial'],internal_split='reserved_validation',independent_checksum_validated=True,instret_scope='total_only',region='total',failed_elements=0,checksum=sum(v.golden(c)),start_cycle=b,issue_end_cycle=b+d[0],fence_end_cycle=b+d[0]+d[1],end_cycle=b+sum(d),instret_delta=s['instret'])
  reference.append(row)
 compared=v.compare_rows(rows,reference,corpus);v.need(sum(x['internal_split']=='train'for x in compared)==114,'All actualTRAIN rows exercised full comparison arithmetic');bad=copy.deepcopy(reference);j=next(i for i in ids);bad[j]['count']+=1
 try:v.compare_rows(rows,bad,corpus)
 except ValueError:rejected=True
 else:raise ValueError('CorruptactualTRAINcase admitted')
 r=dict(schema='iris.overlap_TRAIN_join_qualification.v1',pass_=True,actual_TRAIN_rows=114,actual_TRAIN_fields_preserved_verbatim=True,actual_TRAIN_added_fields=list(v.HW_FIELDS),actual_TRAIN_absolute_origins_synthetic=True,artificial_pass_flags_added=False,prior_v1_scope_correction='Previous test rebuilt rows using synthetic template and added pass=True; it tested actualduration arithmetic but did not qualify actualreference schema. Prior report/tool preserved.',actual_TRAIN_subwindow_and_total_errors_evaluated=456,reserved_reference_rows=54,reserved_reference_values='synthetic only, not persisted as hardware',actual_reserved_reference_labels_opened=False,mixed_statistics_reported_as_hardware=False,corrupt_actual_TRAIN_metadata_rejected=rejected,model_native_and_CSR_revalidated=True,parameters_refitted=False,hardware_contacted=False,input_sha256={str(p):v.sha(p)for p in[Path(__file__).resolve(),R/'timing/compare_overlap_completion_v3.py',train/'report.json',train/'regions.jsonl',R/'build/overlap-completion-console-selected7bd5-baseline-v1/run.json']});r['pass']=r.pop('pass_');(o/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(pass_=True,TRAIN_rows=114,report_sha256=v.sha(o/'report.json'))))
if __name__=='__main__':main()
