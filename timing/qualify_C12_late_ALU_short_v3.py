#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,copy,subprocess
R=Path(__file__).resolve().parents[1];O=R/'build/C12-late-ALU-short-proof-v3';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(b,s):
 if not b:raise ValueError(s)
def source(rows):
 need(len(rows)==6 and{(x['seed'],x['mode'])for x in rows}=={(s,m)for s in(1,17)for m in range(3)},'Source complete6cases')
 for x in rows:
  for k in('RRD','load_EX','load_COM','ALU_COM','ALU_WB','dependent_RRD','WB_value','RF_dependent_value'):need(type(x[k])is int,'Typed edge/value')
  need(x['load_EX']==x['RRD']+1 and x['load_COM']==x['ALU_COM']==x['RRD']+3 and x['ALU_WB']==x['ALU_COM']+1==x['dependent_RRD'],'Source COM/WB/RAW phases')
  need(x['WB_value']==0x123456789+(3 if x['mode']==0 else 5) and x['RF_dependent_value']==x['WB_value']+1 and x['state_injected']is False and x['pass']is True,'Exact source value')
sp=R/'build/Shuttle-late-ALU-source-probe-v1';rows=[json.loads(l)for l in(sp/'stdout').read_text().splitlines()];source(rows);mut=[]
for n,k,v in(('WB-one-edge-early','ALU_WB',5),('dependent-RRD-early','dependent_RRD',5),('wrong-result','WB_value',0),('boolean-COM','ALU_COM',True)):
 x=copy.deepcopy(rows);x[0][k]=v
 try:source(x)
 except ValueError:mut.append(n)
 else:raise ValueError(n)
G=R/'build/C12-late-ALU-coherence-full-ON-v1';g=json.loads((G/'graph.json').read_text());ev=g['events'];by={x['id']:x for x in ev};late=[x for x in ev if x['hart']==0 and x['pc']==0x800004d8 and x['name'].endswith('.late-WB-result')];need(len(late)==3,'Target2positive/1coherencekill');positive=[];killed=[]
for x in late:
 cs=[by[d]for d in x['deps']if by[d]['name'].endswith('.COM')and by[d]['pc']==x['pc']];need(len(cs)==1,'Unique own semanticCOM dependency');c=cs[0];need(x['id']not in c['deps'],'No COM-WB dependency cycle')
 if x.get('cancelled'):
  need(x['issued']is False and x['completed']is False and c.get('cancelled')is True and c['completed']is False and x['bytes']==x['macs']==0,'Killed lateALU no publication/credit');killed.append({'WB':x,'COM':c})
 else:
  need(x['completed']is True and c['completed']is True and x['start']==c['end']and x['end']==c['end']+1,'Physical result after semanticCOM');positive.append({'WB':x,'COM':c})
need(len(positive)==2 and len(killed)==1,'Actual source-eligible positive and replay outcomes');need(g['pending_operations']==0 and g['pending_owned_load_responses']==0,'No orphan physical/CPU actor');need(g['load_front_metrics'][0]['coherence_fallbacks']==1,'Actual target coherence fallback')
B=R/'build/C12-late-ALU-coherence-ON-v1';need((B/'stdout').read_bytes()==(G/'stdout').read_bytes(),'Full/bounded values identical');need((B/'features.jsonl').read_bytes()==(G/'features.jsonl').read_bytes(),'Full/bounded actual CSR prefixes identical');need(json.loads((B/'graph.json').read_text())['cycles']==g['cycles'],'Full/bounded clock parity')
irq=[]
for h in(0,1):
 d=R/f'build/C12-late-ALU-IPI-h{h}-ON-v1';starts={};writes={};exceptions=[]
 elf=R/f'build/C12-late-ALU-IPI-h{h}-guest-v1/guest.elf';nm=subprocess.check_output(['/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm','-n',str(elf)],text=True);base=int(next(l.split()[0]for l in nm.splitlines()if l.endswith(' pending_ipi_load')),16);actor_pc=base+12
 for l in(d/'cpu.jsonl').open():
  x=json.loads(l)
  if x['event']=='late_ALU_semantic_COM'and x['pc']==actor_pc:starts[x['instruction']]=x
  elif x['event']=='late_ALU_physical_WB'and x['pc']==actor_pc:writes[x['instruction']]=x
  elif x['event']=='COM_enter'and x['raw']==0:exceptions.append(x)
 need(len(starts)>0 and set(starts)==set(writes),'Every actual retired late owner publishes exactlyonce')
 for i,x in starts.items():need(writes[i]['cycle']==x['cycle']+1 and writes[i]['value']==46,'Exact physical phase/returned value')
 need(len(exceptions)==64,'All64 actualMSIP perhart');between=[{'late_COM':x,'physical_WB':writes[i],'IRQ_COM':e}for i,x in starts.items()for e in exceptions if e['cycle']==x['cycle']+3]
 irq.append({'hart':h,'real_MSIP_interrupts':64,'late_ALU_retired_and_published':len(starts),'IRQ_selected_same_edge_as_late_COM':between})
paths=[R/'build/C12-late-ALU-OFF-first59-v1/run.json',R/'build/C12-late-ALU-ON-first59-v1/run.json',R/'build/C12-late-ALU-direct-ON-v1/run.json',G/'run.json',B/'run.json',R/'build/C12-late-ALU-pending-guards-ON-v1/run.json']+[R/f'build/C12-late-ALU-unknown-h{h}-ON-v1/run.json'for h in(0,1)]+[R/f'build/C12-late-ALU-IPI-h{h}-ON-v1/run.json'for h in(0,1)]
inputs={}
for p in paths:
 r=json.loads(p.read_text());need(r.get('pass')is True,str(p));inputs[str(p)]=sha(p)
 for n,d in r['input_sha256'].items():need(sha(n)==d,n);inputs[n]=d
for p in(Path(__file__),G/'graph.json',sp/'argv.json',sp/'check',sp/'stdout',R/'timing/shuttle_late_ALU_source_probe_v1.cpp',R/'build/shuttle-lsu-phase-source-v1/build.json',R/'build/shuttle-lsu-phase-source-v1/rtl/ShuttleCore.sv',R/'build/shuttle-lsu-phase-source-v1/obj/VShuttleLSUPhase__ALL.a',R/'third_party/shuttle/src/main/scala/exu/Core.scala'):inputs[str(p)]=sha(p)
r={'schema':'iris.C12_late_ALU_short_proof.v1','pass':True,'native_binary_sha256':sha(R/'build/spike-C12-late-ALU-v1/spike'),'UART_sha256':sha(R/'build/spike-C12-late-ALU-v1/libsifive_uart.so'),'source_cases':rows,'source_event_corruption_refusals':mut,'native_completed_late_owners':positive,'actual_coherence_killed_late_owner':killed,'historical_cancel_reason_note':'source-MEM-mispredict is preexisting generic reason; actual trigger here is recorded load coherence fallback, not branch evidence','IRQ_phase_observations':irq,'OFF_first59_record_CSR_async_byte_parity':True,'ON_first59_full_numerics_and_instret':True,'direct_numeric_calls':1056,'partial_unknown_producer_refusals':2,'source_timing_2pct_certified':False,'model_time_improvement_observed_in_representative_loop':False,'hardware_contacted':False,'native_source_frozen':True,'full1320_ON_qualification':'running-separately-not-claimed-in-this-short-receipt','input_sha256':inputs};(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'source_cases':6,'killed_late_owners':len(killed),'IRQ_cases':len(irq),'report_sha256':sha(O/'report.json')}))
