#!/usr/bin/env python3
"""Describe/verify a source-controller experiment; no calibrated provider fallback."""
import argparse, hashlib, json, math, os, re, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.empirical_provider_v4 import document
from iris_model.graph_run_buffered import kill_owned

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def checked(path,expected):
 path=Path(path)
 if not path.is_absolute()or not path.is_file()or not isinstance(expected,str)or not re.fullmatch('[a-f0-9]{64}',expected)or sha(path)!=expected:raise ValueError('IRIS_SOURCE_OPU_INPUT_IDENTITY_MISMATCH '+str(path))
 return path
def verify(path,expected):
 path=checked(Path(path).resolve(),expected);m=document(path)
 if m.get('schema')!='iris.source_OPU_developer_package.v1'or m.get('ready')is not True:raise ValueError('IRIS_SOURCE_OPU_PACKAGE_SCHEMA')
 if m.get('calibrated_provider_available')is not False or m.get('default_selection_changed')is not False:raise ValueError('IRIS_SOURCE_OPU_CALIBRATION_SCOPE')
 for n,h in m['input_sha256'].items():checked(n,h)
 for name in('native','UART','launcher','bootrom','dtb'):
  role=m['roles'][name]
  if m['input_sha256'].get(role['path'])!=role['sha256']:raise ValueError('IRIS_SOURCE_OPU_ROLE_BINDING '+name)
 for mode in('off','tk124'):
  role=m['fixtures'][mode]
  if m['input_sha256'].get(role['path'])!=role['sha256']:raise ValueError('IRIS_SOURCE_OPU_FIXTURE_BINDING')
  text=Path(role['path']).read_text();lines=[x.split()for x in text.splitlines()if x.startswith('empirical_profile ')]
  if len(lines)!=1 or len(lines[0])!=4 or lines[0][1]!='experimental-effective-services'or lines[0][3]!='bounded':raise ValueError('IRIS_SOURCE_OPU_HISTORY_SCOPE')
  opu=[x for x in text.splitlines()if x.startswith('empirical_opu_entry ')]
  if (mode=='off'and opu)or(mode=='tk124'and opu!=['empirical_opu_entry source-VDQ4-IQ3-entry-MM-TK124-COMplus1-v3']):raise ValueError('IRIS_SOURCE_OPU_MODE_BINDING')
 return m
def descriptor(m,mode):
 return {'schema':'iris.source_OPU_developer_descriptor.v1','available_for_explicit_native_experiment':True,'calibrated_provider_available':False,'calibrated_provider_refusal':'IRIS_SOURCE_OPU_CALIBRATED_PROVIDER_UNAVAILABLE: own native/mode timing replay and runtime binding absent','mode':mode,'native_binary_sha256':m['roles']['native']['sha256'],'UART_sha256':m['roles']['UART']['sha256'],'fixture':m['fixtures'][mode],'capabilities':m['capabilities'],'limitations':m['limitations'],'whole_CPU_timing_certified':False,'source_image_association':False,'timing_2pct_certified':False}
def run(m,mode,elf,out,timeout,seed,manifest_path,manifest_sha):
 if type(timeout)not in(int,float)or not math.isfinite(timeout)or not 0<timeout<=1800:raise ValueError('Finite positive timeout <=1800 required')
 if type(seed)is not int or not 0<=seed<2**32:raise ValueError('Unsigned32 schedule seed required')
 elf=Path(elf).resolve()
 if not elf.is_file():raise ValueError('Existing guest ELF required')
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);roles=m['roles'];argv=[roles['launcher']['path'],*m['fixed_arguments'],'--extlib='+roles['UART']['path'],'--iris-bootrom='+roles['bootrom']['path'],'--dtb='+roles['dtb']['path'],'--iris-timing-fixture='+m['fixtures'][mode]['path'],'--iris-schedule-seed='+str(seed),'--iris-timing-trace='+str(out/'summary.json'),str(elf)]
 inputs={**m['input_sha256'],str(Path(manifest_path).resolve()):manifest_sha,str(elf):sha(elf)};env=dict(os.environ)
 env.pop('IRIS_FATAL_PCS',None);env.pop('IRIS_EMPIRICAL_ASYNC_TRACE',None);env['IRIS_EMPIRICAL_FEATURES']=str(out/'features.jsonl')
 receipt={'schema':'iris.source_OPU_native_experiment.v1','status':'starting','mode':mode,'argv':argv,'input_sha256':inputs,'calibrated_provider_used':False,'native_experiment_only':True,'numeric_validation_performed':False,'normal_HTIF_guest_exit_independently_verified':False,'hardware_contacted':False,'timeout_seconds':timeout,'schedule_seed':seed,'environment':{k:v for k,v in env.items()if k.startswith(('IRIS_','LD_'))}}
 proc=None;started=time.monotonic();save=lambda:(out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n');save()
 try:
  with(out/'stdout').open('wb')as so,(out/'stderr').open('wb')as se:
   proc=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True);receipt.update(status='running',owned_child_pid=proc.pid);save()
   try:code=proc.wait(timeout=timeout);timed=False
   except(subprocess.TimeoutExpired,KeyboardInterrupt):kill_owned(proc);code=proc.returncode;timed=True
  for n,h in inputs.items():checked(n,h)
  receipt.update(exit_status=code,timed_out=timed,status='process_exit_zero'if code==0 and not timed else'failed_or_timed_out',**{'pass':code==0 and not timed})
 except(Exception,KeyboardInterrupt)as e:receipt.update(status='refused_or_failed',error=str(e),**{'pass':False})
 finally:
  if proc is not None and proc.poll()is None:kill_owned(proc)
  receipt.update(host_seconds=time.monotonic()-started,owned_process_cleanup_complete=proc is None or proc.returncode is not None,output_sha256={str(p):sha(p)for p in out.iterdir()if p.is_file()and p.name!='execution.json'});save()
 return receipt
def main():
 def interrupted(signum,frame):raise KeyboardInterrupt('signal '+str(signum))
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
 p=argparse.ArgumentParser(__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--expected-sha256',required=True);p.add_argument('--action',choices=['describe','verify','provider','run'],default='describe');p.add_argument('--mode',choices=['off','tk124'],default='off');p.add_argument('--elf',type=Path);p.add_argument('--output',type=Path);p.add_argument('--timeout',type=float,default=120);p.add_argument('--seed',type=int,default=0);a=p.parse_args()
 try:
  m=verify(a.package,a.expected_sha256)
  if a.action=='provider':raise ValueError('IRIS_SOURCE_OPU_CALIBRATED_PROVIDER_UNAVAILABLE: new native/mode actual timing calibration replay and runtime binding required')
  if a.action=='run':
   if a.elf is None or a.output is None:raise ValueError('--elf and fresh --output required')
   r=run(m,a.mode,a.elf,a.output,a.timeout,a.seed,a.package,a.expected_sha256);print(json.dumps(r,indent=2));return 0 if r['pass']else 1
  print(json.dumps(descriptor(m,a.mode),indent=2));return 0
 except(ValueError,OSError,KeyError,TypeError)as e:print('IRIS_SOURCE_OPU_REFUSED: '+str(e),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
