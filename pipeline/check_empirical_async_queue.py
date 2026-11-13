#!/usr/bin/env python3
"""Executed-ELF numeric, two-owner publication and interrupt phase checks."""
import json,pathlib,subprocess,os,time,hashlib
import argparse
R=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--binary',type=pathlib.Path,required=True);p.add_argument('--uart',type=pathlib.Path,required=True);args=p.parse_args();root=args.output.resolve();root.mkdir(exist_ok=False,parents=True);all_two=set()
old=json.load(open(R/'build/empirical-async-two-metrics-v1/selected/report.json'))['argv']
for name,fixture,elf in [('time',R/'build/empirical-async-two-first-v1/two.fixture',R/'build/empirical-time-guest-v2/guest.elf'),('interrupt',R/'build/empirical-async-two-first-v1/two.fixture',R/'build/empirical-async-two-irq-unrolled-guest-v1/guest.elf'),('interrupt-shifted',R/'build/empirical-async-two-first-v1/two.fixture',R/'build/empirical-async-two-irq-shifted-guest-v1/guest.elf'),('long-interrupt',R/'build/empirical-async-two-guards-v1/irq.fixture',R/'build/empirical-async-irq-guest-v1/guest.elf')]:
 o=root/name;o.mkdir();a=[('--iris-timing-trace='+str(o/'summary.json'))if x.startswith('--iris-timing-trace=')else('--iris-timing-fixture='+str(fixture))if x.startswith('--iris-timing-fixture=')else x for x in old];a[0]=str(args.binary.resolve());a=['--extlib='+str(args.uart.resolve())if x.startswith('--extlib=')else x for x in a];a[-1]=str(elf);t=time.monotonic();env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(o/'features.jsonl'),IRIS_EMPIRICAL_ASYNC_TRACE=str(o/'async.jsonl'));p=subprocess.run(a,env=env,capture_output=True,timeout=90);(o/'stdout').write_bytes(p.stdout);(o/'stderr').write_bytes(p.stderr);events=[json.loads(x)for x in(o/'async.jsonl').read_text().splitlines()];begins={(e['hart'],e['backend_node']):e for e in events if e['event']=='begin'};pubs={(e['hart'],e['backend_node']):e for e in events if e['event']=='publish'};cancels={(e['hart'],e['backend_node']):e for e in events if e['event']=='cancel'};handoffs=[]
 assert set(begins)==set(pubs)|set(cancels) and not set(pubs)&set(cancels)
 for key,e in begins.items():
  if key in cancels:continue
  assert pubs[key]['cycle']>=e['com'] and pubs[key]['cycle']>e['ex']
  if 'prior_backend_node'in e:
   prior=(e['hart'],e['prior_backend_node']);assert e['prior_com']<=e['ex'] and e['prior_backend_end']<=e['ex'] and pubs[prior]['cycle']<=e['ex'];handoffs.append(e)
 summary=json.load(open(o/'summary.json'));assert summary['async_owner_limit']==2 and not any(summary['pending_async_backends']);assert p.returncode==0
 defer={e['hart'] for e in events if e['event']=='interrupt_defer' and e['pending']==2}
 pre={e['hart']for e in events if e['event']=='interrupt_pre_completion'and e['pending']==2};all_two|=pre
 if name.startswith('interrupt'):
  fields=[line.split() for line in p.stdout.decode().splitlines()if line.startswith('IRIS_ASYNC_TWO_IRQ ')]
  assert len(fields)==3 and all(int(row[-1])==1027 and int(row[-2])==1 for row in fields),fields
 r={'schema':'iris.empirical.async_two_ledger.v1','pass':True,'argv':a,'binary_sha256':hashlib.sha256(pathlib.Path(a[0]).read_bytes()).hexdigest(),'host_seconds':time.monotonic()-t,'input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in[pathlib.Path(__file__).resolve(),pathlib.Path(a[0]),args.uart.resolve(),fixture,elf,R/'board/evidence/bootrom.rv64.img',R/'board/build/iris.dtb']},'begin_count':len(begins),'publish_count':len(pubs),'cancel_count':len(cancels),'qualified_handoffs':len(handoffs),'all_harts_handoffs':summary['async_handoffs'],'two_pending_during_interrupt_harts':sorted(defer),'two_pending_before_completion_harts':sorted(pre),'source_EX_remains_RRD_plus1':True,'prior_COM_and_actual_publish_by_successor_EX_checked':True,'scope':'model scheduling/numeric temporal invariant, notRTLcyclevalidation'};(o/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(name,r,flush=True);print(p.stdout.decode()[-700:],flush=True)

assert all_two=={0,1,2},all_two
inputs=[pathlib.Path(__file__).resolve(),args.binary.resolve(),args.uart.resolve()]
report={'schema':'iris.empirical.async_two_native_guards.v1','pass':True,'all3_two_pending_on_timer_transition':True,'input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in inputs},'reports':{str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in root.glob('*/report.json')},'timing_certified':False}
(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
