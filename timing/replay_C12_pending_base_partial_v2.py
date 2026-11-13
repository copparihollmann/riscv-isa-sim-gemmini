#!/usr/bin/env python3
"""Same-ELF first59 debugger readback for isolated pending-base retry; no reference labels."""
import argparse,hashlib,json,os,subprocess,time,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));sys.path.insert(0,str(R/'firesim'))
from iris_model.graph_run_buffered import kill_owned
import rvv_compute1320_review as review
from spike.empirical_launch_v2 import launcher_text
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--on',action='store_true');p.add_argument('--trace-first',type=int);p.add_argument('--trace-last',type=int);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
base=R/'build/RVV-floor-C12-zero-first59-CPU-instrumented-v1';ref=json.loads((base/'run.json').read_text());native=R/'build/spike-C12-pending-base-v1/spike';uart=native.parent/'libsifive_uart.so';launch=o/'spike';launch.write_text(launcher_text(native,sha(native),Path(sys.executable).resolve(),sha(Path(sys.executable).resolve())));launch.chmod(0o755)
fixture=o/'runtime.fixture';raw=(base/'full.fixture').read_bytes();fixture.write_bytes(raw+(b'\nempirical_pending_base_retry h0h1-live-XPR-base-RRD-retry-v1\n'if a.on else b''));cmd=o/'commands.txt';cmd.write_bytes((base/'commands.txt').read_bytes())
argv=[str(launch)if i==0 else '--iris-timing-fixture='+str(fixture)if x.startswith('--iris-timing-fixture=')else '--iris-timing-trace='+str(o/'graph.json')if x.startswith('--iris-timing-trace=')else '--debug-cmd='+str(cmd)if x.startswith('--debug-cmd=')else '--extlib='+str(uart)if x.startswith('--extlib=')else x for i,x in enumerate(ref['argv'])]
env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(o/'features.jsonl'),IRIS_EMPIRICAL_ASYNC_TRACE=str(o/'async.jsonl'));[env.pop(k,None)for k in list(env)if k.startswith('IRIS_CPU_DIAGNOSTIC_')]
if a.trace_first is not None:env.update(IRIS_CPU_DIAGNOSTIC_TRACE=str(o/'cpu.jsonl'),IRIS_CPU_DIAGNOSTIC_FIRST=str(a.trace_first),IRIS_CPU_DIAGNOSTIC_LAST=str(a.trace_last),IRIS_CPU_DIAGNOSTIC_HART='0')
r={'schema':'iris.C12_pending_base_partial.v1','status':'running','mode':'ON'if a.on else'OFF','argv':argv,'hardware_contacted':False,'normal_guest_exit_verified':False,'controlled_postmeasurement_quit':True,'training_or_hardware_labels_read':False,'fixture_cost_bytes_unchanged':True,'input_sha256':{str(x):sha(x)for x in(Path(__file__),native,uart,fixture,cmd,Path(argv[-1]))}};save=lambda:(o/'run.json').write_text(json.dumps(r,indent=2)+'\n');save();start=time.monotonic()
with(o/'stdout').open('wb')as so,(o/'stderr').open('wb')as se:
 child=subprocess.Popen(argv,env=env,stdout=so,stderr=se,start_new_session=True);r['owned_pid']=child.pid;save()
 try:code=child.wait(timeout=120);timed=False
 except subprocess.TimeoutExpired:kill_owned(child);code=child.returncode;timed=True
r.update(exit_status=code,timed_out=timed,host_seconds=time.monotonic()-start,status='execution_finished');save()
if code or timed:raise RuntimeError('partial replay failed')
vals=[int(x,16)for x in(o/'stderr').read_text().splitlines()if x.startswith('0x')];assert len(vals)==59*17+3,len(vals)
corpus=json.loads((R/'build/rvv-compute1320-v2/corpus.json').read_text());can=review.validator().canonical(corpus);old=[json.loads(x)for x in(R/'build/rvv-compute1320-C12-TK124-zero-adjustment-diagnostic-v2/regions.jsonl').read_text().splitlines()][:59];prefix=[json.loads(x)for x in(o/'features.jsonl').read_text().splitlines()];rows=[]
for i in range(59):
 v=vals[17*i:17*(i+1)];assert v[0]==i and v[1]==0 and v[8]==v[9]==can[i]['checksum']and v[10]==0 and v[11]==can[i]['checked_words']and v[12]==can[i]['vl']and v[15]==v[16]==0,(i,v)
 assert v[7]-v[5]==old[i]['instret_delta'],(i,'instret',v[7]-v[5],old[i]['instret_delta'])
 endpoints=[]
 for value in v[2:5]:
  match=[x for x in prefix if x['hart']==0 and x['value']==value];assert len(match)==1,(i,value,len(match));endpoints.append(match[0])
 rows.append({'index':i,'case_id':can[i]['case_id'],'hart':0,'start_cycle':v[2],'issue_cycle':v[3],'end_cycle':v[4],'cycles':v[4]-v[2],'old_cycles':old[i]['end_cycle']-old[i]['start_cycle'],'instret_delta':v[7]-v[5],'begin_global_read_cycle':endpoints[0]['read_cycle'],'drain_global_read_cycle':endpoints[2]['read_cycle']})
if not a.on:
 for name in('stderr','features.jsonl','async.jsonl'):assert (o/name).read_bytes()==(base/name).read_bytes(),name
 r['OFF_record_prefix_async_byte_parity']=True
(o/'rows.json').write_text(json.dumps(rows,indent=2)+'\n');r.update(status='partial59_numeric_and_CSR_joins_passed',pass_=True,completed_rows=59,CSR_endpoint_joins=177,prefix_records=len(prefix),numerical_and_instret_mismatches=0);r['pass']=r.pop('pass_');r['output_sha256']={str(x):sha(x)for x in o.iterdir()if x.is_file()and x.name!='run.json'};save();print(json.dumps({k:r[k]for k in('pass','mode','host_seconds','completed_rows','CSR_endpoint_joins')}))
