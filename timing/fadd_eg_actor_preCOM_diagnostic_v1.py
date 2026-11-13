"""Replay exact failing bytes with a new observation-only scope diagnostic."""
from pathlib import Path
import hashlib,json,os,signal,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=ROOT/'build/rvv-compute-asm-FADD-EG-ON-v1';out=ROOT/'build/FADD-EG-preCOM-geometry-diagnostic-v1';out.mkdir(exist_ok=False)
original=json.loads((old/'run.json').read_text());build=ROOT/'build/spike-FADD-EG-observer-v1';meta=json.loads((build/'pipeline-build.json').read_text());argv=[]
for x in original['argv']:
 if x==str(ROOT/'build/FADD-EG-actor-frozen-8f071711-v2/spike'):x=str(build/'spike')
 elif x.startswith('--extlib='):x='--extlib='+str(build/'libsifive_uart.so')
 elif x.startswith('--iris-timing-trace='):x='--iris-timing-trace='+str(out/'summary.json')
 argv.append(x)
env={k:v for k,v in os.environ.items()if not k.startswith('IRIS_EMPIRICAL_')};env['IRIS_EMPIRICAL_FEATURES']=str(out/'features.jsonl')
r=dict(schema='iris.FADD_EG_preCOM_readonly_diagnostic.v1',status='running',hardware_contacted=False,normal_guest_exit_verified=False,argv=argv,
 input_sha256={str(p):sha(p)for p in[Path(__file__).resolve(),old/'run.json',old/'features.jsonl',build/'spike',build/'libsifive_uart.so',build/'pipeline-build.json',Path(meta['source'])/'riscv/iris_fadd_eg_actor.inc']})
def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
save();start=time.monotonic()
with(out/'stdout').open('wb')as so,(out/'stderr').open('wb')as se:
 p=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True);r['owned_pid']=p.pid;save()
 try:r['exit_status']=p.wait(timeout=180);r['timed_out']=False
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGKILL);r['exit_status']=p.wait();r['timed_out']=True
r['host_seconds']=time.monotonic()-start;r['expected_refusal']='IRIS_FADD_EG_FULLVL_HSD_UNMASKED_SCOPE';r['diagnostic']=(out/'stderr').read_text();r['all_pre_failure_CSR_bytes_identical']=(out/'features.jsonl').read_bytes()==(old/'features.jsonl').read_bytes();r['actual_CSR_records']=sum(1 for _ in(out/'features.jsonl').open());r['pass']=not r['timed_out']and r['exit_status']!=0 and r['expected_refusal']in r['diagnostic']and r['all_pre_failure_CSR_bytes_identical'];r['status']='expected_failure_observed'if r['pass']else'diagnostic_failed';save();print(json.dumps({k:r[k]for k in['pass','exit_status','host_seconds','actual_CSR_records','diagnostic']}))
