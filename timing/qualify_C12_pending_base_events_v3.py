#!/usr/bin/env python3
"""Independent accepted-instruction/result/IRQ trace joins for the retry actor."""
import bisect,copy,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'build/C12-pending-base-event-proof-v3';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def events(p):
 rows=[]
 for line in p.open():
  x=json.loads(line)
  if x["event"]in("rrd_accept","result_callback","candidate_boundary","pending_base_retry","COM_enter","COM_exit"):rows.append(x)
 return rows
def symbols(elf):
 tool=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm');text=subprocess.check_output([str(tool),'-n',str(elf)],text=True);out={}
 for l in text.splitlines():
  f=l.split()
  if len(f)==3:out[f[2]]=int(f[0],16)
 return out
def retry_join(xs,pc):
 accepted={x['instruction']:x for x in xs if x['event']=='rrd_accept'};results={x['instruction']:x for x in xs if x['event']=='result_callback'};targets=[x for x in xs if x['event']in('rrd_accept','candidate_boundary')and x['pc']==pc];target_cycles=[x['cycle']for x in targets];joined=[]
 for w in xs:
  if w['event']!='pending_base_retry'or w['pc']!=pc:continue
  p=accepted.get(w['instruction']);f=results.get(w['instruction']);need(p is not None and f is not None,'Actual producer admission/completion missing');need(p['pc']==w['producer_pc']and p['cycle']<w['cycle']<f['cycle'],'Held base must have real older unfinished producer')
  k=bisect.bisect_left(target_cycles,w['cycle']);need(k<len(targets),'Retry never reaches original candidate path');t=targets[k];need(t['cycle']>=f['cycle'],'Consumer decision before producer value readiness');joined.append({'retry':w,'producer_RRD':p,'producer_result':f,'consumer_next_decision':t})
 return joined
def irq_join(xs):
 wait=[x for x in xs if x['event']=='pending_base_retry'];exc=[x for x in xs if x['event']=='COM_enter'and x['raw']==0];out=[]
 for e in exc:
  for w in wait:
   if e['pc']!=w['pc']or e['cycle']!=w['cycle']+4:continue
   need(not any(x['event']=='rrd_accept'and x['pc']==w['pc']and w['cycle']<x['cycle']<=e['cycle']for x in xs),'Held load issued before precise IRQ');exits=[x for x in xs if x['event']=='COM_exit'and x['instruction']==e['instruction']and x['cycle']==e['cycle']];need(len(exits)==1 and exits[0]['retired_delta']==0,'IRQ exception must retire no guest instruction');out.append({'held_load':w,'precise_exception':e,'exception_exit':exits[0]})
 need(bool(out),'No actual held-frontier IRQ observed');return out
D=R/'build/C12-pending-base-direct-ON-v2';x=events(D/'cpu.jsonl');sym=symbols(R/'build/C12-pending-base-guest-v1/guest.elf');loadpc=sym['pending_base_load']+8;faultpc=sym['pending_base_fault_load'];load=retry_join(x,loadpc);fault=retry_join(x,faultpc);need(len(load)==577 and len(fault)==1,'All576 hot /one cold /one fault pending-base decisions');need(sum(z['consumer_next_decision']['event']=='rrd_accept'for z in load)==576,'Exactly576 hot loads admitted');need(sum(z['consumer_next_decision']['event']=='candidate_boundary'for z in load)==1,'Resolved cold miss follows original conservative boundary');need(fault[0]['consumer_next_decision']['event']=='candidate_boundary','Misalignment must remain conservative');need(not any(a['event']=='rrd_accept'and a['pc']==faultpc for a in x),'Faulting load speculatively accepted');rows=[list(map(int,l.split()[1:]))for l in(D/'stdout').read_text().splitlines()if l.startswith('PENDING_BASE ')];need(all(rows[h][-1]==faultpc and rows[h][-2]==1 for h in(0,1)),'Actual trap PCs equal exact ELF load address')
I=R/'build/C12-pending-base-IPI-ON-v2';ix=events(I/'cpu.jsonl');irq=irq_join(ix);need(len(irq)==9,'Expected9 actual precise held-load IRQ observations');I1=R/'build/C12-pending-base-IPI-h1-ON-v1';irq1=irq_join(events(I1/'cpu.jsonl'));need(len(irq1)==8,'Expected8 actual hart1 held-load IRQ observations');unknown=[]
for h,n in((0,'C12-pending-base-unknown-h0-ON-v2'),(1,'C12-pending-base-unknown-h1-ON-v3')):
 d=R/'build'/n;elf=R/f'build/C12-pending-base-unknown-h{h}-guest-v2/guest.elf';pc=symbols(elf)['pending_unknown_consumer'];xs=events(d/'cpu.jsonl');j=retry_join(xs,pc);need(len(j)==1 and j[0]['consumer_next_decision']['event']=='candidate_boundary','Partial unknown producer must finish then fall back');need(not any(a['event']=='rrd_accept'and a['pc']==pc for a in xs),'Opaque-EA consumer must never be speculatively admitted');err=(d/'stderr').read_text();need('IRIS_UNDEFINED_STATE hart='+str(h)in err and 'unit=empirical-memory-address'in err,'Original undefined-address refusal');unknown.append({'hart':h,'join':j[0],'run':str(d/'run.json')})
