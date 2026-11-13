#!/usr/bin/env python3
"""Qualify completed raw guard executions; shared stream includes nonasync actors."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1];P=R/'build/C12-async-RRD-wake-native-guards-v1';O=R/'build/C12-async-RRD-wake-native-guards-v2';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();reports=[];inputs={str(Path(__file__)):sha(Path(__file__))}
for d in sorted(p.parent for p in P.glob('*/run.json')):
 p=d/'run.json';r=json.loads(p.read_text());assert r['exit_status']==0 and r['timed_out']is False
 for f,h in r['input_sha256'].items():assert sha(f)==h,f
 text=(d/'stdout').read_text();summary=json.loads((d/'summary.json').read_text());assert not any(summary['pending_async_backends'])and summary['async_owner_limit']==2;events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()];beg={(x['hart'],x['backend_node']):x for x in events if x['event']=='begin'};pub={(x['hart'],x['backend_node']):x for x in events if x['event']=='publish'};kill={(x['hart'],x['backend_node']):x for x in events if x['event']=='cancel'};assert set(beg)==set(pub)|set(kill)and not set(pub)&set(kill)
 for k,b in beg.items():
  if k not in pub:continue
  assert pub[k]['cycle']>=b['com']and pub[k]['cycle']>b['ex']
  if 'prior_backend_node'in b:assert b['prior_com']<=b['ex']and b['prior_backend_end']<=b['ex']and pub[b['hart'],b['prior_backend_node']]['cycle']<=b['ex']
 if r['name']=='scalar-no-head':
  rows=[list(map(int,l.split()[1:]))for l in text.splitlines()if l.startswith('PENDING_IPI ')];assert len(rows)==1 and rows[0][:3]==[0,43,64];assert not beg and not pub and not kill;assert not(d/'cpu.jsonl').read_bytes();assert all(x['event']=='load-coherence-fallback-debug'for x in events)
 else:assert r.get('pass')is True
 cpu=[json.loads(x)for x in(d/'cpu.jsonl').read_text().splitlines()];wake=[x for x in cpu if x['event']=='async_RRD_wake'];pending_cycles={x['cycle']for x in cpu if x['event']=='scheduler_advance'and x.get('pending_interrupt')};assert not any(x['cycle']in pending_cycles for x in wake)
 for w in wake:assert w['cycle']<w['retry_edge']<w['old_next_event']and w['retry_edge']==max(w['head_COM'],w['backend_end'])-1
 if r['mode']=='OFF' or r['name']in('short','scalar-no-head'):assert not wake
 reports.append({'name':r['name'],'mode':r['mode'],'pass':True,'normal_guest_exit_verified':True,'published':len(pub),'cancelled_without_publication':len(kill),'actual_future_deadline_shortenings':len(wake),'actual_pending_IRQ_observation_cycles':len(pending_cycles),'raw_run':str(p),'sha256':sha(p)})
 for f in(p,d/'stdout',d/'stderr',d/'summary.json',d/'features.jsonl',d/'async.jsonl',d/'cpu.jsonl'):inputs[str(f)]=sha(f)
for name in('short','scalar-no-head'):
 a,b=[P/(name+s)for s in('-OFF','-ON')]
 for f in('stdout','features.jsonl','async.jsonl'):assert(a/f).read_bytes()==(b/f).read_bytes(),(name,f)
result={'schema':'iris.C12_async_RRD_wake_native_guards.v2','pass':True,'actual_normal_guest_exit_runs':len(reports),'reports':reports,'source_of_v1_auditor_refusal':'The scalar-only guest has4 ordinary load-coherence-fallback-debug records in the shared async.jsonl stream; no async heads/publications/cancellations or wake events exist. V1 incorrectly required the entire mixed-purpose stream to be empty. Raw successful executions remain unchanged.','short_and_scalar_stdout_CSR_async_byte_parity':True,'pending_IRQ_never_shortens_own_deadline':True,'future_aligned_deadlines_only':True,'all_front_owners_publish_or_cancel_once':True,'hardware_contacted':False,'parameters_fitted':False,'timing_certified':False,'input_sha256':inputs};(O/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'runs':len(reports),'report_sha256':sha(O/'report.json')}))
