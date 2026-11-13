"""Independent power-of-two single-active-hart geometry, pointer and counter oracle."""
import json
SIZES=tuple(1<<k for k in range(10,23));RESERVED=(4096,65536,524288)
SPLIT_SHA='d987081d2f398ed062e38f95d197f4adaf98d3f5518ef26387f5d7ec0b1e6f0e'
def need(ok,why):
 if not ok:raise ValueError(why)
def uint(x):return type(x)is int and 0<=x<1<<64
def canonical():
 out=[]
 for trial in range(3):
  for size in SIZES:
   for hart in range(3):
    parent='memory.pow2.single.%d.hart%d.trial%d'%(size,hart,trial);expected=0x90000000+hart*0x02000000+64*((17*trial+7*hart)%(size//64))
    for p in range(2):out.append(dict(case_id=parent+'.pass%d'%p,parent_case_id=parent,suite='pow2_single_memory',region='chase',trial_id=trial,pass_index=p,hart=hart,footprint_bytes=size,body_loads=size//64,requested_bytes=size//8,checksum=expected,expected_checksum=expected,**{'pass':True}))
 return out
def validate_corpus(c):
 need(c.get('schema')=='iris.pow2_single_memory_corpus.v1'and c.get('split_id')=='iris-pow2-single-memory-v1'and c.get('frozen_split_sha256')==SPLIT_SHA,'Exact frozen power2corpus/split')
 need(c.get('fitting_only')is True and c.get('global_heldout')is False and c.get('reserved_timing_labels_root_only')is True and c.get('negative_skip_kernel')is False and c.get('source_image_association_verified')is False and c.get('physical_DRAM_miss_or_traffic_measured')is False,'Source/label policy')
 for k,v in [('trials',3),('passes',2),('physical_harts',3),('required_regions',234),('measurement_groups',39),('records_per_group',6),('console_free_windows_per_group',6)]:need(type(c.get(k))is int and c[k]==v,'Typed corpus '+k)
 need(c.get('reserved_sizes')==list(RESERVED)and c.get('groupwise_console_records')is True and len(c.get('cases',[]))==117,'Complete117cohorts withreservedgrouping')
 index=0
 for trial in range(3):
  for size in SIZES:
   for hart in range(3):
    row=c['cases'][index];index+=1;parent='memory.pow2.single.%d.hart%d'%(size,hart);stem=parent+'.trial%d'%trial
    fields=dict(id=stem,case_id=stem,semantic_parent_case_id=parent,footprint_bytes=size,nodes=size//64,mask=1<<hart,active_harts=[hart],trial_id=trial,base_by_hart=[0x90000000+h*0x02000000 for h in range(3)],expected_checksums_by_hart=[0x90000000+h*0x02000000+64*((17*trial+7*h)%(size//64))for h in range(3)],internal_split='reserved_holdout'if size in RESERVED else'train',split_group_id='footprint-bytes:'+str(size))
    need(all(type(row.get(k))is type(v)and row.get(k)==v for k,v in fields.items()),'Independent source geometry/golden/split')
    need(all(type(x)is int for k in ['base_by_hart','expected_checksums_by_hart','active_harts']for x in row[k]),'No boolean ininteger geometry')
 return True
def validate(text,corpus):
 validate_corpus(corpus);need('IRIS_FATAL'not in text,'No fatal guest');got=[];groups=[];done=[]
 for line in text.splitlines():
  if line.startswith('IRIS_REGION '):got.append(json.loads(line.split(' ',1)[1]))
  elif line.startswith('IRIS_FOOTPRINT_GROUP '):
   g=json.loads(line.split(' ',1)[1]);need(g==dict(group=len(groups),records=len(got))and all(type(v)is int for v in g.values())and len(got)==6*(len(groups)+1),'Exact group frontierafter6rows');groups.append(g)
  elif line.startswith('IRIS_BATCH_DONE '):done.append(json.loads(line.split(' ',1)[1]))
 want=canonical();need(len(got)==len(want)==234 and len(groups)==39,'All234ROIs/39frontiers');need(done==[dict(failed=0,cases=117,regions=234,trials=3)]and all(type(v)is int for v in done[0].values()),'Actualnormalallcorrectcompletion')
 prior={}
 for a,b in zip(got,want):
  need(all(type(a.get(k))is type(v)and a.get(k)==v for k,v in b.items()),'CanonicalactualROI/golden/placement')
  need(all(uint(a.get(k))for k in['start_cycle','end_cycle','instret_delta','mtime_before','mtime_after'])and a['end_cycle']>a['start_cycle']>=prior.get(a['hart'],0)and a['instret_delta']>=3*b['body_loads']+1 and a['mtime_after']>=a['mtime_before'],'Knownorderedcounter/CLINTwindow;equalsubtickallowed');prior[a['hart']]=a['end_cycle']
  for k,v in [('mtime_hz',500000),('source_core_cycles_per_mtime_tick',1000),('mtime_quantization_error_bound_core_cycles',1000),('mtime_scope','encloses_CSR_ROI_with_sampling_overhead')]:need(type(a.get(k))is type(v)and a[k]==v,'Actual sourceCLINTsampling scope')
 return dict(cases=117,regions=234,trials=3,physical_harts=[0,1,2],single_active_hart=True,footprint_sizes=list(SIZES),groups=39,body_loads=sum(x['body_loads']for x in want),requested_bytes=sum(x['requested_bytes']for x in want),physical_bytes_or_misses_measured=False,CLINT_windows=234,mtime_hz=500000,quantization_error_bound_source_core_cycles=1000,overhead_subtracted=False,train_regions=180,reserved_regions=54,reserved_timing_labels_root_only=True,normal_completion=True,global_heldout=False)
