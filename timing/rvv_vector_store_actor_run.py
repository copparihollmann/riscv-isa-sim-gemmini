#!/usr/bin/env python3
"""Finite original-handler VSE32 actor: actual ELF numeric/lease/ACK guards."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);native=R/'build/rvv-vector-store-actor-native-v1';parent=R/'build/warm-OPU-inputs-v2/baseline.fixture';template=json.loads((R/'build/saturn-native-first-v2/results.json').read_text())['argv'];reports=[]
 cases=[('positive',h,seed,20)for h in range(3)for seed in[0,17]]+[('positive',h,0,200)for h in range(3)]+[('IRQ',0,0,20),('busy-peer',0,0,20),('pending-IRQ',0,0,20),('killed',0,0,20),('killed',0,17,20)]
 for kind,h,seed,ack in cases:
  d=o/(kind+'-h'+str(h)+'-seed'+str(seed)+'-ACK'+str(ack));d.mkdir();fixture=d/'actor.fixture';fixture.write_text(parent.read_text().replace('iris-source-warm-OPU-7108-baseline-v2','iris-VSE32-actor-SYNTHETIC-ACK'+str(ack)+'-h'+str(h))+'\nempirical_vector_store_actor finite-VSE32-single-hart-v1 '+str(h)+' 3 3 '+str(ack)+' 1 core_edges\n');elf=R/('build/rvv-store-actor-guest-'+('h'+str(h)if kind=='positive'else kind)+'-v2/guest.elf');argv=[]
  for arg in template:
   if arg==template[0]:arg=str(native/'spike')
   elif arg.startswith('--extlib='):arg='--extlib='+str(native/'libsifive_uart.so')
   elif arg.startswith('--iris-timing-fixture='):arg='--iris-timing-fixture='+str(fixture)
   elif arg.startswith('--iris-timing-trace='):arg='--iris-timing-trace='+str(d/'summary.json')
   elif arg==template[-1]:arg=str(elf)
   argv.append(arg)
  argv.insert(-1,'--iris-schedule-seed='+str(seed));env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl'));start=time.perf_counter();timed=False
  with(d/'stdout').open('w')as so,(d/'stderr').open('w')as se:
   try:r=subprocess.run(argv,env=env,stdout=so,stderr=se,timeout=90);code=r.returncode
   except subprocess.TimeoutExpired:code=None;timed=True
  stdout=(d/'stdout').read_text();stderr=(d/'stderr').read_text();events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()]if(d/'async.jsonl').exists()else[];front=[x for x in events if x.get('event')=='VSE_actor_front_COM'];reads=[x for x in events if x.get('event')=='VSE_actor_VRF_read'];A=[x for x in events if x.get('event')=='VSE_actor_A_beat'];D=[x for x in events if x.get('event')=='VSE_actor_ACK_publish'];checks=[]
  if kind in['positive','killed']:
   rows=[json.loads(x.split(' ',1)[1])for x in stdout.splitlines()if x.startswith('IRIS_VSE_ACTOR {')];req=64 if h<2 else 32;beats=64 if h<2 else 128
   checks=[not timed and code==0,len(rows)==1 and rows[0]['hart']==h and rows[0]['checked_words']==256 and rows[0]['mismatch_or']==0 and rows[0]['checksum']==1152,'IRIS_VSE_ACTOR_DONE'in stdout,len(front)==4,len(reads)==req,len(A)==beats,len(D)==req,sum(x['bytes']for x in D)==1024]
   if rows and D:
    prefixes=[json.loads(x)for x in(d/'features.jsonl').read_text().splitlines()];endpoints=[x for x in prefixes if x['hart']==h and x['value']==rows[0]['fence_end']];checks +=[len(endpoints)==1 and endpoints[0]['read_cycle']>=max(x['cycle']for x in D),rows[0]['issue_end']<rows[0]['fence_end']]
    # Guestmcycle offsets afterbootWFI mustnever beequatedtoglobalgraphclock.
   # No nearest-PC join: command IDs originate at actual original-handler COM.
   for c in front:
    rr=[x for x in reads if x['command']==c['command']];dd=[x for x in D if x['command']==c['command']];aa=[x for x in A if x['command']==c['command']]
    if not(rr and dd and aa):checks.append(False);continue
    checks +=[rr[0]['cycle']>=c['cycle']+3,rr[-1]['cycle']<dd[-1]['cycle'],min(x['cycle']for x in aa)>=rr[0]['cycle']+2]
   for first,second in zip(front,front[1:]):checks +=[second['cycle']>max(x['cycle']for x in reads if x['command']==first['command'])]
   peak=0;owned=set()
   for t in sorted({x['cycle']for x in A+D}):
    for x in D:
     if x['cycle']==t:checks.append(x['tag']in owned);owned.discard(x['tag'])
    for x in A:
     if x['cycle']==t and x['beat']==0:checks.append(x['tag']not in owned);owned.add(x['tag'])
    peak=max(peak,len(owned))
   checks +=[not owned,peak<=(16 if h<2 else 32),sum(x['beat_payload_bytes']for x in A)==1024]
   for ackrow in D:
    accepted=[x for x in A if x['command']==ackrow['command']and x['tag']==ackrow['tag']and x['cycle']<ackrow['cycle']];checks.append(bool(accepted)and ackrow['cycle']-max(x['cycle']for x in accepted)==ack)
  else:
   expected={'IRQ':'IRIS_VSE_ACTOR_GLOBAL_IRQ_ENABLE_UNSUPPORTED','busy-peer':'IRIS_VSE_ACTOR_PEER_NOT_QUIET','pending-IRQ':'IRIS_VSE_ACTOR_PENDING_INTERRUPT_UNSUPPORTED'}[kind];checks=[not timed,code not in[None,0],expected in stderr,not D,'IRIS_VSE_ACTOR_DONE'not in stdout]
  passed=all(checks);inputs=[Path(__file__),native/'spike',native/'libsifive_uart.so',fixture,elf,R/'board/build/iris.dtb',R/'board/evidence/bootrom.rv64.img'];rep=dict(schema='iris.finite_VSE32_actor_execution.v1',status='passed'if passed else'failed',kind=kind,hart=h,seed=seed,synthetic_ACK_edges=ack,checks=len(checks),failed_checks=[i for i,x in enumerate(checks)if not x],argv=argv,env={'IRIS_EMPIRICAL_ASYNC_TRACE':str(d/'async.jsonl')},exit_status=code,timed_out=timed,host_seconds=time.perf_counter()-start,macro_COMs=len(front),VRF_reads=len(reads),A_beats=len(A),ACKs=len(D),input_sha256={str(x):sha(x)for x in inputs},output_sha256={str(x):sha(x)for x in d.iterdir()if x.is_file()});(d/'run.json').write_text(json.dumps(rep,indent=2)+'\n');reports.append(rep)
 report=dict(schema='iris.finite_VSE32_actor_gates.v1',status='passed'if all(x['status']=='passed'for x in reports)else'failed',runs=reports,physical_harts=3,source_StoreSequencer_qualified=True,CPU_VU_join_qualified=False,ACK_service='EXPLICIT SYNTHETIC20/200coreedges, not physical calibration',whole_SoC_or_2pct_claim=False,hardware_contacted=False,reserved_hardware_labels_consumed=False);(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report_sha256':sha(o/'report.json')}));raise SystemExit(0 if report['status']=='passed'else 2)
if __name__=='__main__':main()
