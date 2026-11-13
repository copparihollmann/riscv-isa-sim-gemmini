#!/usr/bin/env python3
"""Root-only frozen overlap archive analysis; optional114 TRAIN-only export."""
import argparse,collections,hashlib,json,struct,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import digest,parse_regions
from overlap_capture_common_v1 import validator,inspect,host_cases,ELF,PARENT_READY,SPLIT_SHA,is_reserved
ROLE='source_overlap_completion_validation_v1'
def training_rows(rows):
 result=[]
 for original in rows:
  if original['internal_split']!='train':continue
  if(original['hart']<2 and original['edge']==16)or(original['hart']==2 and original['edge']==64):raise ValueError('Reserved label in TRAIN')
  r=dict(original)
  for k in('start_cycle','issue_end_cycle','fence_end_cycle','end_cycle'):r.pop(k,None)
  result.append(r)
 if len(result)!=114:raise ValueError('Exactly114 TRAIN labels')
 return result

def analyze(job,out,training_export=None):
 if out.exists()or job==out or job in out.parents:raise ValueError('Fresh analysis outside job')
 out.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[Path(__file__).resolve(),ROOT/'firesim/overlap_capture_common_v1.py',ROOT/'benchmarks/overlap_completion_v1/validate_console.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.source_overlap_managed_archive_analysis.v1',status='failed',hardware_contacted=False,reserved_timing_labels_root_only=True,source_mechanism_validation=True,global_heldout=False,source_image_association_verified=False,timing_accuracy_certified=False,calibration_usable=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'))
 try:
  cap=current['capture'];archive=Path(cap['archive'])
  if cap['status']!='captured'or cap['returncode']!=0 or digest(archive)!=cap['archive_sha256']:raise ValueError('Exact quiescent capture')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_verified=True,archive_sha256=cap['archive_sha256'])
  if m.get('campaign_role')!=ROLE or m.get('require_regions')is not True or m.get('require_goldens')is not True or m.get('reserved_timing_labels_root_only')is not True or m.get('global_heldout')is not False or m.get('cohorts')!=168 or m.get('expected_regions')!=168 or len(m['cases'])!=168:raise ValueError('Exact168 source-overlap experiment')
  for p in sources:
   want=m['runner_sha256']if p.name=='batch_runner.py'else m['input_sha256'].get(str(p))
   if want!=digest(p)or want not in ids.values():raise ValueError('Archived source identity '+str(p))
  with tarfile.open(archive,'r:gz')as t:
   frozen={n:t.extractfile('job/'+n).read()for n in['ready.json','qualification.json','build.json','corpus.json','readback-layout.json','compiled-proof.json','frozen-split.json']};raw=t.extractfile('job/manager/workloads/iris-batch/batch.elf').read()
  for name,rawfile in frozen.items():
   if hashlib.sha256(rawfile).hexdigest()!=ids['job/'+name]or ids['job/'+name]!=m['prepared_file_sha256'][name]:raise ValueError('Exact immutable prepared record '+name)
  if ids['job/ready.json']!=PARENT_READY or ids['job/ready.json']!=m['reviewed_ready_sha256']or ids['job/corpus.json']!=m['corpus_sha256']or hashlib.sha256(raw).hexdigest()!=ELF or m['elf_sha256']!=ELF or ids['job/frozen-split.json']!=SPLIT_SHA or m['frozen_split_sha256']!=SPLIT_SHA:raise ValueError('Sourcepacket/ELF/split identity')
  ready=json.loads(frozen['ready.json']);q=json.loads(frozen['qualification.json']);c=json.loads(frozen['corpus.json']);layout=json.loads(frozen['readback-layout.json']);proof=json.loads(frozen['compiled-proof.json'])
  if ids['job/qualification.json']!=ready['qualification_sha256']or q.get('pass')is not True or inspect(raw,c,layout)!=proof or host_cases(c)!=m['cases']:raise ValueError('Compiled corpus/kernel/layout/roles')
  member,report['guest_uart']=select_guest_uart(data,ids);text=data[member].decode('utf-8','strict');(out/'uartlog').write_bytes(data[member]);(out/'observed.elf').write_bytes(raw)
  if current['status']!='completed_uncertified':raise ValueError('Failed hardware outcome; raw output retained without normal-completion claim')
  report['numeric']=validator().validate(text,c);rows=parse_regions(text,host_cases(c),ELF,m['image']['sha256'],True,True)
  for row in rows:
   i=int(row['case_id'].rsplit('.',1)[1]);case=c['cases'][i];row.update(semantic_source_case_id=case['case_id'],parent_case_id=case['case_id'].rsplit('.trial',1)[0],trial=case['trial'],fp8=case['fp8'],edge=case['edge'],count=case['count'],rotate=case['rotate'],internal_split='reserved_validation'if is_reserved(case)else'train',issue_window_cycles=row['issue_end_cycle']-row['start_cycle'],fence_window_cycles=row['fence_end_cycle']-row['issue_end_cycle'],dependent_readout_window_cycles=row['end_cycle']-row['fence_end_cycle'],instret_scope='total_only',ELF_sha256=ELF)
  phases=m['commands'];report['lifecycle']=[{k:r.get(k)for k in['task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out']}for r in phases]
  if[(r['task'],r['status'])for r in phases]!=[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]or any(r['returncode']!=0 or r['timed_out']is not False for r in phases)or current['cleanup_status']!='passed'or current.get('error')is not None or current.get('cleanup_error')is not None or m['status']!=current['status']or m['cleanup_status']!=current['cleanup_status']:raise ValueError('All4 owned phases/cleanup normal success')
  if digest(archive)!=cap['archive_sha256']:raise ValueError('Archive changed during analysis')
  (out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));(out/'corpus.json').write_bytes(frozen['corpus.json']);report.update(status='passed',regions=168,boundary_values=672,total_instret_deltas=168,independent_numeric_elements=19872,by_hart=dict(collections.Counter(r['hart']for r in rows)),train_regions=114,reserved_regions=54,matrix_coverage='row0of4tiles;32wordseachincludinginactivecolumns; NOTallMRFrows',vector_console_coverage='activeVLbytesonly; nopaddingclaim',CLINT_available=False,global_time_alignment_or_end_to_end_claimed=False)
  if training_export is not None:
   export=Path(training_export)
   if export.exists()or export==out or out in export.parents or job in export.parents:raise ValueError('Fresh separate TRAIN export')
   selected=training_rows(rows);export.mkdir(parents=True);(export/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in selected));packet=dict(schema='iris.source_overlap_TRAIN_only_export.v1',status='passed',regions=114,reserved_timing_labels_excluded=True,absolute_timestamps_removed_to_hide_reserved_gaps=True,frozen_split_sha256=SPLIT_SHA,ELF_sha256=ELF,archive_sha256=cap['archive_sha256'],regions_sha256=digest(export/'regions.jsonl'),source_mechanism_validation=True,source_image_association_verified=False);(export/'report.json').write_text(json.dumps(packet,indent=2)+'\n');report['TRAIN_export']=dict(path=str(export),report_sha256=digest(export/'report.json'),regions=114)
 except(OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as e:report.update(status='failed',error=str(e))
 report['output_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['status','archive_verified','regions','error']}));return 0 if report['status']=='passed'else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--training-export',type=Path);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve(),a.training_export))
