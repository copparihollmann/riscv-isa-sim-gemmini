#!/usr/bin/env python3
"""Prospective identical-ELF saved-RTL run after frozen native prediction."""
import argparse,datetime,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
EXPECTED_PREDICTION='5d075b36512b05082bd82d742560974ea8fdc5058a313981e6d1cf1d9af6b1dc'
EXPECTED_ELF='a65bfb1f0a819cb0a0dea063f1ccdc5d9520c622ccbdbf9e3fb18d5b62758b07'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--reference',type=Path,required=True);p.add_argument('--prediction',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=1800);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'runner.py');reference=a.reference.resolve();prediction=a.prediction.resolve();pred=json.loads((prediction/'report.json').read_text());build=json.loads((reference/'build.json').read_text());elf=R/'build/saturn-timing-live-guest-capsule-v1/build/saturn-timing-live-guest-v1/guest.elf'
 if sha(prediction/'report.json')!=EXPECTED_PREDICTION or pred['ELF_sha256']!=EXPECTED_ELF or sha(elf)!=EXPECTED_ELF:raise ValueError('Exact pre-observation native prediction and identical guest required')
 for name,key in [('spike','native_sha256'),('libsifive_uart.so','uart_sha256'),('source-overlay.patch','source_overlay_sha256')]:
  if sha(prediction/name)!=pred[key]:raise ValueError('Changed frozen native prediction '+name)
 binary=reference/'simulator-k1'
 if sha(binary)!=build['binary_sha256']or not build['all_target_RTL_runtime_preload_objects_unchanged']:raise ValueError('Exact unchanged-target-RTL reference required')
 for name,wanted in build['input_sha256'].items():
  if sha(name)!=wanted:raise ValueError('Changed reference input '+name)
 # Audit existing nearby reports before any new timing observation. This is
 # a prospective diagnostic, never enrollment in the frozen global holdouts.
 matches=[]
 for base in[R/'build',R/'runs']:
  for current,dirs,files in os.walk(base):
   if len(Path(current).relative_to(base).parts)>=3:dirs[:]=[]
   for name in files:
    path=Path(current)/name
    if path.suffix=='.json'and path.stat().st_size<20_000_000:
     try:content=path.read_text()
     except UnicodeError:continue
     if EXPECTED_ELF in content:matches.append(str(path))
 audit={'schema':'iris.identical_K1_pre_observation_reference_audit.v1','captured_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'searched':'JSONfiles build/runs depth<=3,each<20MB; frozen source reference manifests inspected separately','matching_reports':matches,'no_preexisting_identical_ELF_RTL_run_found':not any('rtl' in Path(x).name.lower()or'rtl-k1' in x.lower()for x in matches),'not_global_held_out_enrollment':True,'prediction_capsule_sha256':EXPECTED_PREDICTION};(out/'prior-reference-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
 if not audit['no_preexisting_identical_ELF_RTL_run_found']:raise ValueError('Existing exact RTL reference requires explicit nonblind scope review')
 shutil.copy2(prediction/'report.json',out/'frozen-native-prediction.json');shutil.copy2(reference/'build.json',out/'reference-build.json');shutil.copy2(elf,out/'guest.elf');cmd=[str(binary),'+permissive','+verilator+seed+1','+verilator+rand+reset+2','+loadmem=1','+max-cycles=8000000','+init_write=0x2000004:0x1','+init_write=0x2000008:0x1','+iris-activity='+str(out/'activity.bin.gz'),'+iris-ownership='+str(out/'ownership.bin.gz'),'+permissive-off',str(out/'guest.elf')]
 inputs=[Path(__file__),prediction/'report.json',prediction/'spike',prediction/'libsifive_uart.so',prediction/'source-overlay.patch',reference/'build.json',binary,elf,out/'prior-reference-audit.json'];report={'schema':'iris.saturn_K1_prospective_saved_RTL_run.v1','status':'running','started_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':cmd,'host_timeout_seconds':a.timeout,'input_sha256':{str(p):sha(p)for p in inputs},'prediction_frozen_before_RTL':True,'target_RTL_runtime_preload_unchanged':True,'saved_FIR_two_state_exploration':True,'source_image_association_verified':False,'native_memory_is_explicit_functional_fixture':True,'comparison_is_not_fitting_or_global_held_out_certification':True,'timing_certified':False,'hardware_contacted':False};(out/'run.json').write_text(json.dumps(report,indent=2)+'\n');start=time.monotonic()
 with(out/'stdout').open('w')as stdout,(out/'stderr').open('w')as stderr:
  try:q=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=a.timeout,cwd=R);code=q.returncode;timed=False
  except subprocess.TimeoutExpired:code=None;timed=True
 report.update(exit_status=code,timed_out=timed,host_seconds=time.monotonic()-start,status='process_completed_validation_required'if code==0 and not timed else'bounded_incomplete_or_failed');report['artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()and p.name!='run.json'};(out/'run.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'exit_status':code,'host_seconds':report['host_seconds'],'report_sha256':sha(out/'run.json')}))
 if code!=0 or timed:raise SystemExit(1)
if __name__=='__main__':main()
