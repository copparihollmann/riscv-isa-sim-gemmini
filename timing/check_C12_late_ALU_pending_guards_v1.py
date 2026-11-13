#!/usr/bin/env python3
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));from iris_model.graph_run_buffered import kill_owned
from spike.empirical_launch_v2 import launcher_text
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--on',action='store_true');ap.add_argument('--elf',type=Path,default=R/'build/C12-pending-base-guest-v1/guest.elf');ap.add_argument('--expect-refusal',action='store_true');ap.add_argument('--trace-first',type=int,default=0);ap.add_argument('--trace-last',type=int,default=500000);ap.add_argument('--trace-hart',type=int,choices=(0,1),default=0);a=ap.parse_args();O=a.output.resolve();O.mkdir(parents=True);N=R/'build/spike-C12-late-ALU-v1';F=R/'build/C12-late-ALU-inputs-v1'/('ON.fixture'if a.on else'OFF.fixture');launch=O/'spike';launch.write_text(launcher_text(N/'spike',sha(N/'spike'),Path(sys.executable).resolve(),sha(Path(sys.executable).resolve())));launch.chmod(0o755)
ref=json.loads((R/'build/C12-pending-base-OFF-first59-v2/run.json').read_text());argv=[str(launch)if i==0 else'--iris-timing-fixture='+str(F)if x.startswith('--iris-timing-fixture=')else'--iris-timing-trace='+str(O/'graph.json')if x.startswith('--iris-timing-trace=')else'--extlib='+str(N/'libsifive_uart.so')if x.startswith('--extlib=')else str(a.elf.resolve())if i==len(ref['argv'])-1 else x for i,x in enumerate(ref['argv'])if x!='-d'and not x.startswith('--debug-cmd=')];env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(O/'features.jsonl'),IRIS_CPU_DIAGNOSTIC_TRACE=str(O/'cpu.jsonl'),IRIS_CPU_DIAGNOSTIC_FIRST=str(a.trace_first),IRIS_CPU_DIAGNOSTIC_LAST=str(a.trace_last),IRIS_CPU_DIAGNOSTIC_HART=str(a.trace_hart));r={'schema':'iris.C12_pending_base_native_check.v1','status':'running','mode':'ON'if a.on else'OFF','argv':argv,'input_sha256':{str(x):sha(x)for x in(Path(__file__),N/'spike',N/'libsifive_uart.so',F,a.elf.resolve())},'hardware_contacted':False};save=lambda:(O/'run.json').write_text(json.dumps(r,indent=2)+'\n');save();start=time.monotonic()
with(O/'stdout').open('wb')as so,(O/'stderr').open('wb')as se:
 p=subprocess.Popen(argv,env=env,stdout=so,stderr=se,start_new_session=True);r['owned_pid']=p.pid;save()
 try:c=p.wait(timeout=90);timed=False
 except subprocess.TimeoutExpired:kill_owned(p);c=p.returncode;timed=True
r.update(exit_status=c,timed_out=timed,host_seconds=time.monotonic()-start);save()
if a.expect_refusal:
 text=(O/'stderr').read_text();r['pass']=not timed and c!=0 and ('UNDEFINED' in text or 'unknown' in text.lower());r['normal_guest_exit_verified']=False
else:
 rows=[list(map(int,x.split()[1:]))for x in(O/'stdout').read_text().splitlines()if x.startswith('PENDING_BASE ')];assert len(rows)==3,rows
 for h,row in enumerate(rows):assert row==([h,0,43+h,99+h,1,1,row[-1]]if h<2 else[2,0,0,0,0,0,0]),row
 assert rows[0][-1]==rows[1][-1] and rows[0][-1]>0;assert c==0 and not timed,(c,timed);r.update(**{'pass':True},normal_guest_exit_verified=True,independent_numeric_harts=3,precise_expected_load_faults=2,timer_interrupts=2)
r['status']='passed'if r['pass']else'failed';r['output_sha256']={str(x):sha(x)for x in O.iterdir()if x.is_file()and x.name!='run.json'};save();print(json.dumps({k:r[k]for k in('pass','mode','host_seconds','exit_status')}));assert r['pass']
