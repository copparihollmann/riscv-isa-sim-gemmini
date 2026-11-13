#!/usr/bin/env python3
"""Root-only complete matrix archive validation; export only96 TRAIN labels."""
import argparse,collections,hashlib,json,struct,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import digest
from pow2_matrix_review import validator,inspect,flatten,ELF
from check_pow2_matrix_clint import inspect_clint_window
ROLE='pow2_single_matrix_train_reserved_v1'
def training_rows(rows):
 result=[]
 for original in rows:
  if original['internal_split']!='train':continue
  if(original['m'],original['n'],original['k'])in {(16,16,16),(128,128,128),(32,32,64)}:raise ValueError('Reserved shape mislabeled TRAIN')
  r=dict(original)
  for k in('start_cycle','end_cycle','mtime_before','mtime_after'):r.pop(k,None)
  result.append(r)
 if len(result)!=96:raise ValueError('Exactly96 TRAIN labels')
 return result
def analyze(job,out,training_export=None):
 if out.exists()or job==out or job in out.parents:raise ValueError('Fresh analysis outside job')
 out.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[Path(__file__).resolve(),ROOT/'firesim/pow2_matrix_review.py',ROOT/'firesim/check_pow2_matrix_clint.py',ROOT/'benchmarks/pow2_matrix_v1/validate.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.pow2_single_matrix_archive_analysis.v1',status='failed',hardware_contacted=False,reserved_timing_labels_root_only=True,timing_accuracy_certified=False,source_image_association_verified=False,global_heldout=False,calibration_usable=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'))
 try:
  cap=current['capture'];archive=Path(cap['archive'])
  if cap['status']!='captured'or cap['returncode']!=0 or digest(archive)!=cap['archive_sha256']:raise ValueError('Exact quiescent capture')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_verified=True,archive_sha256=cap['archive_sha256'])
  if m.get('campaign_role')!=ROLE or m.get('require_goldens')is not True or m.get('require_regions')is not True or m.get('reserved_timing_labels_root_only')is not True or m.get('global_heldout')is not False or m.get('cohorts')!=132 or m.get('expected_regions')!=132 or len(m['cases'])!=132:raise ValueError('Exact132-case matrix source experiment')
  for p in sources:
   want=m['runner_sha256']if p.name=='batch_runner.py'else m['input_sha256'].get(str(p))
   if want!=digest(p)or want not in ids.values():raise ValueError('Captured analyzer source mismatch '+str(p))
  if ids['job/ready.json']!=m['reviewed_ready_sha256']or ids['job/corpus.json']!=m['corpus_sha256']or ids['job/manager/workloads/iris-batch/batch.elf']!=ELF or m['elf_sha256']!=ELF:raise ValueError('Ready/corpus/actual ELF identity')
  ready=json.loads(data['job/ready.json']);c=json.loads(data['job/corpus.json'])
  with tarfile.open(archive,'r:gz')as t:
   raw=t.extractfile('job/manager/workloads/iris-batch/batch.elf').read();gold=t.extractfile('job/golden-words.bin').read();qualification=json.load(t.extractfile('job/qualification.json'))
  if digest(archive)!=cap['archive_sha256']or hashlib.sha256(raw).hexdigest()!=ELF or hashlib.sha256(gold).hexdigest()!=ready['artifact_sha256']['golden-words.bin']:raise ValueError('Actual compiled/golden bytes')
  if inspect(raw,c,gold)!=qualification['compiled_proof']or flatten(c)!=m['cases']:raise ValueError('Compiled table/fullwordgolden/roles')
  report['compiled_CLINT_window']=inspect_clint_window(raw);member,report['guest_uart']=select_guest_uart(data,ids);text=data[member].decode('utf-8','strict');(out/'uartlog').write_bytes(data[member]);(out/'observed.elf').write_bytes(raw)
  if current['status']!='completed_uncertified':raise ValueError('Failed hardware run; raw prefix retained, NOT normalcompletion')
  report['numeric']=validator().validate(text,c);rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_REGION ')];byid={x['id']:x for x in c['cases']}
  for row in rows:
   case=byid[row['case_id']];row.update(cycles=row['end_cycle']-row['start_cycle'],mtime_delta=row['mtime_after']-row['mtime_before'],quantized_global_window_source_core_cycles=(row['mtime_after']-row['mtime_before'])*1000,internal_split=case['internal_split'],parent_case_id=case['parent_case_id'],split_group_id=case['split_group_id'],macs=case['macs'],ELF_sha256=ELF)
  phases=m['commands'];report['lifecycle']=[{k:r.get(k)for k in ['task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out']}for r in phases]
  if[(r['task'],r['status'])for r in phases]!=[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]or any(r['returncode']!=0 or r['timed_out']is not False for r in phases)or current['cleanup_status']!='passed'or current.get('error')is not None or current.get('cleanup_error')is not None or m['status']!=current['status']or m['cleanup_status']!=current['cleanup_status']:raise ValueError('Complete owned lifecycle+cleanup required')
  (out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));(out/'corpus.json').write_bytes(data['job/corpus.json']);report.update(status='passed',regions=132,train_regions=96,reserved_regions=36,by_hart=dict(collections.Counter(r['hart']for r in rows)),all_words_checked=1109760,new_exact_reference=True,global_accuracy_2percent_claimed=False,physical_MAC_count_or_memory_traffic_measured=False)
  if training_export is not None:
   export=Path(training_export)
   if export.exists()or export==out or out in export.parents or job in export.parents:raise ValueError('Fresh separate TRAIN export')
   selected=training_rows(rows);export.mkdir(parents=True);(export/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in selected));packet=dict(schema='iris.pow2_single_matrix_TRAIN_only_export.v1',status='passed',regions=96,reserved_timing_labels_excluded=True,absolute_timestamps_removed_to_hide_reserved_gaps=True,reserved_shapes=[[16,16,16],[128,128,128],[32,32,64]],frozen_split_sha256=c['frozen_split_sha256'],ELF_sha256=ELF,archive_sha256=cap['archive_sha256'],regions_sha256=digest(export/'regions.jsonl'),source_image_association_verified=False);(export/'report.json').write_text(json.dumps(packet,indent=2)+'\n');report['TRAIN_export']=dict(path=str(export),report_sha256=digest(export/'report.json'),regions=96)
 except(OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as e:report.update(status='failed',error=str(e))
 report['output_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['status','archive_verified','regions','error']}));return 0 if report['status']=='passed'else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--training-export',type=Path);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve(),a.training_export))
