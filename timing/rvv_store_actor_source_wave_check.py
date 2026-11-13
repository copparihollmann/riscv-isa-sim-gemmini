#!/usr/bin/env python3
"""Independent finite source-unit/public-port comparison; no timing fitting."""
from pathlib import Path
import copy,hashlib,json
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify(source,native):
 rows=[]
 for line in source.splitlines():
  k,p=line.split(' ',1);v=json.loads(p)
  if any(type(x)is not int or x<0 for x in v.values()):raise ValueError('Strict sourcephysicalfields')
  rows.append((k,v))
 sources=[]
 for seed in[1,17]:
  label=[(k,v)for k,v in rows if v['seed']==seed and v['delay']==20];wb=[v for k,v in label if k=='WB'];reads=[v for k,v in label if k=='READ'];a=[v for k,v in label if k=='A'];d=[v for k,v in label if k=='D'];result=[v for k,v in label if k=='RESULT'];
  if len(wb)!=1 or wb[0]['edge']!=2 or len(reads)!=8 or len(a)!=32 or len(d)!=8 or len(result)!=1:raise ValueError('Wholeactualsourcewave required')
  if [v['eidx']for v in reads]!=list(range(0,64,8))or[v['eg']for v in reads]!=list(range(8,16)):raise ValueError('SourceeveryphysicalVRFgroup')
  if any(v['size']!=5 or v['mask']!=255 for v in a):raise ValueError('Source32Brequest and8Bbeat masks')
  if result[0]['masked_payload_bytes']!=256 or result[0]['A_beats']!=32 or result[0]['D_acks']!=8:raise ValueError('Source256actualpayloadgeometry')
  sources.append(dict(VRF=[v['edge']-wb[0]['edge']for v in reads],A=[v['edge']-wb[0]['edge']for v in a],D=[v['edge']-wb[0]['edge']for v in d]))
 if sources[0]!=sources[1]:raise ValueError('Independentresetseeds disagree')
 fronts=[v for v in native if v.get('event')=='VSE_actor_front_COM'];
 if len(fronts)!=4:raise ValueError('Exactactualnativefourcommands')
 c=fronts[0];read=[v for v in native if v.get('event')=='VSE_actor_VRF_read'and v['command']==c['command']];a=[v for v in native if v.get('event')=='VSE_actor_A_beat'and v['command']==c['command']];d=[v for v in native if v.get('event')=='VSE_actor_ACK_publish'and v['command']==c['command']]
 if any(type(v['cycle'])is not int for v in read+a+d):raise ValueError('Nativeknownsourceclockfield')
 actual={'VRF':[v['cycle']-c['cycle']for v in read],'A':[v['cycle']-c['cycle']for v in a],'D':[v['cycle']-c['cycle']for v in d]}
 if actual!=sources[0]:raise ValueError('Sourcewavebackpressure/width/ACKphase mismatch')
 return actual

def main():
 out=R/'build/rvv-store-actor-source-wave-v1';out.mkdir(exist_ok=False);source=R/'build/rvv-source-rocket-VSE32-256-probe-v1/stdout';native=R/'build/rvv-vector-store-actor-v2-gates-v1/positive-h2-seed0-ACK20/async.jsonl';events=[json.loads(x)for x in native.read_text().splitlines()];wave=verify(source.read_text(),events);controls=[]
 for name in['early-read','missing-A','wrong-ACK','bool-time','missing-WB']:
  s=source.read_text();e=copy.deepcopy(events)
  if name=='early-read':next(v for v in e if v.get('event')=='VSE_actor_VRF_read'and v['command']==1)['cycle']-=1
  if name=='missing-A':e.pop(next(i for i,v in enumerate(e)if v.get('event')=='VSE_actor_A_beat'))
  if name=='wrong-ACK':next(v for v in e if v.get('event')=='VSE_actor_ACK_publish')['cycle']+=1
  if name=='bool-time':next(v for v in e if v.get('event')=='VSE_actor_VRF_read')['cycle']=True
  if name=='missing-WB':s='\n'.join(x for x in s.splitlines()if not x.startswith('WB '))
  try:verify(s,e)
  except(ValueError,KeyError):controls.append({'name':name,'rejected':True});continue
  raise ValueError('Corruptionaccepted '+name)
 paths=[Path(__file__),source,native,R/'timing/rvv_source_rocket_store_probe_v4.cpp',R/'timing/saturn_timing_reset_writers.cpp',R/'build/rvv-source-rocket-VSE32-256-probe-v1/probe',R/'build/rvv-source-rocket-VSE32-256-probe-v1/argv.json',R/'build/saturn-timing-sdk-v1/sdk/libiris_saturn_timing.a',R/'build/rvv-vector-store-actor-v2-gates-v1/report.json'];report=dict(schema='iris.finite_native_VSE_source_unit_wave.v1',status='passed',matched_source_reset_seeds=[1,17],matched_hart=2,SEW=32,LMUL=8,VL=64,bytes=256,first_command_comparison_only=True,source_anchor='ActualunitWBpreedge2',native_anchor='ActualoriginalhandlerfrontCOM;CPUjoiningremainsconditional',relative_source_edges=wave,refusals=controls,source_drain_scope='SourceRESULTunit_drained59 isafteredge59; STATE59 remainsbusy preedge. FullCPU/FENCE/VLU/MROB-returntail notqualified bythiswave.',numeric_scope='ActualRTL scrubknownzero maskedbytes; nativeindependent3..6/poison words qualifiedseparately',memory_service='EXPLICITSYNTHETICACK20edges;Aready1. NotphysicalNoC/DRAMfit.',source_state_or_ready_injected=False,hardware_contacted=False,reserved_Hardware_timings_consumed=False,input_sha256={str(p):sha(p)for p in paths});(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':main()
