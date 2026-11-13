"""Execute an ELF with a provider-checked model and an exact history-only override.

The full graph is observability, not a different calibration or a certificate.
Original provider, native, fatal launcher, costs and calibrated inputs remain
verified and unchanged. No provider manifest or existing fixture is rewritten.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from .empirical_run import checked_inputs, descriptor, load

ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()


def derive_history(parent,history):
 if type(parent)is not bytes or history not in('bounded','full'):raise ValueError('Exact parent bytes and supported history required')
 matches=list(re.finditer(rb'^empirical_profile [^\s]+ [^\s]+ (bounded)(?=\r?$)',parent,re.M))
 if len(matches)!=1:raise ValueError('Unique bounded empirical profile declaration required')
 match=matches[0];start,end=match.span(1)
 result=parent[:start]+history.encode()+parent[end:]
 if result[:start]!=parent[:start]or result[start+len(history):]!=parent[end:]:raise ValueError('History-only derivation failed')
 return result,{'changed_token':'empirical_profile history','parent_token':'bounded','job_token':history,
  'parent_byte_offset':start,'all_other_bytes_identical':True,'parameters_changed':False,'calibration_identity_changed':False}


def kill_owned(proc):
 if proc is None or proc.returncode is not None:return
 # Keep the leader unreaped until both signals, avoiding process-group reuse.
 try:os.killpg(proc.pid,signal.SIGTERM)
 except ProcessLookupError:pass
 time.sleep(.2)
 try:os.killpg(proc.pid,signal.SIGKILL)
 except ProcessLookupError:pass
 proc.wait()


def run(elf,manifest,output,layout_path,timeout=120,seed=0,history='full'):
 if type(timeout)not in(int,float)or not math.isfinite(timeout)or not 0<timeout<=86400:raise ValueError('Finite positive bounded wall timeout required')
 if type(seed)is not int or not 0<=seed<1<<64:raise ValueError('Unsigned scheduling seed required')
 elf,manifest,output=(Path(x).resolve()for x in(elf,manifest,output));output.mkdir(parents=True,exist_ok=False)
 receipt={'schema':'iris.provider_checked_full_graph_ELF_execution.v1','pass':False,'status':'preflight','history':history,
  'hardware_contacted':False,'global_heldout_timings_consumed':False,'timing_accuracy_certified':False,'full_model_certified':False,
  'independent_numeric_validation':None,'physical_harts':3,'started_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 def save():
  tmp=output/'.run.json.tmp';tmp.write_text(json.dumps(receipt,indent=2)+'\n');tmp.replace(output/'run.json')
 save();start=time.monotonic();proc=None;inputs={}
 try:
  model=descriptor(manifest)
  if model.get('automatic_fatal_handler_resolution')is not True:raise ValueError('Verified fatal-aware provider launcher required')
  per=model.get('per_hart_isa',{});memory=model.get('memory_regions')
  if set(per)!={'0','1','2'}or any(not isinstance(v,str)or not v for v in per.values()):raise ValueError('All three exact heterogeneous ISA declarations required')
  if(not isinstance(memory,list)or not memory or any(not isinstance(r,(list,tuple))or len(r)!=2 or any(type(x)is not int for x in r)or r[0]<0 or r[1]<=0 for r in memory)):raise ValueError('Provider real memory map required')
  inputs=dict(model.get('execution_input_sha256',{}));launch=list(model['launch_args'])
  indices=[i for i,x in enumerate(launch)if isinstance(x,str)and x.startswith('--iris-timing-fixture=')]
  if len(indices)!=1:raise ValueError('Unique provider-bound fixture required')
  index=indices[0];parent=Path(launch[index].split('=',1)[1]).resolve()
  if inputs.get(str(parent))!=sha(parent):raise ValueError('Parent fixture must match the provider input closure')
  raw=parent.read_bytes();child,derivation=derive_history(raw,history);job=output/'job.fixture';job.write_bytes(child)
  launch[index]='--iris-timing-fixture='+str(job)
  layout_path=Path(layout_path).resolve();layout=load(layout_path)
  from timing.memory_routes_current_audit_v2 import Elf
  actual=Elf(elf)
  if layout.get('schema')!='iris.short_VME_profile_readback.v1'or layout.get('elf_sha256')!=sha(elf)or layout.get('rows')!=6 or layout.get('row_stride')!=64:raise ValueError('Exact declared profile layout required')
  for name,size in [('profile_measurements_done',8),('profile_rows',384),('profile_words',768)]:
   entry=layout['objects'][name]
   if type(entry['address'])is not int or entry['size']!=size or actual.symbol(name)!=(entry['address'],size):raise ValueError('ELF buffered object mismatch')
  address=lambda name:layout['objects'][name]['address']
  if actual.read(address('profile_measurements_done'),8)!=b'\xff'*8:raise ValueError('Known completion sentinel required')
  commands=['rs 0',f'while mem {address("profile_measurements_done"):x} ffffffffffffffff',f'mem {address("profile_measurements_done"):x}']
  commands += [f'mem {address("profile_rows")+row*64+field*8:x}'for row in range(6)for field in range(4)]
  commands += [f'mem {word:x}'for word in range(address('profile_words'),address('profile_words')+768,8)]
  commands += [f'mem {address("profile_measurements_done"):x}','rs']
  command_path=output/'readback.commands';command_path.write_text('\n'.join(commands)+'\n')
  for path in(manifest,elf,Path(__file__).resolve(),ROOT/'iris_model/empirical_run.py',ROOT/'timing/memory_routes_current_audit_v2.py',layout_path,command_path,job):
   value=sha(path)
   if str(path)in inputs and inputs[str(path)]!=value:raise ValueError('Conflicting input identity')
   inputs[str(path)]=value
  checked_inputs(inputs)
  argv=[model['binary'],'-d','--debug-cmd='+str(command_path),'--isa='+per['2'],'-p3','-m'+','.join(f'{b:#x}:{n:#x}'for b,n in memory),*launch,
    *('--hart-isa='+str(h)+':'+per[str(h)]for h in range(3)),'--iris-schedule-seed='+str(seed),
    '--iris-timing-trace='+str(output/'graph.json'),str(elf)]
  environment=dict(os.environ);environment.pop('IRIS_EMPIRICAL_ASYNC_TRACE',None);environment['IRIS_EMPIRICAL_FEATURES']=str(output/'features.jsonl')
  receipt.update(status='running',argv=argv,ELF_sha256=sha(elf),manifest_sha256=sha(manifest),
    native_binary_sha256=model.get('native_binary_sha256'),launcher_sha256=model['binary_sha256'],
    parent_fixture=str(parent),parent_fixture_sha256=sha(parent),fixture_sha256=sha(job),history_derivation=derivation,
    post_ROI_debugger_observation_then_resume=True,debug_commands_end='unbounded silent run; no quit command',readback_layout=str(layout_path),
    calibration_identity=load(manifest)['calibration_identity'],input_sha256=inputs,
    environment={k:v for k,v in environment.items()if k.startswith('IRIS_')or k.startswith('LD_')},timeout_seconds=timeout,schedule_seed=seed)
  save()
  with(output/'stdout').open('wb')as stdout,(output/'stderr').open('wb')as stderr:
   proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=environment,start_new_session=True);receipt['owned_child_pid']=proc.pid;save()
   try:code=proc.wait(timeout=timeout);timed=False
   except(subprocess.TimeoutExpired,KeyboardInterrupt):kill_owned(proc);code=proc.returncode;timed=True
  checked_inputs(inputs);receipt.update(exit_status=code,timed_out=timed,owned_process_cleanup_complete=proc.returncode is not None,
    status='passed_guest_exit'if code==0 and not timed else'failed_guest_exit',**{'pass':code==0 and not timed})
 except(Exception,KeyboardInterrupt)as error:
  receipt.update(status='refused_or_failed',error=str(error),**{'pass':False})
 finally:
  if proc is not None and proc.returncode is None:kill_owned(proc)
  receipt['host_seconds']=time.monotonic()-start;receipt['owned_process_cleanup_complete']=proc is None or proc.returncode is not None
  receipt['output_sha256']={str(p):sha(p)for p in(output/'stdout',output/'stderr',output/'features.jsonl',output/'graph.json')if p.is_file()}
  save()
 return receipt


def main():
 def interrupted(signum,frame):raise KeyboardInterrupt('Interrupted by signal '+str(signum))
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
 p=argparse.ArgumentParser(__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--layout',type=Path,required=True);p.add_argument('--model',type=Path,default=ROOT/'spike/empirical-current/manifest.json');p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,default=120);p.add_argument('--seed',type=int,default=0);p.add_argument('--history',choices=('bounded','full'),default='full');a=p.parse_args()
 r=run(a.elf,a.model,a.output,a.layout,a.timeout,a.seed,a.history);print(json.dumps({k:r.get(k)for k in('pass','status','exit_status','timed_out','host_seconds','error')}));return 0 if r['pass']else 1


if __name__=='__main__':raise SystemExit(main())
