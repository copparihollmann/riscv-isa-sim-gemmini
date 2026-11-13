#!/usr/bin/env python3
"""Execute actual VSE32 original-handler COM quarantine and refusal controls."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);native=R/'build/rvv-vector-store-native-build-v1';parent=R/'build/warm-OPU-inputs-v2/baseline.fixture';text=parent.read_text().replace('iris-source-warm-OPU-7108-baseline-v2','iris-VSE32-COM-quarantine-v1')+'\nempirical_vector_store_capture guard-Mbare-VSE32-COM-selfcheck-v1\n';fixture=o/'capture.fixture';fixture.write_text(text)
 template=json.loads((R/'build/saturn-native-first-v2/results.json').read_text())['argv'];reports=[]
 for kind in ['positive','undefined','masked']:
  for seed in([0,17]if kind=='positive'else[0]):
   d=o/(kind+'-seed'+str(seed));d.mkdir();elf=R/('build/rvv-store-capture-'+kind+'-v1/guest.elf');argv=[]
   for arg in template:
    if arg==template[0]:arg=str(native/'spike')
    elif arg.startswith('--extlib='):arg='--extlib='+str(native/'libsifive_uart.so')
    elif arg.startswith('--iris-timing-fixture='):arg='--iris-timing-fixture='+str(fixture)
    elif arg.startswith('--iris-timing-trace='):arg='--iris-timing-trace='+str(d/'summary.json')
    elif arg==template[-1]:arg=str(elf)
    argv.append(arg)
   argv.insert(-1,'--iris-schedule-seed='+str(seed))
   env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'));started=time.perf_counter();timeout=False
   with(d/'stdout').open('w')as so,(d/'stderr').open('w')as se:
    try:r=subprocess.run(argv,env=env,stdout=so,stderr=se,timeout=90);status=r.returncode
    except subprocess.TimeoutExpired:status=None;timeout=True
   stdout=(d/'stdout').read_text();stderr=(d/'stderr').read_text();events=[]
   if(d/'async.jsonl').exists():events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()if x.startswith('{')and'VSE32_COM_quarantine_publish'in x]
   if kind=='positive':
    rows=[json.loads(x.split(' ',1)[1])for x in stdout.splitlines()if x.startswith('IRIS_VSE_CAPTURE {')]
    passed=not timeout and status==0 and len(rows)==3 and {x['hart']for x in rows}=={0,1,2}and all(x['checked_words']==448 and x['mismatch_or']==0 for x in rows)and'IRIS_VSE_CAPTURE_DONE'in stdout and len(events)==21 and sum(x['words']for x in events)==381
   else:
    diagnostic='IRIS_VSE_CAPTURE_UNDEFINED_VRF_SOURCE'if kind=='undefined'else'IRIS_VSE_CAPTURE_REQUIRES_UNMASKED_UNITSTRIDE_NF1_VSE32'
    passed=not timeout and status not in[None,0]and diagnostic in stderr and'IRIS_VSE_CAPTURE_DONE'not in stdout
   inputs=[Path(__file__),native/'spike',native/'libsifive_uart.so',fixture,elf,Path(argv[-4].split('=',1)[-1])if argv[-4].startswith('--dtb=')else R/'board/build/iris.dtb',R/'board/evidence/bootrom.rv64.img']
   rep=dict(schema='iris.VSE32_COM_quarantine_execution.v1',status='passed'if passed else'failed',kind=kind,seed=seed,argv=argv,env={'IRIS_EMPIRICAL_ASYNC_TRACE':env['IRIS_EMPIRICAL_ASYNC_TRACE'],'schedule_seed_transport':'actual --iris-schedule-seed='+str(seed)},exit_status=status,timed_out=timeout,host_seconds=time.perf_counter()-started,captured_commands=len(events),captured_words=sum(x['words']for x in events),input_sha256={str(x):sha(x)for x in inputs},output_sha256={str(x):sha(x)for x in d.iterdir()if x.is_file()});(d/'run.json').write_text(json.dumps(rep,indent=2)+'\n');reports.append(rep)
 report=dict(schema='iris.VSE32_COM_quarantine_gate.v1',status='passed'if all(x['status']=='passed'for x in reports)else'failed',runs=reports,physical_harts=3,CPU_timing_changed=False,early_COM=False,ACK_timing_or_visibility_qualified=False,unmodified_original_VSE_handler=True,hardware_contacted=False,reserved_hardware_timings_consumed=False);(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report_sha256':sha(o/'report.json')}));raise SystemExit(0 if report['status']=='passed'else 2)
if __name__=='__main__':main()
