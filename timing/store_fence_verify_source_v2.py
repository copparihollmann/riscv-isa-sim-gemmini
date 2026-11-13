#!/usr/bin/env python3
"""Independent finite event-chain/source provenance proof; not a fitted latency."""
import copy,hashlib,json,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify(text):
 cases=[];events=[];done=[]
 for line in text.splitlines():
  kind,payload=line.split(' ',1);x=json.loads(payload)
  if kind=='CASE':cases.append(x)
  elif kind=='EVENT':events.append(x)
  elif kind=='DONE':done.append(x)
  else:raise ValueError('Unexpected transcript')
 expected={'exclusive-clean-dirtify','exclusive-dirty-local','shared-line-after-two-peer-flag-reads','different-line-peer-polls'}
 if len(cases)!=8 or{(x['seed'],x['case'])for x in cases}!={(s,c)for s in(1,17)for c in expected}or len(done)!=1 or done[0]['status']!='passed'or done[0]['cases']!=8:raise ValueError('Complete8finitecases')
 results=[]
 for row in cases:
  if any(type(row[k])is not int for k in ['seed','writer','accepted_edge','response_edge','ordered_edge','response_delay','ordered_delay','A','B','C','D','outer_reads']):raise ValueError('Typed event/counter records')
  if not row['accepted_edge']<row['response_edge']<row['ordered_edge']or row['response_delay']!=row['response_edge']-row['accepted_edge']or row['ordered_delay']!=row['ordered_edge']-row['accepted_edge']or row['outer_reads']!=0:raise ValueError('Exact positive interval arithmetic/noouterreads')
  own=[e for e in events if(e['seed'],e['case'])==(row['seed'],row['case'])]
  if [sum(e['kind']==k for e in own)for k in range(4)]!=[row[k]for k in['A','D','B','C']]:raise ValueError('Actual event counts')
  if row['case']=='shared-line-after-two-peer-flag-reads':
   if len(own)!=4 or [e['kind']for e in own]!=[0,2,3,1]or [e['edge']for e in own]!=sorted(set(e['edge']for e in own)):raise ValueError('AcceptedAcquire→peerProbe→ProbeAck→matchingGrant')
   a,b,c,d=own
   if(a['opcode'],a['param'],a['source'],a['address'])!=(6,2,0,0x80010000)or(c['opcode'],c['param'],c['source'],c['address'])!=(4,2,0,0x80010000)or(d['opcode'],d['param'],d['source'])!=(4,0,0):raise ValueError('SourceBtoTupgrade/peerack/toTgrant identity')
   if a['hart']!=d['hart']!=1 or b['hart']!=1 or c['hart']!=1 or b['address']!=a['address']or b['opcode_known']is not False:raise ValueError('Physical port ownership/unknownunexposedopcode')
   if not row['accepted_edge']<=a['edge']<b['edge']<c['edge']<d['edge']<row['response_edge']<row['ordered_edge']:raise ValueError('Causal accepted/completed intervals')
  elif own:raise ValueError('Local metadata/data writes must not inventTL transactions')
  results.append(dict(seed=row['seed'],case=row['case'],ordered_delay_source_edges=row['ordered_delay']))
 for seed in(1,17):
  group={r['case']:r for r in cases if r['seed']==seed}
  if group['exclusive-dirty-local']['ordered_delay']!=group['different-line-peer-polls']['ordered_delay']or group['shared-line-after-two-peer-flag-reads']['ordered_delay']<=group['exclusive-clean-dirtify']['ordered_delay']<=group['exclusive-dirty-local']['ordered_delay']:raise ValueError('Finite shared/private counterfactual ordering')
 return results

