#!/usr/bin/env python3
"""Validate the exact captured footprint experiment without assuming DRAMmisses."""
import argparse,collections,hashlib,json,sys,tarfile,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from analyze_campaign import read_archive as original_read_archive,select_guest_uart
from batch_runner import digest
from rvv_identify_1908_review import validator,inspect,flatten,inspect_clint_window,ELF,ROLE
def read_archive(archive,expected_manifest):
 data,ids=original_read_archive(archive,expected_manifest);m=json.loads(data['job/run.json'])
 if m.get('campaign_role')!=ROLE:raise ValueError('Exact isolated experiment role')
 with tarfile.open(archive,'r:gz')as t:
  for name in ['scope-proof.json','scope-proof.json','ready.json','corpus.json','build.json','qualification.json','layout.json','review.json','host-cases.json','protocol-proof.json','phase-proof.json']:
   member='job/'+name;want=m['prepared_file_sha256'][name]
   if ids.get(member)!=want:raise ValueError('Immutable admission record changed '+name)
   raw=t.extractfile(member).read()
   if hashlib.sha256(raw).hexdigest()!=want:raise ValueError('Retained record changed '+name)
   data[member]=raw
 return data,ids
def training_rows(rows):
 selected=[]
 for original in rows:
  if original['internal_split']!='train':continue
  r=dict(original);r.update(issue_cycles=r['issue_cycle']-r['start_cycle'],drain_cycles=r['end_cycle']-r['issue_cycle'])
  for key in ('start_cycle','issue_cycle','end_cycle','mtime_before','mtime_after'):r.pop(key,None)
  selected.append(r)
 if len(selected)!=1410:raise ValueError('Exactly1410TRAINrows')
 return selected
