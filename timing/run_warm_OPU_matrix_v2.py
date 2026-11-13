#!/usr/bin/env python3
"""Actual same-ELF matrix timing prediction; never opens hardware timing labels."""
import argparse,hashlib,json,os,signal,subprocess,time
from pathlib import Path
from iris_model.graph_run_buffered import kill_owned
from benchmarks.pow2_matrix_v1.validate import validate,check_corpus
from timing.memory_routes_current_audit_v2 import Elf
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--timeout',type=int,default=1800);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);b=ROOT/'build/pow2-matrix-single-v2';c=ROOT/'build/warm-OPU-frozen-7108a6ec-v1';fixture=ROOT/'build/warm-OPU-inputs-v2/OPU-ON.fixture';launcher=ROOT/'build/warm-OPU-inputs-v2/spike';elf=b/'matrix.elf';corpus=json.load(open(b/'corpus.json'));check_corpus(corpus,(b/'golden-words.bin').read_bytes());template=ROOT/'build/pow2-matrix-selected-baseline-v2/run.json';old=json.load(open(template));argv=old['argv'][:];argv[0]=str(launcher);argv[-1]=str(elf);argv=[('--extlib='+str(c/'libsifive_uart.so')if x.startswith('--extlib=')else'--iris-timing-fixture='+str(fixture)if x.startswith('--iris-timing-fixture=')else'--iris-timing-trace='+str(o/'summary.json')if x.startswith('--iris-timing-trace=')else x)for x in argv];
 if not any(x.startswith('--iris-timing-trace=')for x in argv):argv.insert(-1,'--iris-timing-trace='+str(o/'summary.json'))
 paths=[Path(__file__).resolve(),b/'build.json',b/'corpus.json',b/'ready.json',b/'golden-words.bin',elf,c/'manifest.json',c/'verification.json',c/'spike',c/'libsifive_uart.so',fixture,launcher,ROOT/'benchmarks/pow2_matrix_v1/validate.py',template]
 inputs={str(p):sha(p)for p in paths};report={'schema':'iris.warm_OPU_pow2_matrix_timed_execution.v1','pass':False,'status':'running','argv':argv,'input_sha256':inputs,'hardware_contacted':False,'timing_reference_consumed':False,'normal_guest_exit_verified':False,'timeout_seconds':a.timeout,'ELF_sha256':sha(elf),'native_binary_sha256':sha(c/'spike'),'fixture_sha256':sha(fixture),'scope':'Inherited effective services plus conditional source OPU queue/entry model; CPU COM+1/FENCE/IRQ limitations; no new fit'}
 def save():(o/'run.json').write_text(json.dumps(report,indent=2)+'\n')
 p=None;t=time.monotonic();save()
 def stop(*unused):raise KeyboardInterrupt('owned local test interrupted')
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGHUP,stop);env=dict(os.environ);env.pop('IRIS_EMPIRICAL_ASYNC_TRACE',None);env.pop('IRIS_FATAL_PCS',None);env['IRIS_EMPIRICAL_FEATURES']=str(o/'features.jsonl')
 try:
  with(o/'stdout').open('wb')as so,(o/'stderr').open('wb')as se:
   p=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True);report['owned_pid']=p.pid;save()
   try:code=p.wait(timeout=a.timeout)
   except subprocess.TimeoutExpired:kill_owned(p);report['timed_out']=True;raise RuntimeError('owned timeout; raw prefix retained')
  report['exit_status']=code
  if code:raise RuntimeError('native scoped refusal/failure; see stderr')
  text=(o/'stdout').read_text();proof=validate(text,corpus);rows=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_REGION ')];features=[json.loads(l)for l in(o/'features.jsonl').read_text().splitlines()];e=Elf(elf);joins=0
  for row in rows:
   for key in('start_cycle','end_cycle'):
    hits=[x for x in features if x['hart']==row['hart']and x['value']==row[key]and x['result_discarded']is False];assert len(hits)==1,'missing/ambiguous actual CSR join';q=hits[0];assert q['csr']==0xb00 and int.from_bytes(e.read(q['pc'],4),'little')==q['raw'];joins+=1
  if any(sha(Path(p))!=h for p,h in inputs.items()):raise RuntimeError('bound execution input changed')
  (o/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');report.update(pass_=True,status='normal_guest_all132_fullword_and_CSR_joins_passed',normal_guest_exit_verified=True,proof=proof,actual_CSR_ELF_joins=joins,fit_parameters_changed=False)
 except (Exception,KeyboardInterrupt)as ex:report.update(status='failed_or_scoped_refusal',error=str(ex))
 finally:
  if p and p.poll()is None:kill_owned(p)
  report['owned_cleanup_complete']=p is None or p.poll()is not None;report['host_seconds']=time.monotonic()-t;report['pass']=report.pop('pass_',False);report['output_sha256']={x.name:sha(x)for x in o.iterdir()if x.is_file()and x.name in('stdout','stderr','features.jsonl','regions.json','summary.json')};save()
 print(json.dumps({k:report.get(k)for k in('pass','status','host_seconds','error','actual_CSR_ELF_joins')}));return 0 if report['pass']else 1
if __name__=='__main__':raise SystemExit(main())
