#!/usr/bin/env python3
"""Strict archive-bound functional result; failed/partial observations stay failed."""
import argparse,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from fpga_bringup_v1 import validate,host_cases,need
from batch_runner import digest
from analyze_campaign import read_archive,select_guest_uart
from prepare_zephyr_bringup_v1 import ROLE

def lifecycle(current,m):
 need(current['status']==m['status']=='completed_uncertified'and current['cleanup_status']==m['cleanup_status']=='passed','Normal managed completion+cleanup required')
 need(current.get('error')is None and current.get('cleanup_error')is None,'No managed errors')
 commands=m['commands'];need([(r['task'],r['status'])for r in commands]==[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')],'All four owned managed phases')
 need(all(type(r['returncode'])is int and r['returncode']==0 and r['timed_out']is False for r in commands),'All four phases normally exit zero')
 return [{k:r.get(k)for k in ('task','status','returncode','timed_out','host_elapsed_seconds','cleanup_phase')}for r in commands]

def analyze(job,out):
 need(not out.exists()and job!=out and job not in out.parents,'Fresh output outside job');out.mkdir(parents=True)
 current=json.loads((job/'run.json').read_text());sources=[Path(__file__).resolve(),ROOT/'zephyr/fpga_bringup_v1.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/prepare_zephyr_bringup_v1.py']
 report=dict(schema='iris.Zephyr_scalar6_bringup_archive_analysis.v1',**{'pass':False},functional_only=True,calibration_usable=False,timing_certified=False,source_image_association_verified=False,hardware_contacted=False,current_manifest_sha256=digest(job/'run.json'),input_sha256={str(p):digest(p)for p in sources})
 try:
  cap=current['capture'];archive=Path(cap['archive']);need(cap['status']=='captured'and cap['returncode']==0 and digest(archive)==cap['archive_sha256'],'Exact completed capture')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_sha256=cap['archive_sha256'],archive_verified=True)
  need(m['campaign_role']==ROLE and m['require_regions']is True and m['require_goldens']is True and m['calibration_usable']is False and m['cases']==host_cases(),'Exact finite scalar6 contract')
  for p in sources:
   want=m['runner_sha256']if p.name=='batch_runner.py'else m['input_sha256'].get(str(p));need(want==digest(p)and want in ids.values(),'Bound analyzer/source identity '+str(p))
  for name,want in [('ready.json',m['reviewed_ready_sha256']),('corpus.json',m['corpus_sha256']),('manager/workloads/iris-batch/batch.elf',m['elf_sha256'])]:need(ids.get('job/'+name)==want,'Archived actual artifact '+name)
  with tarfile.open(archive,'r:gz')as stream:
   elf=stream.extractfile('job/manager/workloads/iris-batch/batch.elf').read();ready=json.load(stream.extractfile('job/ready.json'));q=json.load(stream.extractfile('job/qualification.json'))
  import hashlib
  need(hashlib.sha256(elf).hexdigest()==ready['ELF_sha256']==q['ELF_sha256']==m['elf_sha256'],'Actual ELF equality')
  need(ids['job/qualification.json']==ready['qualification_sha256']and q['pass']is True,'Original compiled/native qualification')
  member,report['guest_uart']=select_guest_uart(data,ids);text=data[member].decode('utf-8','strict');(out/'uartlog').write_bytes(data[member]);(out/'observed.elf').write_bytes(elf)
  report['observed_region_count']=sum(x.startswith('IRIS_REGION ')for x in text.splitlines());report['observed_completion_marker']=any(x.startswith('IRIS_BATCH_DONE ')for x in text.splitlines())
  report['guest_proof']=validate(text,True);report['lifecycle']=lifecycle(current,m)
  rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_REGION ')];(out/'regions.json').write_text(json.dumps(rows,indent=2)+'\n')
  need(digest(archive)==cap['archive_sha256'],'Archive unchanged throughout analysis')
  report.update(**{'pass':True},qualification='Actual scalar Zephyr SMP three-hart functional bringup passed on this exact archived image/driver/ELF. RVV/VME context, per-hart IRQ counts, whole source-image equivalence and timing remain unqualified.')
 except(OSError,ValueError,KeyError,TypeError,UnicodeError,tarfile.TarError)as e:report['error']=str(e)
 report['artifact_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.job.resolve(),a.output.resolve());print(json.dumps({k:r.get(k)for k in ('pass','archive_verified','guest_proof','error')}));raise SystemExit(0 if r['pass']else 1)