def analyze(job,out,training_export=None):
 if out.exists()or job==out or job in out.parents:raise ValueError('Freshanalysisoutsidejob')
 out.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[Path(__file__).resolve(),ROOT/'firesim/rvv_identify_1908_review.py',ROOT/'benchmarks/rvv_identify_1908_v1/qualify.py',ROOT/'benchmarks/rvv_identify_1908_v1/validate.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.rvv_identify_archive_analysis.v1',**{'pass':False},hardware_contacted=False,fitting_only=True,global_heldout=False,new_exact_reference=True,physical_hit_or_miss_measured=False,physical_memory_traffic_measured=False,source_image_association_verified=False,timing_accuracy_certified=False,calibration_usable=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'))
 try:
  cap=current['capture'];archive=Path(cap['archive'])
  if cap['status']!='captured'or cap['returncode']!=0 or digest(archive)!=cap['archive_sha256']:raise ValueError('Exactquiescentcapture')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_verified=True,archive_sha256=cap['archive_sha256'])
  if m.get('campaign_role')!=ROLE or m.get('fitting_only')is not True or m.get('global_heldout')is not False or m.get('new_exact_reference_required')is not True or m.get('old_campaign_timings_applicable')is not False or m.get('require_goldens')is not True or m.get('require_regions')is not True or m.get('cohorts')!=1908 or m.get('expected_regions')!=1908 or len(m['cases'])!=1908:raise ValueError('Exactnew1908singlehart fittingexperiment')
  for p in sources:
   want=m['runner_sha256']if p.name=='batch_runner.py'else m['input_sha256'].get(str(p))
   if want!=digest(p)or want not in ids.values():raise ValueError('Archivedanalysissourcemismatch '+str(p))
  if ids['job/ready.json']!=m['reviewed_ready_sha256']or ids['job/corpus.json']!=m['corpus_sha256']or ids['job/manager/workloads/iris-batch/batch.elf']!=m['elf_sha256']or m['elf_sha256']!=ELF:raise ValueError('Exactapprovedready/corpus/ELFbinding')
  ready=json.loads(data['job/ready.json']);corpus=json.loads(data['job/corpus.json'])
  with tarfile.open(archive,'r:gz')as t:
   raw=t.extractfile('job/manager/workloads/iris-batch/batch.elf').read();layout=json.load(t.extractfile('job/layout.json'));review=json.load(t.extractfile('job/review.json'))
  if hashlib.sha256(raw).hexdigest()!=ELF or ids['job/layout.json']!=ready['artifact_sha256']['layout.json']or ids['job/review.json']!=ready['artifact_sha256']['review.json']or ready['ELF_sha256']!=ELF:raise ValueError('Actualbinary/layout/reviewidentity')
  binary=inspect(raw,corpus,layout);report['compiled_CLINT_window']=inspect_clint_window(raw)
  if binary!=review['compiled_and_layout_proof']or flatten(corpus)!=m['cases']:raise ValueError('Independentactualcompiledtable/layout/flattenedhostcases')
  member,report['guest_uart']=select_guest_uart(data,ids);text=data[member].decode('utf-8','strict');(out/'uartlog').write_bytes(data[member]);(out/'observed.elf').write_bytes(raw)
  if current['status']!='completed_uncertified':
   raise ValueError('Hardware run failed; no normal completed isolated measurement qualification')
  report['numeric']=validator().validate(text,corpus);rows=[json.loads(x[len('IRIS_REGION '):])for x in text.splitlines()if x.startswith('IRIS_REGION ')];spec={c['id']:c for c in m['cases']}
  for r in rows:r.update(mtime_delta=r['mtime_after']-r['mtime_before'],quantized_global_window_source_core_cycles=(r['mtime_after']-r['mtime_before'])*1000,global_window_scope='encloses_CSR_ROI_with_sampling_overhead',no_overhead_subtraction=True,global_quantization_error_bound_core_cycles=1000,cycles=r['end_cycle']-r['start_cycle'],semantic_parent_case_id=spec[r['case_id']]['semantic_parent_case_id'],internal_split=spec[r['case_id']]['internal_split'],ELF_sha256=ELF,source_case_id=r['case_id'])
  phases=m['commands'];report['lifecycle']=[{k:r.get(k)for k in['task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out']}for r in phases]
  if [(r['task'],r['status'])for r in phases]!=[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]or any(r['returncode']!=0 or r['timed_out']is not False for r in phases)or current['status']!='completed_uncertified'or current['cleanup_status']!='passed'or current.get('error')is not None or current.get('cleanup_error')is not None or m['status']!=current['status']or m['cleanup_status']!=current['cleanup_status']:raise ValueError('Completeownedfourphase success+cleanup required')
  if digest(archive)!=cap['archive_sha256']:raise ValueError('Archivechangedduringanalysis')
  (out/'observed.elf').write_bytes(raw);(out/'uartlog').write_bytes(data[member]);(out/'corpus.json').write_bytes(data['job/corpus.json']);(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n');(out/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');(out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));report.update(reserved_timing_labels_root_only=True,train_regions=1410,reserved_regions=498,**{'pass':True},compiled_case_records=1908,declared_host_cases=1908,regions=1908,by_hart=dict(collections.Counter(r['hart']for r in rows)),by_kind=dict(collections.Counter(r['kind']for r in rows)),global_time_scope='CLINTbracketsall3CSRphases;quantization1000cycles;nosubtraction',mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,global_quantization_error_bound_core_cycles=1000,global_accuracy_2percent_claimed=False,counter_scope=corpus['clock_scope'],history_scope='Activeonlypreparation;inactivequietWFI;allmeasurementsbeforeUART',requested_byte_scope='Architecturalvectorpayloadgeometry;notphysicalTLtraffic',qualification='NewRVV/FPHSD/LSU/rowmove issue/drain observations; no physicalrequest/transaction/fullSoCtimingclaim.')
  if training_export is not None:
   export=Path(training_export)
   if export.exists()or export==out or out in export.parents or job in export.parents:raise ValueError('Fresh TRAIN export outside combined analysis/job')
   selected=training_rows(rows)
   if len(selected)!=1410 or any(r['internal_split']!='train'for r in selected):raise ValueError('Strict TRAIN-only rows')
   export.mkdir(parents=True);(export/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in selected))
   packet=dict(schema='iris.rvv_identify_TRAIN_only_export.v1',status='passed',regions=1410,reserved_timing_labels_excluded=True,absolute_timestamps_removed_to_hide_reserved_gaps=True,excluded_group_rule='ArithmeticLMUL4/memory64B/overlap128B/rowcount16/matrixjointedge16TK4',ELF_sha256=ELF,archive_sha256=cap['archive_sha256'],frozen_split_sha256=corpus['frozen_split_sha256'],regions_sha256=digest(export/'regions.jsonl'),new_exact_reference=True,source_image_association_verified=False,physical_hit_or_miss_measured=False)
   (export/'report.json').write_text(json.dumps(packet,indent=2)+'\n');report['TRAIN_export']=dict(path=str(export),report_sha256=digest(export/'report.json'),regions=1410)
 except(OSError,ValueError,AssertionError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as e:report['error']=str(e)
 report['output_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['pass','archive_verified','regions','error']}));return 0 if report['pass']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--training-export',type=Path);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve(),a.training_export))
