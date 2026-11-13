#!/usr/bin/env python3
"""Verify all parent/trial/hart identities and independent numerical goldens."""
import argparse,collections,json
from pathlib import Path
def validate(text,corpus):
 if corpus.get('split_id')!='iris-broad-fit-campaign-v1':raise ValueError('Wrong campaign corpus')
 cases={c['case_id']:c for c in corpus['cases']};expected={(c['case_id'],h):c['expected_checksums'][h] for c in cases.values() for h in range(3) if c['mask']&(1<<h)};seen={};done=[];phases=[]
 for line in text.splitlines():
  if line.startswith(('IRIS_FATAL','IRIS_CAMPAIGN_FAILED')):raise ValueError(line)
  if line.startswith('IRIS_BATCH_DONE '):done.append(json.loads(line.split(' ',1)[1]));continue
  if line.startswith('IRIS_CAMPAIGN_PHASE '):phases.append(json.loads(line.split(' ',1)[1]));continue
  if not line.startswith('IRIS_REGION '):continue
  x=json.loads(line.split(' ',1)[1]);key=(x['case_id'],x['hart'])
  if key not in expected or key in seen:raise ValueError('Unexpected/duplicate identity '+repr(key))
  c=cases[x['case_id']]
  for field in ['parent_case_id','trial_id','suite']:
   if x.get(field)!=c[field]:raise ValueError('Wrong parent/trial identity '+repr(key))
  for field in ['start_cycle','end_cycle','instret_delta','checksum','expected_checksum','hart','trial_id']:
   if type(x.get(field))is not int or not 0<=x[field]<(1<<64):raise ValueError('Invalid '+field)
  if x.get('pass')is not True or x['checksum']!=expected[key] or x['expected_checksum']!=expected[key]:raise ValueError('Independent checksum mismatch '+repr(key))
  if x['end_cycle']<=x['start_cycle'] or x['region']!='kernel':raise ValueError('Invalid measured boundary')
  seen[key]=x
 if set(seen)!=set(expected):raise ValueError('Missing '+str(len(set(expected)-set(seen)))+' regions; first '+repr(sorted(set(expected)-set(seen))[:5]))
 expected_done={'failed':0,'cases':len(cases),'regions':len(expected),'trials':corpus['trials']}
 if done!=[expected_done]:raise ValueError('Invalid campaign completion')
 want=[{'suite':s,'trial_id':t,'begin':b} for s in ['baseline','distribution','memory'] for t in range(corpus['trials']) for b in [True,False]]
 if phases!=want:raise ValueError('Missing/duplicate/reordered suite trial phase')
 counts=collections.Counter(c['suite'] for c in cases.values());per_hart=collections.Counter(h for _,h in seen);return {'functional_checks_passed':True,'cases':len(cases),'regions':len(seen),'trials':corpus['trials'],'per_suite_cases':dict(counts),'per_hart_regions':dict(per_hart),'phase_markers':len(phases),'all_parent_trial_hart_ids_unique':True,'all_independent_checksums_passed':True,'timing_certified':False,'calibration_usable':False}
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('console',type=Path);p.add_argument('--corpus',type=Path,required=True);a=p.parse_args();print(json.dumps(validate(a.console.read_text(),json.loads(a.corpus.read_text())),indent=2))
if __name__=='__main__':main()
