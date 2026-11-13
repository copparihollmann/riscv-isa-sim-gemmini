#!/usr/bin/env python3
"""Independent finite read/Put/ACK/ownership transcript proof, not memory calibration."""
from pathlib import Path
import copy,hashlib,json
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def exact(v):
 if type(v)is not int or v<0:raise ValueError('Typed nonnegative physical field')
 return v

def verify(text,rocket):
 parsed=[]
 for line in text.splitlines():
  k,p=line.split(' ',1);v=json.loads(p)
  if k not in ['EX','WB','A','D','READ','STATE','RESULT']:raise ValueError('Unknown observer record')
  for value in v.values():exact(value)
  parsed.append((k,v))
 labels={(s,d,vl)for s in[1,17]for d in[2,20]for vl in([16,32,64,128]if rocket else[0])};actual={(v['seed'],v['delay'],v.get('vl',0))for k,v in parsed};
 if actual!=labels:raise ValueError('Every seed/ACKcontrol/shape required')
 summaries=[]
 for label in sorted(labels):
  s,d,vl=label;rows={k:[v for tag,v in parsed if tag==k and(v['seed'],v['delay'],v.get('vl',0))==label]for k in ['EX','WB','A','D','READ','STATE','RESULT']};a=rows['A'];acks=rows['D'];reads=rows['READ'];states=rows['STATE'];result=rows['RESULT']
  if len(result)!=1 or not states or [x['edge']for x in states]!=list(range(states[-1]['edge']+1)):raise ValueError('Complete bounded continuous source window')
  macro=1 if rocket else 4;ng=(vl+31)//32 if rocket else 32
  if len(rows['EX'])!=macro or len(reads)!=ng:raise ValueError('Accepted macro/read geometry')
  if rocket:
   req=(vl+31)//32
   if len(a)!=req*4 or len(acks)!=req or len(rows['WB'])!=1 or rows['WB'][0]['edge']!=2:raise ValueError('EarlyfrontWB and all expanded physical A/D')
   for j,x in enumerate(reads):
    if(x['eg'],x['eidx'],x['debug_id'],x['rintent'])!=(8+j,32*j,0,((15>>j)<<j)<<8):raise ValueError('Every physicalEG read releases only earlier consumedgroups')
   packets=[]
   for j in range(req):
    beat=a[j*4:j*4+4]
    if [x['beat']for x in beat]!=[0,1,2,3]or len({(x['source'],x['size'],x['address'])for x in beat})!=1:raise ValueError('One un-interleaved32B TLmessage')
    if beat[0]['size']!=5 or beat[0]['address']!=0x80010000+32*j:raise ValueError('Source32Brequest width/address')
    for b,x in enumerate(beat):
     expected=0xff if 32*j+8*b<vl else 0
     if x['mask']!=expected:raise ValueError('Partial payload masked wire slots')
    packets.append((beat[0]['edge'],beat[-1]['edge'],beat[0]['source']))
  else:
   if len(a)!=32 or len(acks)!=32:raise ValueError('Four128Bstores require32distinct16Brequests')
   for j,x in enumerate(reads):
    group=j//8;off=j%8
    if(x['eg'],x['eidx'],x['debug_id'],x['rintent'])!=(48+off,4*off,group,((255>>off)<<off)<<48):raise ValueError('Compute perEG WAR/read-intent release')
   for j,x in enumerate(a):
    if x['size']!=4 or x['address']!=0x80010000+16*j or x['mask']!=(0xffff0000 if j%2 else 0xffff):raise ValueError('Actual16B masked Put in32B port')
   packets=[(x['edge'],x['edge'],x['source'])for x in a]
  if reads[0]['edge']!=5 or a[0]['edge']!=7:raise ValueError('Finite actual EX/read/firstA phase')
  owned={};queued={};peak=0
  for st in states:
   t=st['edge'];
   if st['owned']!=len(owned)or st['writer_inflights']!=len(queued)%(32 if rocket else 16):raise ValueError('Actual source ownership vs modulo inflight count')
   if owned and st['backend_busy']!=1:raise ValueError('Aggregate backend cannotidle with owned unackedrequest')
   for ack in[x for x in acks if x['edge']==t]:
    tag=ack['source']
    if tag not in queued or t!=queued[tag]+d:raise ValueError('Ack mustmatch completed Amessage and declared externaldelay')
    del queued[tag];del owned[tag]
   for start,end,tag in packets:
    if start==t:
     if tag in owned:raise ValueError('Source reuse beforeACK')
     owned[tag]=t
    if end==t:queued[tag]=t
   peak=max(peak,len(owned))
  if owned or queued or result[0]['unit_drained']<=acks[-1]['edge']:raise ValueError('Complete ACK/drain required')
  summaries.append(dict(profile='rocket'if rocket else'compute',seed=s,synthetic_ACK_delay_edges=d,VL=vl if rocket else 32,macro_stores=macro,VRF_read_groups=len(reads),TL_requests=len(packets),physical_A_beats=len(a),D_acks=len(acks),peak_outstanding_requests=peak,front_WB=2 if rocket else None,first_VRF_read=5,first_A=7,unit_drained=result[0]['unit_drained']))
 return summaries

