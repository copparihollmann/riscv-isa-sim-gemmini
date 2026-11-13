"""Fresh independent parallel runs of eight preserved compiled kernel images."""
import argparse,concurrent.futures,hashlib,importlib.util,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);native,uart,fixture=[p.resolve()for p in(a.binary,a.uart,a.fixture)];vp=ROOT/'integration/iris-mlir/examples/iris/run.py';spec=importlib.util.spec_from_file_location('compiler_goldens',vp);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);cap=native.parent/'manifest.json';m=json.loads(cap.read_text());assert m['artifact_sha256'][native.name]==sha(native)and m['artifact_sha256'][uart.name]==sha(uart)
 ids={str(p):sha(p)for p in(Path(__file__).resolve(),native,uart,fixture,vp,cap)};tasks=[]
 for op in('gemm','conv2d'):
  for workers in(1,2):
   receipt=ROOT/('build/hybrid7bd5-selected-merlin-'+op+'-h'+str(workers)+'-v1/results.json');old=json.loads(receipt.read_text());assert old['pass']is True;ids[str(receipt)]=sha(receipt);mi,ni,ki=old['shape_mnk'];gold_i32,gold_out=v.inputs_and_golden(op,mi,ni,ki)
   for prior in old['runs']:
    elf=Path(prior['argv'][-1]);assert sha(elf)==prior['elf_sha256'];ids[str(elf)]=sha(elf);folder=out/(op+'-h'+str(workers)+'-'+prior['kind']);folder.mkdir();argv=[str(native),*prior['argv'][1:]];argv=['--extlib='+str(uart)if x.startswith('--extlib=')else'--iris-timing-fixture='+str(fixture)if x.startswith('--iris-timing-fixture=')else x for x in argv];assert sum(x.startswith('--iris-timing-fixture=')for x in argv)==1;argv.insert(-1,'--iris-timing-trace='+str(folder/'summary.json'))
    for x in argv:
     if x.startswith(('--iris-bootrom=','--dtb=')):
      p=Path(x.split('=',1)[1]);ids[str(p)]=sha(p)
    tasks.append(dict(index=len(tasks),op=op,workers=workers,kind=prior['kind'],argv=argv,folder=folder,gold_i32=gold_i32,gold_out=gold_out))
 report=dict(schema='iris.parallel_fresh_preserved_compiler_images.v1',passed=False,hardware_contacted=False,fresh_compiler_invocation=False,full_model_or_timing_certified=False,parallel_processes=len(tasks),per_gate_wall_bound_seconds=a.timeout,native_sha256=sha(native),uart_sha256=sha(uart),fixture_sha256=sha(fixture),source_capsule_manifest_sha256=sha(cap),input_sha256=ids,cases=[]);path=out/'report.json'
 def save():path.write_text(json.dumps(report,indent=2)+'\n')
 save()
 def run(t):
  f=t['folder'];env={k:w for k,w in os.environ.items()if not k.startswith('IRIS_EMPIRICAL_')and k!='IRIS_FATAL_PCS'};env['IRIS_EMPIRICAL_FEATURES']=str(f/'features.jsonl');start=time.monotonic();r={k:t[k]for k in('index','op','workers','kind','argv')};r.update(passed=False,normal_guest_exit_verified=False,timed_out=False)
  try:
   with(f/'stdout').open('wb')as so,(f/'stderr').open('wb')as se:
    proc=subprocess.Popen(t['argv'],stdout=so,stderr=se,env=env,start_new_session=True);r['owned_pid']=proc.pid
    try:r['returncode']=proc.wait(timeout=a.timeout)
    except subprocess.TimeoutExpired:
     r['timed_out']=True;os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(timeout=1)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
     r['returncode']=proc.returncode
   if r['returncode']!=0 or r['timed_out']:raise ValueError('Native failed or wall bound reached')
   text=(f/'stdout').read_text();parsed=v.parse(text,len(t['gold_i32']));assert parsed['ACC_I32']==t['gold_i32']and parsed['OUT']==t['gold_out'];regions=[list(map(int,l.split()[1:]))for l in text.splitlines()if l.startswith('REGION ')];assert sorted(row[0]for row in regions)==list(range(t['workers']))and all(len(row)==4 and row[2]>row[1]and row[3]>0 for row in regions);r.update(passed=True,normal_guest_exit_verified=True,accumulator_words=len(t['gold_i32']),w8a8_words=len(t['gold_out']),regions=regions)
  except(Exception)as e:r['error']=str(e)or type(e).__name__
  r['host_seconds']=time.monotonic()-start;r['output_sha256']={str(p):sha(p)for p in f.iterdir()if p.is_file()};(f/'result.json').write_text(json.dumps(r,indent=2)+'\n');return r
 with concurrent.futures.ThreadPoolExecutor(max_workers=8)as pool:
  for future in concurrent.futures.as_completed([pool.submit(run,t)for t in tasks]):report['cases'].append(future.result());report['cases'].sort(key=lambda r:r['index']);save()
 report['inputs_unchanged']=all(sha(p)==h for p,h in ids.items());report['passed']=len(report['cases'])==8 and all(c['passed']for c in report['cases'])and report['inputs_unchanged'];save();print(json.dumps(dict(passed=report['passed'],cases=len(report['cases']),host_seconds=[r['host_seconds']for r in report['cases']])));return 0 if report['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__)
 for k in('binary','uart','fixture','output'):p.add_argument('--'+k,type=Path,required=True)
 p.add_argument('--timeout',type=int,default=300);raise SystemExit(main(p.parse_args()))
