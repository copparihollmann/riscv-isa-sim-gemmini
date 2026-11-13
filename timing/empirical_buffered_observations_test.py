#!/usr/bin/env python3
"""Synthetic validation controls only: creates no fitting observations/labels."""
import copy,json,pathlib
import empirical_buffered_observations as m
r=m.ROOT;corpus=json.load(open(r/'build/campaign-buffered-fit-v1/corpus.json'));split=json.load(open(r/'calibration/empirical-buffered-v1/split.json'))
raw=[]
for c in corpus['cases']:
 for h in range(3):
  if c['mask']&(1<<h):
   raw.append({k:c[k] for k in ('case_id','parent_case_id','semantic_parent_case_id','suite','trial_id','mask')}|{'hart':h,'start_cycle':100,'end_cycle':200,'cycles':100,'instret_delta':10,'checksum':c['expected_checksums'][h],'expected_checksum':c['expected_checksums'][h]})
rows=m.normalize_rows(raw,corpus,split);assert len(rows)==4050;neg=[]
for control in ('boolean_hart','float_cycle','bad_checksum','wrong_semantic','duplicate','missing','wrong_span','inactive_hart'):
 bad=copy.deepcopy(raw)
 if control=='boolean_hart':bad[0]['hart']=False
 elif control=='float_cycle':bad[0]['cycles']=100.0
 elif control=='bad_checksum':bad[0]['checksum']+=1
 elif control=='wrong_semantic':bad[0]['semantic_parent_case_id']='wrong'
 elif control=='duplicate':bad.append(copy.deepcopy(bad[0]))
 elif control=='missing':bad.pop()
 elif control=='wrong_span':bad[0]['cycles']=101
 else:bad[0]['hart']=3
 try:m.normalize_rows(bad,corpus,split)
 except ValueError:neg.append(control)
 else:raise ValueError('Negative control accepted '+control)
out=r/'build/empirical-buffered-observation-controls-v1';out.mkdir(exist_ok=False);report={'schema':'iris.empirical_buffered_normalizer_controls.v1','pass':True,'synthetic_rows':4050,'synthetic_values_are_reference_timings':False,'fitting_data_emitted':False,'negative_controls_rejected':neg,'global_heldout_timings_consumed':False,'input_sha256':{str(p.relative_to(r)):m.sha(p) for p in [pathlib.Path(__file__).resolve(),r/'timing/empirical_buffered_observations.py',r/'build/campaign-buffered-fit-v1/corpus.json',r/'calibration/empirical-buffered-v1/split.json']}};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
