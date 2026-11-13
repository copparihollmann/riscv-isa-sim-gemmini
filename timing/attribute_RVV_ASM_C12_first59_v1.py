#!/usr/bin/env python3
"""Six predeclared TRAIN rows; model-only timing and scheduler evidence."""
from pathlib import Path
import json,hashlib,collections,statistics,subprocess
R=Path(__file__).resolve().parents[1];D=R/'build/RVV-ASM-C12-ownzero-first59-diagnostic-v1';PAR=R/'build/RVV-ASM-C12-first59-parity-v2/report.json';assert json.loads(PAR.read_text())['pass']is True;O=R/'build/RVV-ASM-C12-six-TRAIN-attribution-v1';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();allrows=[json.loads(x)for x in(R/'build/rvv-compute-asm-C12-ownzero-v1/regions.jsonl').read_text().splitlines()];selected={i:allrows[i]for i in(1,4,19,22,55,58)};windows={i:(r['begin_global_read_cycle']-20,r['drain_global_read_cycle']+10)for i,r in selected.items()};cpu={i:[]for i in selected};streams={i:(O/f'case{i}.cpu.jsonl').open('w')for i in selected};tot=0
for line in(D/'cpu.jsonl').open():
 tot+=1;at=line.index('"cycle":')+8;c=int(line[at:line.index(',',at)])
 matches=[i for i,(a,b)in windows.items()if a<=c<=b]
 if matches:
  x=json.loads(line)
  for i in matches:cpu[i].append(x);streams[i].write(line)
for f in streams.values():f.close()
# A hard debuggerquit may leave one nonflushed async tail: preserve, do not decode.
raw=(D/'async.jsonl').read_bytes();tail=0
if raw and not raw.endswith(b'\n'):raw,rest=raw.rsplit(b'\n',1);tail=len(rest);raw+=b'\n'
asyncs=[json.loads(x)for x in raw.splitlines()];report=[]
for i,r in selected.items():
 assert r['internal_split']=='train'and r['lmul']in(1,2,8)and r['kind']==0
 b,issue,end=[r[k]for k in('begin_global_read_cycle','issue_global_read_cycle','drain_global_read_cycle')];xs=cpu[i];beg={x['backend_node']:x for x in asyncs if x['event']=='begin'and x['hart']==0 and b<=x['rrd']<end};pub={x['backend_node']:x for x in asyncs if x['event']=='publish'and x['backend_node']in beg};cancel={x['backend_node']:x for x in asyncs if x['event']=='cancel'and x['backend_node']in beg};done={x['backend_node']:x for x in xs if x['event']=='async_backend_complete'and x['backend_node']in beg};need=r['operations'];assert len(pub)==need,(i,len(pub),need);actors=[]
 for node,p in sorted(pub.items(),key=lambda z:beg[z[0]]['rrd']):
  a=beg[node];d=done[node];assert d['submitted']==a['rrd']and d['end']==d['cycle']and p['cycle']==max(a['com'],d['end']);actors.append({'instruction':a['instruction'],'node':node,'pc':a['pc'],'RRD':a['rrd'],'EX_earliest':a['ex'],'COM':a['com'],'resource_start':d['start'],'resource_end':d['end'],'latency':d['latency'],'interval':d['interval'],'resource':d['resource'],'numeric_publish':p['cycle']})
 gaps=collections.Counter(y['RRD']-x['RRD']for x,y in zip(actors,actors[1:]));skips=[x for x in xs if x['event']=='scheduler_advance'and x.get('skipped_predicate_edge')and b<=x['cycle']<end];clean=[x for x in skips if x['engaged']and not x['boundary']and x['packets']==0 and not x['blocked']and not x['tail_present']and not x['waiting_for_interrupt']and not x['pending_interrupt']];joined=[]
 for x in clean:
  nexts=[a for a in actors if a['RRD']>=x['next_event']and a['pc']==x['pc']]
  if not nexts:continue
  a=nexts[0]
  if a['RRD']!=x['next_event']:continue
  joined.append({'from_cycle':x['cycle'],'chosen_next_event':x['next_event'],'existing_predicate_first_RRD':x['derived_existing_predicate_first_RRD'],'actual_next_VADD_RRD':a['RRD'],'lost_eligible_cycles':a['RRD']-x['derived_existing_predicate_first_RRD'],'backend_node':x['backend_node'],'head_COM':x['head_COM'],'head_end':x['backend_end'],'frontier_PC':x['pc'],'actual_can_dispatch_now':x['actual_can_dispatch_now'],'all_recorded_blocking_flags_clear':True})
 first,last=actors[0],actors[-1];entry=[x for x in xs if x['event']=='rrd_accept'and b<=x['cycle']<=end];rejections=collections.Counter(x.get('reason')for x in xs if x['event']=='rrd_reject'and b<=x['cycle']<=end);phases={'begin_to_first_VADD_RRD':first['RRD']-b,'first_RRD_to_last_numeric_publish':last['numeric_publish']-first['RRD'],'last_numeric_publish_to_issue_CSR':issue-last['numeric_publish'],'issue_to_drain_CSR':end-issue,'global_total':end-b,'mcycle_total':r['end_cycle']-r['start_cycle'],'global_vs_mcycle_difference':end-b-(r['end_cycle']-r['start_cycle'])};row={'index':i,'case_id':r['case_id'],'hart':0,'SEW':r['sew'],'LMUL':r['lmul'],'N':need,'published_commands':len(pub),'accepted_commands':len(beg),'cancelled_commands':len(cancel),'source_DL128_EG_count':(r['vl']*r['sew']+127)//128,'RRD_gap_histogram':dict(gaps),'backend_start_minus_RRD_histogram':dict(collections.Counter(a['resource_start']-a['RRD']for a in actors)),'backend_latency_histogram':dict(collections.Counter(a['latency']for a in actors)),'numeric_publish_minus_backend_end_histogram':dict(collections.Counter(a['numeric_publish']-a['resource_end']for a in actors)),'phase_global_cycles':phases,'rrd_rejection_counts':dict(rejections),'skipped_eligible_RRD_edges':joined,'sum_lost_eligible_cycles':sum(x['lost_eligible_cycles']for x in joined),'actors':actors,'actual_RRD_instruction_sequence':entry};report.append(row)
inputs=[Path(__file__),PAR,D/'cpu.jsonl',D/'async.jsonl',R/'build/rvv-compute-asm-C12-ownzero-v1/regions.jsonl',R/'pipeline/riscv-isa-sim-C12-scheduler-diagnostic-v1/riscv/iris_timing_adapter.cc',R/'pipeline/riscv-isa-sim-C12-scheduler-diagnostic-v1/riscv/iris_empirical_async.inc',R/'benchmarks/rvv_compute_asm_v1/kernels.S'];out={'schema':'iris.RVV_ASM_C12_six_TRAIN_attribution.v1','pass':True,'provenance_parity_report':str(PAR),'CPU_lines_scanned':tot,'async_partial_tail_bytes_ignored_without_invention':tail,'rows':report,'hardware_labels_read':False,'reserved_hardware_labels_read':False,'parameters_fitted':False,'behavior_changed':False,'input_sha256':{str(p):sha(p)for p in inputs}};(O/'report.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'pass':True,'rows':[{k:r[k]for k in('index','LMUL','N','RRD_gap_histogram','backend_latency_histogram','sum_lost_eligible_cycles','phase_global_cycles')}for r in report],'report_sha256':sha(O/'report.json')}))