def main():
 b=ROOT/'build/store-fence-source-v2';out=ROOT/'build/store-fence-source-proof-v2';out.mkdir();text=(b/'stdout').read_text();results=verify(text);controls=[]
 def reject(name,value):
  try:verify(value)
  except(ValueError,KeyError,TypeError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted '+name)
 lines=text.splitlines();idx=next(i for i,x in enumerate(lines)if x.startswith('EVENT '));reject('missing-acquire','\n'.join(lines[:idx]+lines[idx+1:]));reject('missing-case','\n'.join(x for x in lines if not(x.startswith('CASE ')and'"seed":17'in x and'exclusive-dirty-local'in x)))
 for name,key,value in [('wrong-A-source','source',1),('wrong-A-permission','param',1),('AafterGrant','edge',99999)]:
  bad=lines[:];r=json.loads(bad[idx].split(' ',1)[1]);r[key]=value;bad[idx]='EVENT '+json.dumps(r);reject(name,'\n'.join(bad))
 ci=next(i for i,x in enumerate(lines)if x.startswith('CASE '));bad=lines[:];r=json.loads(bad[ci].split(' ',1)[1]);r['ordered_delay']=False;bad[ci]='CASE '+json.dumps(r);reject('boolean-delay','\n'.join(bad))
 source=[ROOT/'third_party/shuttle/src/main/scala/dmem/DCache.scala',ROOT/'third_party/shuttle/src/main/scala/dmem/MSHR.scala',ROOT/'third_party/shuttle/src/main/scala/dmem/MSHRs.scala',ROOT/'third_party/shuttle/src/main/scala/exu/Core.scala',ROOT/'third_party/rocket-chip/src/main/scala/tilelink/Metadata.scala',ROOT/'third_party/rocket-chip/src/main/scala/rocket/DCache.scala',ROOT/'third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala'];build=json.loads((ROOT/'build/shuttle-memory-system-native-v6/build.json').read_text());libs=[Path(x)for x in build['required_static_libraries_in_link_order']]+[ROOT/'build/serial-memory-context-sdk-v2/fased/sdk/libiris_fased_service.a'];deps={Path(x)for x in shlex.split((b/'check.d').read_text().replace('\\\n',' ').split(':',1)[1])};paths=[Path(__file__).resolve(),ROOT/'timing/store_fence_source_check_v2.cpp',ROOT/'timing/shuttle_memory_system_check.cpp',b/'argv.json',b/'check',b/'stdout',b/'stderr',ROOT/'build/shuttle-memory-system-native-v6/build.json',*source,*libs,*[p for p in deps if p.is_file()]]
 r=dict(schema='iris.store_fence_source_permission_path.v2',status='passed_finite_component_witness',seeds=[1,17],cases=8,source_edges=results,independent_corruptions=controls,shared_case_difference_84_edges_is_observation_not_parameter=True,all_cases_outer_reads=0,source='savedIrisConfig FIR andfrozen fullShuttle/Rocket/NoC/L2/Serial/FASED cuts',fixture_FASeD_parameters=dict(readLatency=30,writeLatency=30,readMaxReqs=16,writeMaxReqs=16),outer_service_scope='Explicit synthetic functionalactor; noouterread occursduringthe measured8cases',reset_scope='Actualreset/metadata sweep+64acceptedphysicalwarmuploads perShuttle; strict invalid-RPQguard retained; nointernalstate injection',component_causality='WarmBranch→Dirtypermission upgrade traverses actualAcquireBlockBtoT/probe/ack/GranttoT despite presentline; trueDirtyhit useslocalS3dataarray without mandatoryNoCwrite/ack',CPU_FENCE_instruction_executed=False,ordered_scope='Actualcache io_ordered assertion afteracceptedrequest/response; staticShuttleCore FENCE consumes this predicate pluspipeline/scoreboard/drain gates',Rocket_FENCE_scope='OrdinaryFENCE setsid_reg_fence; nextmemorywaitsordered, whilefollowingCSR maypass. No inventedfullwritebackflush.',unexposed_Probe_opcode_explicitly_unknown=True,not_whole_FPGA_gap_explanation=True,not_universal_store_cost=True,not_arbitrary_ROI_penalty=True,whole_CPU_phase_or_timing_qualified=False,hardware_contacted=False,source_image_association_verified=False,full_2pct_certified=False,reserved_hardware_timing_labels_consumed=False,input_sha256={str(p):sha(p)for p in paths});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',controls=len(controls),report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()
