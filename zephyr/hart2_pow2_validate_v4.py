"""Full little-endian per-element checks for the NEW Zephyr controller packet."""
import hashlib,importlib.util,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'benchmarks/zephyr_hart2_pow2_v4'
spec=importlib.util.spec_from_file_location('hart2_pow2_cases_v1',SOURCE/'cases.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def integer(v,name,minimum=0):
 if type(v)is not int or v<minimum:raise ValueError('Typed integer '+name)
 return v
def boolean(v,name):
 if type(v)is not bool:raise ValueError('Typed bool '+name)
 return v
def decode(text):
 result={}
 def unique(pairs):
  d={}
  for k,v in pairs:
   if k in d:raise ValueError('Duplicate JSON key '+k)
   d[k]=v
  return d
 for line in text.splitlines():
  line=line.strip()
  if line.startswith('IRIS_'):
   token,_,payload=line.partition(' ')
   if token in ['IRIS_REGION','IRIS_DATA','IRIS_BATCH_DONE','IRIS_H2_CONTROL_READY','IRIS_H2_CONTROL_DONE','IRIS_COMPUTE_READY','IRIS_FATAL']:
    obj=json.loads(payload,object_pairs_hook=unique)
    if type(obj)is not dict:raise ValueError('JSON object required')
    result.setdefault(token,[]).append(obj)
 return result
def validate(text,expect_failure=False,corpus=None):
 c=corpus or json.loads((SOURCE/'corpus.json').read_text())
 if c!=m.generate():raise ValueError('Source-only canonical corpus')
 d=decode(text);regions=d.get('IRIS_REGION',[]);data=d.get('IRIS_DATA',[])
 if len(regions)!=648:raise ValueError('Exact 648 regions')
 ready=d.get('IRIS_H2_CONTROL_READY',[]);done=d.get('IRIS_H2_CONTROL_DONE',[])
 if ready!=[dict(physical_hart=2,logical_cpu=2,pin=2,scalar_only=True)]:raise ValueError('Actual scalar hart2 readiness')
 if len(done)!=1 or done[0]!=dict(physical_hart=2,logical_cpu=2,dispatches=486,acknowledgements=648,checked_elements=181440,scalar_only=True):raise ValueError('Controller completion')
 for obj in ready+done:boolean(obj['scalar_only'],'scalar_only')
 wr=d.get('IRIS_COMPUTE_READY',[])
 if len(wr)!=2 or {x['physical_hart']for x in wr}!={0,1}:raise ValueError('Compute ready roles')
 for obj in wr:
  for key in ['physical_hart','logical_cpu','pin']:integer(obj[key],key)
  h=integer(obj['physical_hart'],'worker hart')
  if obj!=dict(physical_hart=h,logical_cpu=h,pin=h,before_vme_enable=True)or not boolean(obj['before_vme_enable'],'before_vme_enable'):raise ValueError('Actual worker role')
 chunks={i:{} for i in range(648)}
 for obj in data:
  if set(obj)!=set(['region_index','hart','offset','little_endian_hex']):raise ValueError('Chunk keys')
  rid=integer(obj['region_index'],'chunk rid');off=integer(obj['offset'],'chunk offset')
  if rid>=648:raise ValueError('Chunk RID')
  desc=c['regions'][rid];integer(obj['hart'],'chunk hart')
  raw=obj['little_endian_hex']
  if type(raw)is not str or not re.fullmatch('[0-9a-f]+',raw)or len(raw)%2:raise ValueError('Exact lowercase hex bytes')
  b=bytes.fromhex(raw)
  if off%128 or len(b)!=min(128,desc['bytes']-off)or off>=desc['bytes']or obj['hart']!=desc['hart']or off in chunks[rid]:raise ValueError('Chunk geometry/duplicate')
  chunks[rid][off]=b
 failed_regions=0;failed_elements=0;elements=0;acks=[0,0];golden_hash=hashlib.sha256();output_hash=hashlib.sha256()
 for rid,(r,desc)in enumerate(zip(regions,c['regions'])):
  for key in ['region_index','group','hart','logical_cpu','pin','hart_mask','trial','operations','start_cycle','issue_cycle','end_cycle','instret_delta','checksum','checked_elements','failed_elements','actual_vl','ack']:integer(r[key],key)
  h=desc['hart'];acks[h]+=1
  for key,value in dict(region_index=rid,group=desc['group'],case_id=desc['case_id'],region='kernel',hart=h,logical_cpu=h,pin=h,role=desc['role'],hart_mask=desc['hart_mask'],trial=desc['trial'],operations=desc['operations'],checked_elements=desc['elements'],ack=acks[h]).items():
   if r[key]!=value:raise ValueError('Region identity '+key)
  if not boolean(r['guard_ok'],'guard_ok'):raise ValueError('Sentinel corruption')
  vl=desc['elements']if not desc['kind']else desc['shape']
  if r['actual_vl']!=vl or not r['start_cycle']<=r['issue_cycle']<=r['end_cycle']or r['end_cycle']==r['start_cycle']or not r['instret_delta']:raise ValueError('Actual configuration/counter order')
  if set(chunks[rid])!=set(range(0,desc['bytes'],128)):raise ValueError('Missing element chunk')
  raw=b''.join(chunks[rid][off]for off in sorted(chunks[rid]));width=desc['element_bytes'];values=[int.from_bytes(raw[i:i+width],'little')for i in range(0,len(raw),width)];gold=m.golden(desc)
  mismatch=sum(a!=b for a,b in zip(values,gold));elements+=len(gold);failed_elements+=mismatch;failed_regions+=bool(mismatch)
  if r['failed_elements']!=mismatch or r['checksum']!=m.checksum(values):raise ValueError('Independent mismatch/checksum')
  if mismatch!=(desc['elements']if expect_failure else 0):raise ValueError('Every active element requires expected body outcome')
  output_hash.update(raw);golden_hash.update(b''.join(v.to_bytes(width,'little')for v in gold))
 if elements!=181440 or failed_regions!=(648 if expect_failure else 0):raise ValueError('All-region numerical coverage')
 footer=d.get('IRIS_BATCH_DONE',[])
 if footer!=[dict(failed=failed_regions,cases=486,regions=648,elements=181440,trials=3)]:raise ValueError('Exact completion footer')
 for k,v in footer[0].items():integer(v,'footer '+k)
 fatal=d.get('IRIS_FATAL',[])
 if expect_failure:
  if fatal!=[dict(reason_code=5,group=648,physical_hart=2,logical_cpu=2)]:raise ValueError('Actual negative fatal transport')
 elif fatal:raise ValueError('Fatal output')
 return dict(regions=648,groups=486,independent_elements=elements,failed_regions=failed_regions,failed_elements=failed_elements,guard_regions=648,training_eligible=456,protected_validation=192,all3_actual_roles=True,hart2_scalar_only_source_proof_required=True,output_sha256=output_hash.hexdigest(),golden_little_endian_sha256=golden_hash.hexdigest(),calibration_authorized=False,timing_certified=False)
