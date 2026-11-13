#!/usr/bin/env python3
"""Strict full-word independent validator for the protected operator batch."""
import hashlib,json,struct

def require(ok,message):
 if not ok:raise ValueError(message)
def fnv(data):
 result=14695981039346656037
 for b in data:result=((result^b)*1099511628211)&((1<<64)-1)
 return result
def independent(k,trial):
 a=bytes((17*i+11*q+3+19*trial)%256 for i in range(2)for q in range(k));b=bytes((13*q+7*j+5+23*trial)%256 for q in range(k)for j in range(32));out=[0]*64
 for q in range(k):
  for i in range(2):
   x=a[i*k+q];x-=256 if x>=128 else 0
   for j in range(32):
    y=b[q*32+j];y-=256 if y>=128 else 0;out[i*32+j]=(out[i*32+j]+x*y)&0xffffffff
 quant=[]
 for word in out:
  signed=word-(1<<32)if word&(1<<31)else word;quant.append(struct.unpack('<I',struct.pack('<f',max(-128,min(127,(signed+512)//1024))))[0])
 return out,quant,fnv(a+b+b''.join(struct.pack('<I',x^0xffffffff)for x in out))
def validate(text,corpus):
 require(corpus.get('schema')=='iris.model_operator_validation_batch.v1' and corpus.get('calibration_usable')is False,'protected corpus required')
 require(len(corpus['cases'])==48 and corpus['required_regions']==120 and corpus['trials']==3,'finite batch geometry')
 regions=[];words=[];done=[]
 for line in text.splitlines():
  for tag,dest in [('IRIS_REGION ',regions),('IRIS_WORDS ',words),('IRIS_BATCH_DONE ',done)]:
   if line.startswith(tag):dest.append(json.loads(line[len(tag):]))
 require(len(regions)==120 and len(words)==48 and done==[dict(failed=0,cases=48,regions=120,trials=3)],'complete unique batch')
 require('IRIS_FATAL 'not in text,'fatal trap')
 lookup={};last={};cache={};ri=0;checks=0
 for c,w in zip(corpus['cases'],words):
  case_id=c['case_id'];require(case_id not in lookup and w['case_id']==case_id,'word output case order/identity');lookup[case_id]=c
  k=c['source_case']['shape_mnk'][2];trial=c['trial_id'];key=(k,trial)
  if key not in cache:cache[key]=independent(k,trial)
  expected,quant,producer=cache[key]
  require(w['accumulator_u32']==expected and w['W8A8_f32_words']==quant,'independent full word mismatch')
  require(c['expected_words']==dict(accumulator_u32=expected,W8A8_f32_words=quant,producer_hash=producer),'embedded mathematical corpus changed')
  checks+=128
  for h in c['active_harts']:
   row=regions[ri];ri+=1;require(row['case_id']==case_id and row['hart']==h and row['trial_id']==trial,'exact region order/identity')
   require(row['region']==('producer'if h==2 else'compiler_kernel')and row['suite']=='model_operator_validation','semantic region')
   count=64//c['workers'];expected_hash=producer if h==2 else fnv(b''.join(struct.pack('<I',x)for x in expected[h*count:(h+1)*count]))
   require(row['checksum']==row['expected_checksum']==c['expected_checksums'][str(h)]==expected_hash and row['pass']is True and row['failed_words']==0,'independent region checksum/failure')
   require(isinstance(row['start_cycle'],int)and row['end_cycle']>row['start_cycle']>=last.get(h,0)and row['instret_delta']>0,'real counter progress/order')
   last[h]=row['end_cycle'];checks+=4
 require(ri==len(regions),'extra regions')
 return dict(cases=48,regions=120,trials=3,full_int32_words=3072,full_W8A8_words=3072,independent_checks=checks,harts=[0,1,2],all_cases_validation_only=True,TinyLlama_protected=True,calibration_usable=False)
