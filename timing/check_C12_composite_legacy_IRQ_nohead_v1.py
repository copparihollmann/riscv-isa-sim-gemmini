#!/usr/bin/env python3
"""Actual ELF short/long, CLINT, squash and scalar-only no-head invariants."""
from pathlib import Path
import json,hashlib,os,subprocess,time,sys,concurrent.futures
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));from iris_model.graph_run_buffered import kill_owned
from spike.empirical_launch_v2 import launcher_text
O=R/'build/C12-source-composite-legacy-IRQ-nohead-guards-v1';O.mkdir();C=R/'build/C12-source-composite-frozen-02b4a9ab-v2';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();base=(R/'build/C12-source-composite-inputs-v1/ownzero-ON.fixture').read_text().replace('empirical_async_rrd_wake h0h1-existing-live-head-eligibility-v1\n','');template=json.loads((R/'build/rvv-compute-asm-C12-ownzero-v1/run.json').read_text())['argv'];cases=[('long-IRQ',10000,R/'build/empirical-async-irq-guest-v1/guest.elf'),('scalar-no-head',0,R/'build/C12-pending-base-IPI-guest-v2/guest.elf')]
def run(item):
 name,extra,elf,on=item;d=O/(name+('-ON'if on else'-OFF'));d.mkdir();lines=[]
 for l in base.splitlines():
  f=l.split()
  if len(f)==10 and f[0]=='empirical_family'and f[2]=='rvv.integer':f[4]=str(extra);f[5]='0';f[7]='SYNTHETIC_MECHANISM_GUARD';l=' '.join(f)
  lines.append(l)
 fixture=d/'runtime.fixture';fixture.write_text('\n'.join(lines)+'\n'+('empirical_async_rrd_wake h0h1-existing-live-head-eligibility-v1\n'if on else''));launcher=d/'spike';launcher.write_text(launcher_text(C/'spike',sha(C/'spike'),Path(sys.executable).resolve(),sha(Path(sys.executable).resolve())));launcher.chmod(0o755)
 argv=[str(launcher)if i==0 else'--iris-timing-fixture='+str(fixture)if x.startswith('--iris-timing-fixture=')else'--iris-timing-trace='+str(d/'summary.json')if x.startswith('--iris-timing-trace=')else'--extlib='+str(C/'libsifive_uart.so')if x.startswith('--extlib=')else str(elf)if i==len(template)-1 else x for i,x in enumerate(template)if x!='-d'and not x.startswith('--debug-cmd=')];env={k:v for k,v in os.environ.items()if not k.startswith(('IRIS_CPU_DIAGNOSTIC_','IRIS_EMPIRICAL_'))};env.update(IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl'),IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'),IRIS_CPU_DIAGNOSTIC_TRACE=str(d/'cpu.jsonl'),IRIS_CPU_DIAGNOSTIC_HART='0',IRIS_CPU_DIAGNOSTIC_EVENTS='async_backend_complete,async_RRD_wake,scheduler_advance,scheduler_arrival');
 if name!='scalar-no-head':env['IRIS_CPU_DIAGNOSTIC_MCYCLEROI']='3'
 r={'schema':'iris.C12_async_RRD_wake_guard_run.v1','status':'running','name':name,'mode':'ON'if on else'OFF','synthetic_setup_cycles':extra,'argv':argv,'input_sha256':{str(p):sha(p)for p in(Path(__file__),C/'spike',C/'libsifive_uart.so',fixture,elf)},'hardware_contacted':False};save=lambda:(d/'run.json').write_text(json.dumps(r,indent=2)+'\n');save();start=time.monotonic()
 with(d/'stdout').open('wb')as so,(d/'stderr').open('wb')as se:
  p=subprocess.Popen(argv,env=env,stdout=so,stderr=se,start_new_session=True);r['owned_pid']=p.pid;save()
  try:code=p.wait(timeout=90);timed=False
  except subprocess.TimeoutExpired:kill_owned(p);code=p.returncode;timed=True
 r.update(exit_status=code,timed_out=timed,host_seconds=time.monotonic()-start,status='process_finished');save();assert code==0 and not timed,(name,on,(d/'stderr').read_text()[:200]);text=(d/'stdout').read_text();summary=json.loads((d/'summary.json').read_text());assert not any(summary['pending_async_backends'])and summary['async_owner_limit']==2
 events=[json.loads(l)for l in(d/'async.jsonl').read_text().splitlines()];beg={(x['hart'],x['backend_node']):x for x in events if x['event']=='begin'};pub={(x['hart'],x['backend_node']):x for x in events if x['event']=='publish'};cancel={(x['hart'],x['backend_node']):x for x in events if x['event']=='cancel'};assert set(beg)==set(pub)|set(cancel)and not set(pub)&set(cancel)
 for k,b in beg.items():
  if k not in pub:continue
  assert pub[k]['cycle']>=b['com']and pub[k]['cycle']>b['ex']
  if 'prior_backend_node'in b:
   prior=b['hart'],b['prior_backend_node'];assert b['prior_com']<=b['ex']and b['prior_backend_end']<=b['ex']and pub[prior]['cycle']<=b['ex']
 if name in('short','long'):
  rows=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_TIME_SENSITIVITY ')];assert len(rows)==3 and all(x['failed']==0 and x['checksum']==280 and x['vl']==8 for x in rows);assert len(cancel)>0,'Actual wrongpath owners must be annulled without publication'
 elif name=='long-IRQ':
  rows=[list(map(int,l.split()[1:]))for l in text.splitlines()if l.startswith('IRIS_ASYNC_IRQ ')];assert len(rows)==3 and all(x[-2:]==[1,4]and x[3]>x[2]>x[1]for x in rows),rows
 elif name=='two-IRQ':
  rows=[list(map(int,l.split()[1:]))for l in text.splitlines()if l.startswith('IRIS_ASYNC_TWO_IRQ ')];assert len(rows)==3 and all(x[-2:]==[1,1027]and x[3]>x[2]>x[1]for x in rows),rows
 else:
  rows=[list(map(int,l.split()[1:]))for l in text.splitlines()if l.startswith('PENDING_IPI ')];assert len(rows)==1 and rows[0][:3]==[0,43,64];assert not beg and not pub and not cancel,'Scalar-only no pending async actor';assert not(d/'cpu.jsonl').read_bytes(),'No async wake or backend event without a head'
 r.update(**{'pass':True},status='passed',normal_guest_exit_verified=True,begins=len(beg),publications=len(pub),cancelled_without_publication=len(cancel),all_pending_owners_closed=True,output_sha256={str(p):sha(p)for p in d.iterdir()if p.is_file()and p.name!='run.json'});save();return d
items=[(*c,on)for c in cases for on in(False,True)]
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
 outputs=list(pool.map(run,items))
for name in('scalar-no-head',):
 a,b=[O/(name+s)for s in('-OFF','-ON')]
 for f in('stdout','features.jsonl','async.jsonl'):assert(a/f).read_bytes()==(b/f).read_bytes(),(name,f)
r={'schema':'iris.C12_composite_legacy_IRQ_nohead_guards.v1','pass':True,'normal_guest_exit_runs':len(outputs),'hardware_contacted':False,'parameters_fitted':False,'scalar_no_head_stdout_CSR_async_byte_parity':True,'all_accepted_front_owners_publish_or_cancel_once':True,'prior_publish_by_successor_EX_verified':True,'IRQ_cases_are_explicit_synthetic_latency_mechanisms_not_hardware_calibration':True,'reports':{str(d/'run.json'):sha(d/'run.json')for d in outputs}};(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'runs':len(outputs),'report_sha256':sha(O/'report.json')}))
