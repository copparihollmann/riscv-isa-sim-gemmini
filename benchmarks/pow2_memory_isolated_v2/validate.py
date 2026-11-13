"""Independent pointer, count, role, typed-record and ordering oracle."""
import json,hashlib
from pathlib import Path
SIZES=tuple(2**k for k in range(10,23));RESERVED=(4096,65536,524288)
def need(ok,why):
 if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical():
 rows=[]
 for t in range(3):
  for size in SIZES:
   for h in range(3):
    stem='memory.pow2.isolated.%d.hart%d.trial%d'%(size,h,t);n=size//64;loads=max(1024,n);expected=0x90000000+h*0x02000000+64*((17*t+7*h)%n)
    for phase,name in enumerate(('cold','steady')):rows.append(dict(case_id=stem+'.'+name,parent_case_id=stem,suite='pow2_isolated_memory',region='chase',trial_id=t,pass_index=phase,hart=h,footprint_bytes=size,body_loads=loads,whole_laps=loads//n,requested_bytes=loads*8,checksum=expected,expected_checksum=expected,eviction_checksum=131072*(0x1001+h),eviction_loads=131072,msip_before=0,msip_after=0,**{'pass':True}))
 return rows
def validate_corpus(c):
 need(c['schema']=='iris.pow2_isolated_memory_corpus.v2'and c['split_id']=='iris-pow2-isolated-memory-v2','New exact corpus role')
 need(c['frozen_split_sha256']==sha(Path(__file__).resolve().parents[2]/'calibration/pow2-memory-isolated-v2/split.json'),'Frozen grouped split')
 need(c['reserved_sizes']==list(RESERVED)and c['reserved_timing_labels_root_only']is True and c['fitting_only']is True and c['global_heldout']is False and c['negative_skip_kernel']is False and c['source_image_association_verified']is False and c['physical_DRAM_miss_or_traffic_measured']is False and c['buffered_all_output']is True,'No timing/reference/source scope transfer')
 for k,v in [('trials',3),('passes',2),('physical_harts',3),('required_regions',234),('min_dependent_loads',1024),('eviction_bytes',8388608),('eviction_loads',131072),('record_bytes',128)]:need(type(c.get(k))is int and c[k]==v,'Typed corpus '+k)
 need(len(c['cases'])==117,'All117cohorts')
 for i,expected in enumerate(canonical()[::2]):
  r=c['cases'][i];h=expected['hart'];n=expected['footprint_bytes']//64
  for k,v in dict(case_id=expected['parent_case_id'],id=expected['parent_case_id'],nodes=n,loads=expected['body_loads'],whole_laps=expected['whole_laps'],footprint_bytes=expected['footprint_bytes'],hart=h,active_harts=[h],mask=1<<h,trial_id=expected['trial_id'],base=0x90000000+h*0x02000000,expected_checksum=expected['checksum'],internal_split='reserved_holdout'if expected['footprint_bytes']in RESERVED else'train',split_group_id='footprint-bytes:'+str(expected['footprint_bytes'])).items():need(type(r.get(k))is type(v)and r[k]==v,'Canonical cohort '+k)
 return True
def validate(text,c):
 validate_corpus(c);need('IRIS_FATAL'not in text,'No guestfatal');rows=[];done=[]
 for l in text.splitlines():
  if l.startswith('IRIS_REGION '):rows.append(json.loads(l.split(' ',1)[1]))
  elif l.startswith('IRIS_BATCH_DONE '):done.append(json.loads(l.split(' ',1)[1]))
 need(len(rows)==234,'All234records');need(done==[dict(failed=0,cases=117,regions=234,trials=3)]and all(type(x)is int for x in done[0].values()),'Actualnormalallcorrectcompletion')
 prior={}
 for r,w in zip(rows,canonical()):
  need(all(type(r.get(k))is type(v)and r[k]==v for k,v in w.items()),'Typedrole/count/pointer/conditioninggolden')
  need(all(type(r.get(k))is int and 0<=r[k]<2**64 for k in('start_cycle','end_cycle','instret_delta','mtime_before','mtime_after')),'Typedcounters')
  need(r['end_cycle']>r['start_cycle']>=prior.get(r['hart'],0)and r['instret_delta']>=3*w['body_loads']+1 and r['mtime_after']>=r['mtime_before'],'Ordered genuine counter/CLINTwindows')
  prior[r['hart']]=r['end_cycle']
  for k,v in dict(mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,mtime_quantization_error_bound_core_cycles=1000,mtime_scope='encloses_CSR_ROI_with_sampling_overhead').items():need(type(r.get(k))is type(v)and r[k]==v,'ActualCLINTscope')
 return dict(cases=117,regions=234,trials=3,normal_completion=True,body_loads=sum(r['body_loads']for r in rows),CLINT_windows=234,reserved_regions=54,train_regions=180,global_accuracy_2percent_claimed=False,physical_misses_measured=False)