# These adversarial edits violate semantic evidence joins, not the implementation.
negative=[]
for name,kind in(('missing-producer','producer'),('producer-ready-before-wait','early'),('early-consumer','consumer')):
 mutant=copy.deepcopy(x);w=next(a for a in mutant if a['event']=='pending_base_retry'and a['pc']==loadpc);pid=w['instruction']
 if kind=='producer':mutant=[a for a in mutant if not(a['event']=='rrd_accept'and a['instruction']==pid)]
 elif kind=='early':next(a for a in mutant if a['event']=='result_callback'and a['instruction']==pid)['cycle']=w['cycle']
 else:mutant.append({'event':'rrd_accept','pc':loadpc,'cycle':w['cycle'],'instruction':99999999});mutant.sort(key=lambda a:a['cycle'])
 try:retry_join(mutant,loadpc)
 except ValueError:negative.append(name)
 else:raise ValueError('Mutant accepted '+name)
mutant=copy.deepcopy(ix);a=irq[0]['held_load'];mutant.append({'event':'rrd_accept','pc':a['pc'],'cycle':a['cycle']+1,'instruction':99999999})
try:irq_join(mutant)
except ValueError:negative.append('held-load-issued-before-IRQ')
else:raise ValueError('Early IRQ load accepted')
inputs=[Path(__file__),D/'run.json',D/'cpu.jsonl',D/'stdout',I/'run.json',I/'cpu.jsonl',I1/'run.json',I1/'cpu.jsonl',R/'build/C12-pending-base-guest-v1/guest.elf'];inputs += [p for u in unknown for p in (Path(u['run']),Path(u['run']).parent/'cpu.jsonl',Path(u['run']).parent/'stderr',R/f"build/C12-pending-base-unknown-h{u['hart']}-guest-v2/guest.elf")];r={'schema':'iris.C12_pending_base_event_proof.v1','pass':True,'real_older_producer_response_joins':len(load)+len(fault),'known_hot_loads':576,'resolved_cold_miss_fallbacks':1,'precise_fault_after_pending_base':fault,'real_guest_MSIP_interrupts':128,'held_frontier_precise_interrupts':irq+irq1,'partial_unknown_producer_refusals':unknown,'adversarial_trace_refusals':negative,'hardware_contacted':False,'parameter_or_clock_changes':False,'whole_CPU_RTL_timing_certified':False,'input_sha256':{str(p):sha(p)for p in inputs}}
(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');(O/'hot-and-cold-joins.json').write_text(json.dumps(load,indent=2)+'\n');print(json.dumps({'pass':True,'producer_joins':len(load)+len(fault),'precise_held_IRQs':len(irq)+len(irq1),'partial_unknown_refusals':len(unknown),'adversarial_refusals':len(negative),'report_sha256':sha(O/'report.json')}))
