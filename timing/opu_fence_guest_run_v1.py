#!/usr/bin/env python3
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from iris_model.graph_run_buffered import kill_owned
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--build',required=True);ap.add_argument('--output',required=True);ap.add_argument('--parent-run',required=True);ap.add_argument('--seed',type=int,required=True);ap.add_argument('--timeout',type=float,default=180);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);b=Path(a.build).resolve();j=json.load(open(b/'build.json'));parent=Path(a.parent_run).resolve();argv=json.load(open(parent))['argv'][:];argv[-1]=str(b/'guest.elf');assert sha(b/'guest.elf')==j['ELF_sha256']
 obj=j['objects'];cmd=['rs 0',f'while mem {obj["opu_fence_done"]["address"]:x} ffffffffffffffff']
 for n in ('opu_fence_done','opu_fence_errors','opu_fence_cases','opu_fence_words','opu_fence_counters'):
  s=obj[n];cmd +=[f'mem {v:x}'for v in range(s['address'],s['address']+s['size'],8)]
 cmd +=['rs'];commands=o/'commands';commands.write_text('\n'.join(cmd)+'\n');argv=['--debug-cmd='+str(commands)if x.startswith('--debug-cmd=')else '--iris-timing-trace='+str(o/'summary.json')if x.startswith('--iris-timing-trace=')else '--iris-schedule-seed='+str(a.seed)if x.startswith('--iris-schedule-seed=')else x for x in argv]
 env=dict(os.environ)
 for n in('IRIS_EMPIRICAL_FEATURES','IRIS_EMPIRICAL_ASYNC_TRACE','IRIS_FATAL_PCS'):env.pop(n,None)
 env['IRIS_EMPIRICAL_ASYNC_TRACE']=str(o/'async.jsonl');env['IRIS_EMPIRICAL_FEATURES']=str(o/'features.jsonl')
 ins={str(p.resolve()):sha(p)for p in(Path(__file__),b/'build.json',b/'guest.elf',parent,commands,Path(argv[0]))}
 for v in argv:
  if v.startswith(('--extlib=','--iris-timing-fixture=','--iris-bootrom=','--dtb=')):
   f=Path(v.split('=',1)[1]);ins[str(f)]=sha(f)
 report={'schema':'iris.opu_fence_finite_guest_run.v1','pass':False,'status':'running','argv':argv,'seed':a.seed,'environment':{'IRIS_EMPIRICAL_ASYNC_TRACE':env['IRIS_EMPIRICAL_ASYNC_TRACE'],'IRIS_EMPIRICAL_FEATURES':env['IRIS_EMPIRICAL_FEATURES']},'input_sha256':ins,'hardware_contacted':False};start=time.monotonic();proc=None
 def save():(o/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  with(o/'stdout').open('wb')as so,(o/'stderr').open('wb')as se:
   proc=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True);report['owned_pid']=proc.pid;save()
   try:code=proc.wait(timeout=a.timeout)
   except subprocess.TimeoutExpired:kill_owned(proc);raise RuntimeError('owned bounded timeout')
  report['exit_status']=code
  if code or(o/'stdout').read_text()!='OPU_FENCE_PASS\n':raise RuntimeError('normal numerical/HTIF banner/exit missing')
  lines=[v for v in(o/'stderr').read_text().splitlines()if v!=':']
  if any(not v.startswith('0x')or len(v)!=18 for v in lines):raise RuntimeError('unexpected diagnostic readback')
  values=[int(v,16)for v in lines]
  if values[:3]!=[0,0,16]:raise RuntimeError('done/errors/cases mismatch')
  words=[w for v in values[3:3+65536//2]for w in(v&0xffffffff,v>>32)]
  expected=[(0x41800000 if fp else 96)for h in range(2)for fp in range(2)for f in range(4)for t in range(4)for row in range(32)for col in range(32)]
  if words!=expected:raise RuntimeError('independent full-MRF INT8/FP8 mismatch')
  counters=values[3+65536//2:]
  if len(counters)!=16 or any(v<=0 for v in counters):raise RuntimeError('actual following-CSR counters missing')
  admissions=[];trace_count=0
  for l in(o/'async.jsonl').open():
   t=json.loads(l);trace_count+=1
   if t['event']=='opu_fence_admit':admissions.append(t)
  sites={v['pc']:v['raw']for v in j['barrier_sites'].values()}
  if any(t['pc']in sites and sites[t['pc']]not in(0x0330000f,0x0ff0000f)for t in admissions):raise RuntimeError('excluded barrier admitted by narrow mode')
  report.update(pass_=True,status='normal_HTIF_and_all_finite_numerics_passed',normal_HTIF_guest_exit=True,numeric_words=len(words),cases=16,actual_CSR_counters=counters,async_events=trace_count,source_FM0_tail_admissions=admissions)
 except Exception as e:report.update(status='failed',error=str(e))
 finally:
  if proc is not None and proc.poll()is None:kill_owned(proc)
  report['host_seconds']=time.monotonic()-start;report['pass']=report.pop('pass_',False)
  for n in('stdout','stderr','summary.json','async.jsonl','features.jsonl'):
   f=o/n
   if f.exists():report.setdefault('output_sha256',{})[str(f)]=sha(f)
  for n,d in ins.items():
   if sha(Path(n))!=d:report['pass']=False;report['status']='failed';report['error']='input changed during execution: '+n
  save()
 print(json.dumps({k:report.get(k)for k in('pass','status','error','normal_HTIF_guest_exit','numeric_words','host_seconds')}));return 0 if report['pass']else 1
if __name__=='__main__':raise SystemExit(main())
