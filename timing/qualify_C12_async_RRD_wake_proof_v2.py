#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1];OLD=R/'build/RVV-ASM-C12-six-TRAIN-attribution-v1';NEW=R/'build/RVV-ASM-C12-async-wake-six-TRAIN-v3';O=R/'build/C12-async-RRD-wake-causal-proof-v2';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();a=json.loads((OLD/'report.json').read_text());b=json.loads((NEW/'report.json').read_text());assert a['pass']is b['pass']is True;results=[];total=0;inputs={str(p):sha(p)for p in(Path(__file__),OLD/'report.json',NEW/'report.json')}
for x,y in zip(a['rows'],b['rows']):
 assert x['case_id']==y['case_id']and x['N']==y['N']and y['sum_lost_eligible_cycles']==0;assert len(x['actors'])==len(y['actors'])==x['N'];p=NEW/f"case{y['index']}.cpu.jsonl";ev=[json.loads(l)for l in p.read_text().splitlines()];inputs[str(p)]=sha(p);joins=[]
 for old,new in zip(x['actors'],y['actors']):
  for k in('latency','interval','resource'):assert old[k]==new[k],(x['case_id'],k)
  assert old['resource_start']-old['RRD']==new['resource_start']-new['RRD']==1;assert old['COM']-old['RRD']==new['COM']-new['RRD']==3
 if x['LMUL']==8:
  for first,second in zip(y['actors'],y['actors'][1:]):
   found=[e for e in ev if e['event']=='async_RRD_wake'and e['backend_node']==first['node']and e['retry_edge']==second['RRD']and e['pc']==second['pc']];assert len(found)==1;w=found[0];assert w['cycle']<w['retry_edge']==first['resource_end']-1<w['old_next_event']and w['head_COM']==first['COM'];accept=[e for e in ev if e['event']=='rrd_accept'and e['instruction']==second['instruction']and e['cycle']==second['RRD']];assert len(accept)==1 and accept[0]['raw']&0xfc00707f==0x57;joins.append({'actual_wake':w,'next_VADD_admission':accept[0],'prior_actor':first})
  assert len(joins)==x['sum_lost_eligible_cycles']==x['N']-1
 else:assert x['RRD_gap_histogram']==y['RRD_gap_histogram']and x['phase_global_cycles']==y['phase_global_cycles']
 total+=len(joins);results.append({'case_id':x['case_id'],'LMUL':x['LMUL'],'N':x['N'],'backend_latencies_and_intervals_unchanged':True,'old_RRD_gaps':x['RRD_gap_histogram'],'new_RRD_gaps':y['RRD_gap_histogram'],'lost_eligible_edges_removed':len(joins),'new_unexplained_skipped_edges':y['sum_lost_eligible_cycles'],'actual_wake_to_admission_joins':joins})
assert total==78
A=R/'build/rvv-compute-asm-C12-async-RRD-wake-ON-v1';B=R/'build/rvv-compute-asm-C12-async-RRD-wake-ON-v2';parity=[]
for name in('regions.jsonl','features.jsonl','stderr','stdout'):
 assert(A/name).read_bytes()==(B/name).read_bytes();inputs[str(A/name)]=sha(A/name);inputs[str(B/name)]=sha(B/name);parity.append(name)
r={'schema':'iris.C12_async_RRD_wake_causal_proof.v2','pass':True,'total_previously_lost_edges_removed':78,'legacy_backend_durations_intervals_capacity_admission_unchanged':True,'rows':results,'own_scope_refinement_full1320_byte_parity':parity,'scope_refinement':'V2 explicitly excludes source OPU-entry actors. Its OWN full1320 replay and10fresh normalexit guards completed; no numerical/source qualification transferred fromV1.','hardware_contacted':False,'hardware_labels_used':False,'parameters_fitted':False,'timing_2pct_certified':False,'input_sha256':inputs};(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'removed_edges':total,'report_sha256':sha(O/'report.json')}))
