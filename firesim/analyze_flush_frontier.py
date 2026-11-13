#!/usr/bin/env python3
"""Independently validate the exact managed archive's two-phase progress diagnosis."""
import argparse,hashlib,json,sys,tarfile,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'zephyr'))
from flush_frontier_validate import timeout as timeout_evidence
from flush_frontier_validate import normal as validate
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import digest
ROLE='fp_flush_one_shot_diagnostic_v1'
def analyze(job,output):
 if output.exists()or job==output or job in output.parents:raise ValueError('Fresh analysis directory outside job required')
 output.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[Path(__file__).resolve(),ROOT/'zephyr/flush_frontier_validate.py',ROOT/'zephyr/flush_frontier_run.py',ROOT/'zephyr/flush_frontier_validate.py',ROOT/'zephyr/compiler_pipeline.py',ROOT/'zephyr/freeze_heldouts.py',ROOT/'zephyr/uart_profiles.py',ROOT/'spike/run_functional.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.flush_frontier_one_shot_archive_analysis.v1',**{'pass':False},hardware_contacted=False,calibration_usable=False,diagnostic_only=True,source_image_association_verified=False,whole_model_qualified=False,timing_accuracy_qualified=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'),archive_verified=False)
 try:
  capture=current['capture'];archive=Path(capture['archive'])
  if capture['status']!='captured'or digest(archive)!=capture['archive_sha256']:raise ValueError('Exact successful quiescent archive required')
  data,identities=read_archive(archive,capture['captured_run_manifest_sha256']);manifest=json.loads(data['job/run.json']);report.update(archive_verified=True,archive_sha256=capture['archive_sha256'])
  if manifest['campaign_role']!=ROLE or manifest.get('diagnostic_only')is not True or manifest.get('calibration_usable')is not False or manifest['require_goldens']is not True or manifest['require_regions']is not True:raise ValueError('Exact diagnostic-only contract')
  for path in sources:
   expected=manifest['runner_sha256']if path.name=='batch_runner.py'else manifest['input_sha256'].get(str(path))
   if expected!=digest(path)or expected not in identities.values():raise ValueError('Actual archived analyzer/validator/runner source mismatch '+str(path))
  if identities.get('job/corpus.json')!=manifest['corpus_sha256']:raise ValueError('Archived independent source-shaped corpus changed')
  corpus=json.loads(data['job/corpus.json']);member='job/manager/workloads/iris-batch/batch.elf'
  if identities.get(member)!=manifest['elf_sha256']:raise ValueError('Archived actual ELF binding')
  with tarfile.open(archive,'r:gz')as stream:elf=stream.extractfile(member).read()
  if hashlib.sha256(elf).hexdigest()!=manifest['elf_sha256']:raise ValueError('Actual ELF bytes changed')
  if type(corpus.get('watchdog_enabled'))is not bool or corpus.get('variant')not in['enabled','disabled']or corpus['watchdog_enabled']!=(corpus['variant']=='enabled')or manifest.get('watch_pair_variant')!=corpus['variant']or manifest.get('watchdog_enabled')is not corpus['watchdog_enabled']:raise ValueError('Exact watchdog variant policy')
  so=struct.unpack_from('<Q',elf,40)[0];ss,sn=struct.unpack_from('<HH',elf,58);secs=[struct.unpack_from('<IIQQQQIIQQ',elf,so+i*ss)for i in range(sn)];matches=[]
  for sec in secs:
   if sec[1]!=2:continue
   st=secs[sec[6]];names=elf[st[4]:st[4]+st[5]]
   for pos in range(sec[4],sec[4]+sec[5],sec[9]):
    name,info,other,index,address,size=struct.unpack_from('<IBBHQQ',elf,pos)
    if name and names[name:].split(b'\0',1)[0]==b'iris_diag_watchdog_enabled':matches.append((address,size,index))
  if len(matches)!=1:raise ValueError('Unique actual retained watchdog byte')
  address,size,index=matches[0];section=secs[index]
  if size!=1 or not section[2]&2 or section[2]&4 or section[1]==8:raise ValueError('Actualwatch flag mustbe allocated nonexec filebacked byte')
  offset=section[4]+address-section[3]
  if elf[offset]!=(1 if corpus['watchdog_enabled']else 0):raise ValueError('Actual ELF watchdog byte disagrees with selectedvariant')
  (output/'observed.elf').write_bytes(elf);uart_name,report['guest_uart']=select_guest_uart(data,identities);uart=data[uart_name].decode('utf-8',errors='strict');(output/'uartlog').write_bytes(data[uart_name]);(output/'corpus.json').write_bytes(data['job/corpus.json']);report['one_shot_snapshot_observed']='IRIS_FLUSH_ONESHOT 'in uart;report['watchdog_enabled']=corpus['watchdog_enabled'];report['watch_pair_variant']=corpus['variant'];
  if report['one_shot_snapshot_observed']and not corpus['watchdog_enabled']:raise ValueError('Disabledwatcher cannotemit targetwatchtimeout')
  report['guest_proof']=timeout_evidence(uart)if report['one_shot_snapshot_observed']else validate(uart,corpus['manifest'],corpus['cases'],corpus['goldens'],corpus['watchdog_enabled'])
  rows=[json.loads(line[len('IRIS_REGION '):])for line in uart.splitlines()if line.startswith('IRIS_REGION ')];(output/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');report['actual_counters_scope']='Fixed-deadline one-shot diagnostic, NOT a no-progress detector. Last-recorded metadata may race; no current-PC/state or physical vector-completion claim. No original timing transfer or fitting/rootcause claim.'
  report['lifecycle']=[{k:r.get(k)for k in('task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out')}for r in manifest['commands']]
  phases=manifest['commands'];normal=not report['one_shot_snapshot_observed']
  if len(phases)!=4 or [r['task']for r in phases]!=['kill','infrasetup','runworkload','kill']or any(phases[i]['status']!='passed'for i in[0,1,3])or current['cleanup_status']!='passed'or current.get('cleanup_error')is not None:raise ValueError('Owned complete setup/cleanup lifecycle required')
  if normal and (phases[2]['status']!='passed'or current['status']!='completed_uncertified'or current.get('error')is not None):raise ValueError('Normal diagnostic completion needs successful run')
  if not normal and (phases[2].get('timed_out')is True or current['status']not in['failed','completed_uncertified']):raise ValueError('Targettimeout event must precede hostwatchdogexpiry')
  if manifest['status']!=current['status']or manifest['cleanup_status']!=current['cleanup_status']:raise ValueError('Archived outcome mismatch')
  if digest(archive)!=capture['archive_sha256']:raise ValueError('Archive changed during analysis')
  report['pass']=True
 except(OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as error:report['error']=str(error)
 report['artifact_sha256']={p.name:digest(p)for p in output.iterdir()if p.is_file()};(output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in('pass','archive_verified','guest_proof','error')}));return 0 if report['pass']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve()))
