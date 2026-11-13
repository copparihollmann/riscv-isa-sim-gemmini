#!/usr/bin/env python3
"""Independently validate the exact managed archive's protected operator words."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workloads'))
from model_operator_batch_validate import validate
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import digest
ROLE='model_operator_protected_validation_v1'
def analyze(job,output):
 if output.exists()or job==output or job in output.parents:raise ValueError('Fresh analysis directory outside job required')
 output.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[Path(__file__).resolve(),ROOT/'workloads/model_operator_batch_validate.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.model_operator_batch_archive_analysis.v1',**{'pass':False},hardware_contacted=False,calibration_usable=False,TinyLlama_protected_validation_only=True,source_image_association_verified=False,whole_model_qualified=False,timing_accuracy_qualified=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'),archive_verified=False)
 try:
  capture=current['capture'];archive=Path(capture['archive'])
  if capture['status']!='captured'or digest(archive)!=capture['archive_sha256']:raise ValueError('Exact successful quiescent archive required')
  data,identities=read_archive(archive,capture['captured_run_manifest_sha256']);manifest=json.loads(data['job/run.json']);report.update(archive_verified=True,archive_sha256=capture['archive_sha256'])
  if manifest['campaign_role']!=ROLE or manifest.get('validation_only')is not True or manifest.get('TinyLlama_protected')is not True or manifest.get('calibration_usable')is not False or manifest['require_goldens']is not True or manifest['require_regions']is not True:raise ValueError('Protected finite validation contract')
  for path in sources:
   expected=manifest['runner_sha256']if path.name=='batch_runner.py'else manifest['input_sha256'].get(str(path))
   if expected!=digest(path)or expected not in identities.values():raise ValueError('Actual archived analyzer/validator/runner source mismatch '+str(path))
  if identities.get('job/corpus.json')!=manifest['corpus_sha256']:raise ValueError('Archived independent source-shaped corpus changed')
  corpus=json.loads(data['job/corpus.json']);member='job/manager/workloads/iris-batch/batch.elf'
  if identities.get(member)!=manifest['elf_sha256']:raise ValueError('Archived actual ELF binding')
  with tarfile.open(archive,'r:gz')as stream:elf=stream.extractfile(member).read()
  if hashlib.sha256(elf).hexdigest()!=manifest['elf_sha256']:raise ValueError('Actual ELF bytes changed')
  (output/'observed.elf').write_bytes(elf);uart_name,report['guest_uart']=select_guest_uart(data,identities);uart=data[uart_name].decode('utf-8',errors='strict');(output/'uartlog').write_bytes(data[uart_name]);(output/'corpus.json').write_bytes(data['job/corpus.json']);report['guest_proof']=validate(uart,corpus)
  rows=[json.loads(line[len('IRIS_REGION '):])for line in uart.splitlines()if line.startswith('IRIS_REGION ')];(output/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');report['actual_counters_scope']='Raw actual FPGA mcycle/minstret for this NEW instrumented validation ELF only; no fitting, transferred accuracy or whole-model claim.'
  report['lifecycle']=[{k:r.get(k)for k in('task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out')}for r in manifest['commands']]
  if [(r['task'],r['status'])for r in manifest['commands']]!=[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]or current['status']!='completed_uncertified'or current['cleanup_status']!='passed'or current.get('error')is not None or current.get('cleanup_error')is not None:raise ValueError('Complete successful four-phase owned lifecycle required')
  if manifest['status']!=current['status']or manifest['cleanup_status']!=current['cleanup_status']:raise ValueError('Archived outcome mismatch')
  if digest(archive)!=capture['archive_sha256']:raise ValueError('Archive changed during analysis')
  report['pass']=True
 except(OSError,ValueError,KeyError,TypeError,UnicodeError,tarfile.TarError)as error:report['error']=str(error)
 report['artifact_sha256']={p.name:digest(p)for p in output.iterdir()if p.is_file()};(output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in('pass','archive_verified','guest_proof','error')}));return 0 if report['pass']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve()))
