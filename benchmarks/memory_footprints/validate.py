"""Independent finite-case/counter/golden checks for memory footprint runs."""
import json,hashlib
SIZES=(2048,16384,131072,1048576,4194304)
def require(value,why):
 if not value:raise ValueError(why)
def uint(x):return type(x)is int and 0<=x<2**64
def canonical():
 rows=[]
 for trial in range(3):
  for size in SIZES:
   for mask in range(1,8):
    for repeat in range(2):
     for hart in range(3):
      if mask>>hart&1:
       parent='memory.footprint.%d.mask%d.trial%d'%(size,mask,trial);base=0x90000000+hart*0x02000000;start=base+64*((17*trial+7*hart)%(size//64))
       rows.append(dict(case_id=parent+'.pass%d'%repeat,parent_case_id=parent,suite='memory_footprints',region='chase',trial_id=trial,pass_index=repeat,hart=hart,footprint_bytes=size,body_loads=size//64,requested_bytes=size//8,checksum=start,expected_checksum=start,**{'pass':True}))
 return rows
def validate_corpus(c):
 require(c.get('schema')=='iris.memory_footprint_fitting.v1'and c.get('fitting_only')is True and all(c.get(k)is False for k in('global_heldout','negative_skip_kernel','source_image_association_verified','physical_DRAM_miss_or_traffic_measured')),'Exactpositive fitting corpus')
 require(all(type(c.get(k))is int and c[k]==v for k,v in [('trials',3),('passes',2),('physical_harts',3),('required_regions',360)])and len(c.get('cases',[]))==105,'Complete typed corpus')
 index=0
 for trial in range(3):
  for size in SIZES:
   for mask in range(1,8):
    row=c['cases'][index];index+=1;parent='memory.footprint.%d.mask%d'%(size,mask);stem=parent+'.trial%d'%trial
    fields=dict(id=stem,case_id=stem,semantic_parent_case_id=parent,footprint_bytes=size,nodes=size//64,mask=mask,active_harts=[h for h in range(3)if mask>>h&1],trial_id=trial,base_by_hart=[0x90000000+h*0x02000000 for h in range(3)],expected_checksums_by_hart=[0x90000000+h*0x02000000+64*((17*trial+7*h)%(size//64))for h in range(3)],internal_split='internal_validation'if int(hashlib.sha256(parent.encode()).hexdigest()[:8],16)%5==0 else'train')
    require(all(row.get(k)==v and type(row.get(k))is type(v)for k,v in fields.items()),'Canonical corpus geometry/split')
    require(all(type(v)is int for k in('active_harts','base_by_hart','expected_checksums_by_hart')for v in row[k]),'Integer corpus geometry')
 return True
def validate(text,corpus):
 validate_corpus(corpus)
 require('IRIS_FATAL'not in text,'Fatalguest')
 got=[json.loads(x[len('IRIS_REGION '):])for x in text.splitlines()if x.startswith('IRIS_REGION ')];done=[json.loads(x[len('IRIS_BATCH_DONE '):])for x in text.splitlines()if x.startswith('IRIS_BATCH_DONE ')]
 want=canonical();require(len(got)==len(want)==360,'All360unique ROIs required');require(done==[dict(failed=0,cases=105,regions=360,trials=3)]and all(type(done[0].get(k))is int for k in('failed','cases','regions','trials')),'Normal allcorrect completion');previous={}
 for a,b in zip(got,want):
  require(all(a.get(k)==v and type(a.get(k))is type(v)for k,v in b.items()),'Independent semantic/golden/placement mismatch')
  require(all(uint(a.get(k))for k in('start_cycle','end_cycle','instret_delta'))and a['end_cycle']>a['start_cycle']>=previous.get(a['hart'],0)and a['instret_delta']>=3*b['body_loads']+1,'Counterprogress/mandatory loopinstruction lowerbound');previous[a['hart']]=a['end_cycle']
 return dict(cases=105,regions=360,trials=3,physical_harts=[0,1,2],footprint_sizes=list(SIZES),body_loads=sum(r['body_loads']for r in want),requested_bytes=sum(r['requested_bytes']for r in want),physical_bytes_or_misses_measured=False,normal_completion=True,fitting_only=True,global_heldout=False)
