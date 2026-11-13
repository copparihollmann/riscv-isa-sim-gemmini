#!/usr/bin/env python3
"""Additional immutable typed-field and missing-field controls for buffered v1."""
import copy,hashlib,json,pathlib
import empirical_buffered_review as base
ROOT=base.ROOT

def strict(corpus,canonical,split):
 by={(suite,c['case_id']):c for suite,cs in canonical.items() for c in cs}
 def same_typed(a,b):
  if type(a) is not type(b):return False
  if isinstance(a,list):return len(a)==len(b) and all(same_typed(x,y) for x,y in zip(a,b))
  if isinstance(a,dict):return a.keys()==b.keys() and all(same_typed(a[k],b[k]) for k in a)
  return a==b
 extras={'parent_case_id','semantic_parent_case_id','split','suite','trial_id'}
 for c in corpus['cases']:
  old=by[(c['suite'],c['semantic_parent_case_id'])]
  if set(c)!=set(old)|extras:raise ValueError('Missing or unknown semantic fields')
  if type(c['trial_id']) is not int:raise ValueError('Boolean/noninteger trial')
  for k,v in old.items():
   if k!='case_id' and not same_typed(c[k],v):raise ValueError('Typed semantic field differs '+k)
 return base.audit(corpus,canonical,split)

def main():
 out=ROOT/'build/empirical-buffered-strict-review-v1';out.mkdir(exist_ok=False)
 cpath=ROOT/'build/campaign-buffered-fit-v1/corpus.json';corpus=json.load(cpath.open());splitpath=ROOT/'calibration/empirical-v1/split.json';split=json.load(splitpath.open())
 b=json.load((ROOT/'benchmarks/calibration-corpus.json').open());g=base.module('buffered_strict_golden',ROOT/'benchmarks/golden.py');g.verify(b)
 for c in b['cases']:
  c['mask']={'all':7,'compute':3,'1':1,'4':4}[c['active_hart_mask_expression']];c['expected_checksums']=[g.checksum(c,h) for h in range(3)]
 canonical={'baseline':b['cases'],'distribution':base.module('strict_dist',ROOT/'benchmarks/v2/cases.py').cases(),'memory':base.module('strict_mem',ROOT/'benchmarks/memory_routes/cases.py').cases()}
 _,counts,checks=strict(corpus,canonical,split);neg=[]
 for kind in ('missing_stride','boolean_trial','float_argument','unknown_latency','boolean_checksum'):
  bad=copy.deepcopy(corpus)
  if kind=='missing_stride':del next(c for c in bad['cases'] if c['suite']=='memory')['stride']
  elif kind=='boolean_trial':bad['cases'][0]['trial_id']=False
  elif kind=='float_argument':bad['cases'][0]['argument']=0.0
  elif kind=='unknown_latency':bad['cases'][0]['unverified_latency']=30
  else:bad['cases'][0]['expected_checksums'][0]=False
  try:strict(bad,canonical,split)
  except(ValueError,KeyError):neg.append({'control':kind,'rejected':True})
  else:raise ValueError('Malformed corpus accepted '+kind)
 report={'schema':'iris.empirical_buffered_strict_review.v1','status':'passed','all2208_case_fields_present_typed_and_canonical':True,'region_counts':counts,'additional_negative_controls':neg,'existing_review_unchanged':True,'functional_execution_claimed':False,'global_heldout_timings_consumed':False,'input_sha256':{str(p.relative_to(ROOT)):base.sha(p) for p in [pathlib.Path(__file__).resolve(),ROOT/'timing/empirical_buffered_review.py',cpath,splitpath,ROOT/'calibration/empirical-buffered-v1/review.json']}}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));print('SHA',base.sha(out/'report.json'))
if __name__=='__main__':main()