def main():
 out=R/'build/rvv-source-store-proof-v1';out.mkdir(exist_ok=False);cb=R/'build/rvv-source-store-probe-v4';rb=R/'build/rvv-source-rocket-store-probe-v3';cases=verify((cb/'stdout').read_text(),False)+verify((rb/'stdout').read_text(),True);controls=[]
 def reject(name,text,rocket):
  try:verify(text,rocket)
  except(ValueError,KeyError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Acceptedcorruption '+name)
 for source,rocket in [(cb,False),(rb,True)]:
  lines=(source/'stdout').read_text().splitlines();idx=next(i for i,x in enumerate(lines)if x.startswith('A '));di=next(i for i,x in enumerate(lines)if x.startswith('D '));ri=next(i for i,x in enumerate(lines)if x.startswith('READ '))
  for name,index,key,value in [('wrong-A-size',idx,'size',6),('wrong-A-mask',idx,'mask',0),('wrong-D-owner',di,'source',999),('wrong-readEG',ri,'eg',0),('boolean-edge',idx,'edge',True)]:
   bad=lines[:];kind,p=bad[index].split(' ',1);v=json.loads(p);v[key]=value;bad[index]=kind+' '+json.dumps(v);reject(('rocket-'if rocket else'compute-')+name,'\n'.join(bad),rocket)
  reject(('rocket-'if rocket else'compute-')+'missing-finalACK','\n'.join(x for i,x in enumerate(lines)if i!=max(j for j,s in enumerate(lines)if s.startswith('D '))),rocket)
 paths=[Path(__file__).resolve(),R/'timing/rvv_source_store_probe_v4.cpp',R/'timing/rvv_source_rocket_store_probe_v3.cpp',R/'timing/saturn_timing_reset_writers.cpp',R/'build/saturn-timing-sdk-v1/sdk/libiris_saturn_timing.a']
 for b in[cb,rb]:paths +=[b/x for x in ['argv.json','probe','stdout','stderr']]
 for name in ['rocket/Integration.scala','shuttle/Integration.scala','mem/Mem.scala','mem/TLInterface.scala','backend/StoreSequencer.scala','backend/OuterProductSequencer.scala','backend/Backend.scala']:
  paths.append(R/'third_party/saturn/src/main/scala'/name)
 paths +=[R/'build/rtl-verilator/gen-collateral'/n for n in ['SaturnRocketUnit.sv','SaturnShuttleUnit.sv','VectorMemUnit.sv','VectorMemUnit_2.sv','StoreSequencer.sv','StoreSequencer_2.sv','Rocket.sv']]
 r=dict(schema='iris.rvv_source_store_ownership_geometry.v1',pass_=True,finite_source_cases=cases,negative_controls=controls,internal_state_or_observed_readiness_injected=False,VRF_definedness='actual reset scrub64compute/32Rocket observed before firstVSE; only masked scrubknown0 payloadbytes checked',external_service='Aready1, sourceconditionalTLBidentity, matching ACK2/20edges aftercompleteA; synthetic boundary NOTphysical memorylatency',source_Rocket_FENCE_predicate='id_vec_busy && id_ctrl.fence; busy includesVU/VMU/TL/Hella; ordinaryscalarFENCE distinction doesnot bypassVU',front_retirement_is_not_memory_publication=True,source_busy_modulo_wrap_alone_not_completeness=True,no_hardware_contact=True,no_reserved_Hardware_labels_consumed=True,no_full_SoC_or_2pct_claim=True,input_sha256={str(p):sha(p)for p in paths});r['pass']=r.pop('pass_');(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',cases=len(cases),controls=len(controls),report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()
