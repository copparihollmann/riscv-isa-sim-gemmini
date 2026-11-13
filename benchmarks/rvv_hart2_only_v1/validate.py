"""Independent exact element-value/count/checksum oracle; no timing predictions."""
import json,struct,hashlib
from pathlib import Path

def need(ok,msg):
 if not ok:raise ValueError(msg)
def expected_words(r):
 result=[]
 if r['kind'] in ('matrix_int','matrix_fp8'):
  number=r['n']*r['mode']*(6 if r['kind']=='matrix_int' else 1)
  if r['kind']=='matrix_fp8':number=struct.unpack('<I',struct.pack('<f',float(number)))[0]
  return [number if row<r['vl'] and col<r['vl'] else 0 for row in range(32) for col in range(32)]
 for stream in range(r['streams']):
  for lane in range(r['vl']):
   k=r['kind'];n=r['n']
   if k in('integer','fp'):value=n+int(r['mode']==2 and stream==1)
   elif k=='load':value=lane+3
   elif k=='store':value=3
   elif k=='load_use':value=lane+3+stream
   elif k=='load_independent':value=lane+3 if not stream else n
   elif k=='store_compute':value=3 if not stream else n
   else:value=6
   if k=='fp':value=struct.unpack({16:'<H',32:'<I',64:'<Q'}[r['sew']],struct.pack({16:'<e',32:'<f',64:'<d'}[r['sew']],float(value)))[0]
   result.append(value)
 return result
def checksum(r):
 acc=14695981039346656037
 for value in expected_words(r):acc=(1099511628211*(acc^value))%(2**64)
 return acc
def validate_corpus(c):
 need(c['schema']=='iris.rvv_identify_corpus.v1'and len(c['cases'])==588 and c['skip_kernel']is False and c['all_output_after_measurements']is True and c['all_output_after_own_hart_measurements']is True and c['single_active_hart']is True,'Exactpositive588experiment')
 need(c['fitting_only']is True and c['global_heldout']is False and c['source_image_association_verified']is False and c['reserved_timing_labels_root_only']is True,'No reference/physicalassociation transfer')
 split=Path(__file__).resolve().parents[2]/'calibration/rvv-identify-compact-v1/split.json';need(c['frozen_split_sha256']==hashlib.sha256(split.read_bytes()).hexdigest(),'Frozen grouped reservedsplit')
 seen=set();counts={}
 for r in c['cases']:
  for k in('kind_id','sew','lmul','mode','n','bytes','vl','streams','hart','trial_id'):need(type(r[k])is int,'Typed integergeometry')
  need(r['case_id']not in seen and r['hart']==2 and 0<=r['trial_id']<3,'Unique actualhart/trial');seen.add(r['case_id']);kind=r['kind'];counts[kind]=counts.get(kind,0)+1
  need(kind in('integer','fp','load','store','load_use','load_independent','store_compute','rowmove','matrix_int','matrix_fp8'),'Finitekind')
  need(not(r['hart']==2 and kind in('load','store')and r['bytes']==256),'Explicit unqualified hart2 LSU256B exclusion')
  if kind in('integer','fp'):
   need(r['sew']in((8,16,32,64)if kind=='integer'else(16,32,64))and r['lmul']in(1,2,4,8)and r['mode']in(0,1,2)and r['n']in(16,64)and r['vl']==256*r['lmul']//r['sew']and r['bytes']==32*r['lmul']and r['streams']==(1 if r['mode']==0 else 2),'Independent arithmeticgeometry')
   reserved=r['lmul']==4
  elif kind in('matrix_int','matrix_fp8'):
   need(r['hart']<2 and r['vl']in(16,32)and r['mode']in(2,4)and r['sew']==32 and r['lmul']==r['vl']//8 and r['bytes']==r['vl']*4 and r['streams']==1 and r['n']in(16,64),'MatrixTK/edgegeometry');reserved=r['vl']==16 and r['mode']==4
  elif kind=='rowmove':need(r['hart']<2 and(r['sew'],r['lmul'],r['vl'],r['bytes'],r['streams'])==(32,4,32,128,1)and r['n']in(1,4,16,64),'Finite rowgeometry');reserved=r['n']==16
  else:
   allowed=(16,32,64,128,256)if kind in('load','store')else(32,128)
   need(r['sew']==32 and r['bytes']in allowed and r['lmul']==max(1,r['bytes']//32)and r['vl']==r['bytes']//4 and r['n']in(16,64)and r['streams']==(1 if kind in('load','store')else 2),'Independentmemorygeometry')
   reserved=r['bytes']==(64 if kind in('load','store')else 128)
  need(r['internal_split']==('reserved_holdout'if reserved else'train')and r['expected_checksum']==checksum(r),'Independent split/valuegolden')
 parent=Path(__file__).resolve().parents[2]/'build/rvv-identify-compact-v1/corpus.json'
 need(c['cases']==[x for x in json.loads(parent.read_text())['cases'] if x['hart']==2],'Exact frozen parent subset/order/goldens')
 need(counts==dict(integer=288,fp=216,load=24,store=24,load_use=12,load_independent=12,store_compute=12),'All requiredCartesianfamilies')
 return True
def canonical(c):
 validate_corpus(c);out=[]
 for r in c['cases']:out.append(dict(case_id=r['case_id'],parent_case_id=r['parent_case_id'],suite='rvv_identify',region='kernel',hart=r['hart'],trial_id=r['trial_id'],kind=r['kind_id'],sew=r['sew'],lmul=r['lmul'],mode=r['mode'],operations=r['n'],vector_bytes=r['bytes'],vl=r['vl'],checked_words=(1024 if r['kind'].startswith('matrix_')else r['vl']*r['streams']),mismatch_or=0,msip_before=0,msip_after=0,checksum=checksum(r),expected_checksum=checksum(r),**{'pass':True}))
 return out
def validate_decoded(text,c):
 want=canonical(c);rows=[];done=[];need('IRIS_FATAL'not in text,'No guestfatal')
 for line in text.splitlines():
  if line.startswith('IRIS_REGION '):rows.append(json.loads(line.split(' ',1)[1]))
  elif line.startswith('IRIS_BATCH_DONE '):done.append(json.loads(line.split(' ',1)[1]))
 need(len(rows)==588 and done==[dict(failed=0,cases=588,regions=588,trials=3)]and all(type(x)is int for x in done[0].values()),'Fullnormal588completion')

 prior={}
 for r,w in zip(rows,want):
  need(all(type(r.get(k))is type(v)and r[k]==v for k,v in w.items()),'Independentrole/word/count/golden')
  for k in('start_cycle','issue_cycle','end_cycle','instret_delta','issue_instret_delta','drain_instret_delta','mtime_before','mtime_after'):need(type(r[k])is int and 0<=r[k]<2**64,'Typed actualphasecounter')
  need(r['start_cycle']<r['issue_cycle']<=r['end_cycle']and r['start_cycle']>=prior.get(r['hart'],0)and r['mtime_after']>=r['mtime_before'],'Ordered actualsourcecounters')
  need(r['instret_delta']==r['issue_instret_delta']+r['drain_instret_delta']and r['issue_instret_delta']>=w['operations'],'Actual minstret phases, no invention');prior[r['hart']]=r['end_cycle']
 return dict(regions=588,trials=3,checked_words=sum(r['checked_words']for r in rows),normal_completion=True,actual_issue_and_drain_windows=588,timing_certified=False)


def validate(text,c):
 return validate_decoded(text,c)
