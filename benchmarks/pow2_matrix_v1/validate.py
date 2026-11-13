"""Independent canonical shape/role, fullword golden and output-counter validation."""
import json,struct
from pathlib import Path
SHAPES=[(x,x,x)for x in(8,16,32,64,128,256)]+[(32,32,x)for x in(8,16,64,128,256)]
RESERVED={(16,16,16),(128,128,128),(32,32,64)}
def need(ok,why):
 if not ok:raise ValueError(why)
def canonical():
 for trial in range(3):
  for m,n,k in SHAPES:
   for fp8 in(0,1):
    for h in(0,1):
     yield dict(id='matrix.pow2.%dx%dx%d.%s.hart%d.trial%d'%(m,n,k,'fp8-e4m3'if fp8 else'int8-signed',h,trial),m=m,n=n,k=k,fp8=fp8,hart=h,trial=trial,words=m*n,macs=m*n*k,internal_split='reserved_holdout'if(m,n,k)in RESERVED else'train')
def check_corpus(c,raw):
 need(c.get('schema')=='iris.pow2_single_matrix_corpus.v1'and c.get('required_regions')==132 and c.get('reserved_timing_labels_root_only')is True and c.get('negative_skip_kernel')is False,'Source corpus scope')
 need(len(c['cases'])==132,'Complete132cases');offset=0
 for row,want in zip(c['cases'],canonical()):
  need(all(type(row.get(k))is type(v)and row[k]==v for k,v in want.items()),'Canonicalshape/dtype/hart/trial/split')
  need(row['golden_offset']==offset and row['golden_bytes']==4*row['words'],'Goldenlayout')
  h=row['hart'];m,n,k=row['m'],row['n'],row['k'];gold=raw[offset:offset+row['golden_bytes']];need(len(gold)==row['golden_bytes'],'Goldenbounds');fnv=14695981039346656037
  for i in range(m):
   for j in range(n):
    # Independent closed-form exact mathematical result; source generator uses every MAC.
    sign=-1 if(i+j)&1 else 1;v=sign*(1+(i+h)%3)*(1+(j+2*h)%4)*k;word=struct.pack('<f',v)if row['fp8']else (v&0xffffffff).to_bytes(4,'little');need(gold[4*(i*n+j):4*(i*n+j+1)]==word,'Independent everyword golden')
    for b in word:fnv=((fnv^b)*1099511628211)&0xffffffffffffffff
  need(row['checksum']==fnv,'Independent allword hash');offset+=len(gold)
 need(offset==len(raw),'No unboundgoldenbytes');return True
def validate(text,c):
 need('IRIS_FATAL'not in text,'No fatal');refusals=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_HART2_VME_REFUSAL ')];need(refusals==[dict(hart=2,illegal_seen=1)]and all(type(v)is int for v in refusals[0].values()),'Actual hart2 refusal');rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_REGION ')];done=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_BATCH_DONE ')];need(len(rows)==132 and done==[dict(failed=0,cases=132,regions=132,trials=3)]and all(type(x)is int for x in done[0].values()),'Complete normal132');prior={}
 for row,spec in zip(rows,c['cases']):
  want=dict(case_id=spec['id'],suite='pow2_matrix',region='kernel',hart=spec['hart'],trial_id=spec['trial'],m=spec['m'],n=spec['n'],k=spec['k'],dtype='fp8-e4m3-e4m3-f32'if spec['fp8']else'int8-signed-i32',words=spec['words'],failed_words=0,checksum=spec['checksum'],expected_checksum=spec['checksum'],**{'pass':True})
  need(all(type(row.get(k))is type(v)and row[k]==v for k,v in want.items()),'All typed numerical outputs/role/shape')
  need(all(type(row.get(k))is int and 0<=row[k]<1<<64 for k in('start_cycle','end_cycle','instret_delta','mtime_before','mtime_after'))and row['start_cycle']>=prior.get(row['hart'],0)and row['end_cycle']>row['start_cycle']and row['instret_delta']>0 and row['mtime_after']>=row['mtime_before'],'Ordered counters');prior[row['hart']]=row['end_cycle']
  for k,v in [('mtime_hz',500000),('source_core_cycles_per_mtime_tick',1000),('mtime_scope','encloses_CSR_ROI_with_sampling_overhead'),('mtime_quantization_error_bound_core_cycles',1000)]:need(type(row.get(k))is type(v)and row[k]==v,'CLINTscope')
 return dict(regions=132,full_words_checked=sum(r['words']for r in rows),all3harts_booted=True,hart2_VME_refusal_required_before_first_case=True,normal_guest_exit=True,train_regions=96,reserved_regions=36,source_image_association_verified=False,timing_certified=False)
