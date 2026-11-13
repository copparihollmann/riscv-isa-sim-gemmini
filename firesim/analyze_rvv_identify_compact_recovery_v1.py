#!/usr/bin/env python3
"""Validate the exact captured footprint experiment without assuming DRAMmisses."""
import argparse,collections,hashlib,json,sys,tarfile,struct,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from analyze_campaign import read_archive as original_read_archive,select_guest_uart
from batch_runner import digest,parse_regions
from rvv_identify_compact_review import validator,inspect,flatten,inspect_clint_window,ELF,ROLE,validate_sections,expand
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
  r=dict(original);r.pop('actual_record_uint64',None);r.update(issue_cycles=r['issue_cycle']-r['start_cycle'],drain_cycles=r['end_cycle']-r['issue_cycle'])
  for key in ('start_cycle','issue_cycle','end_cycle','mtime_before','mtime_after'):r.pop(key,None)
  selected.append(r)
 if len(selected)!=1410:raise ValueError('Exactly1410TRAINrows')
 return selected

def recover_collection_outcome(current,m,text):
 # This whitelist is evaluated against immutable raw UART and the unchanged
 # collector itself. No status/error/phase record is edited or reclassified.
 if current.get('status')!='failed'or m.get('status')!='failed':raise ValueError('Recovery only for preserved failed collector outcome')
 for run in(current,m):
  if run.get('cleanup_status')!='passed'or run.get('cleanup_error')is not None or run.get('lock_release_error')is not None or run.get('lock_retained_for_operator')is True:raise ValueError('Owned cleanup/lock release required')
 phases=m['commands']
 if len(phases)!=4 or [p.get('task')for p in phases]!=['kill','infrasetup','runworkload','kill']:raise ValueError('Exact complete managed four-phase lifecycle')
 for i,p in enumerate(phases):
  if p.get('status')!='passed'or type(p.get('returncode'))is not int or p['returncode']!=0 or p.get('timed_out')is not False or p.get('cleanup_phase')is not(i==3):raise ValueError('Every managed phase passed, including final owned cleanup')
 if current.get('commands')!=phases:raise ValueError('Current and archived phase records disagree')
 exits=[int(x)for x in re.findall(r'COMMAND_EXIT_CODE="([0-9]+)"',text)]
 if not exits or any(x!=0 for x in exits)or m.get('console_process_exit_codes')!=exits:raise ValueError('Actual console process exit zero required')
 if any(l.strip().startswith('IRIS_REGION')for l in text.splitlines()):raise ValueError('Recovery exclusively for compact wire format, no JSON regions')
 try:parse_regions(text,m['cases'],m['elf_sha256'],m['image']['sha256'],True,True)
 except ValueError as e:expected=str(e)
 else:raise ValueError('Unchanged collector must actually refuse compact stream')
 if not expected.startswith('Missing target regions for case/hart pairs: ')or current.get('error')!=expected or m.get('error')!=expected:raise ValueError('Only exact recomputed missing-region collector error is recoverable')
 # validate() decodes exactly136B/17Q, checks all compiled roles/full words,
 # source counters, section order/counts and final Done failed0/normalcompletion.
 return dict(original_runner_status='failed',original_runner_error=expected,original_runner_error_sha256=hashlib.sha256(expected.encode()).hexdigest(),original_runner_passed=False,collection_format_failure_only=True,console_process_exit_codes=exits,all_four_managed_phases_passed=True,owned_cleanup_verified=True,status_or_error_records_modified=False)

def analyze(job,out,training_export=None):
 if out.exists()or job==out or job in out.parents:raise ValueError('Freshanalysisoutsidejob')
 out.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[ROOT/'firesim/analyze_rvv_identify_compact.py',ROOT/'firesim/rvv_identify_compact_review.py',ROOT/'benchmarks/rvv_identify_compact_v1/qualify.py',ROOT/'benchmarks/rvv_identify_compact_v1/validate.py',ROOT/'benchmarks/rvv_identify_compact_v1/codec.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.rvv_identify_compact_postcapture_recovery.v1',adapter_source_sha256=digest(Path(__file__).resolve()),postcapture_analysis_adapter=True,original_runner_passed=False,**{'pass':False},hardware_contacted=False,fitting_only=True,global_heldout=False,new_exact_reference=True,physical_hit_or_miss_measured=False,physical_memory_traffic_measured=False,source_image_association_verified=False,timing_accuracy_certified=False,calibration_usable=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'))
 try:
  cap=current['capture'];archive=Path(cap['archive'])
  if cap['status']!='captured'or cap['returncode']!=0 or digest(archive)!=cap['archive_sha256']:raise ValueError('Exactquiescentcapture')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_verified=True,archive_sha256=cap['archive_sha256'])
  for name,want in m['prepared_file_sha256'].items():
   if ids.get('job/'+name)!=want:raise ValueError('Every frozen prepared byte must match archive: '+name)
  for name,want in m['input_sha256'].items():
   if want not in ids.values():raise ValueError('Every bound source/input byte must be archived: '+name)
  for name in('image','driver'):
   if not m[name].get('sha256')or m[name]['sha256']not in ids.values():raise ValueError('Archived image/driver SHA required')
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
  decoded=expand(text,corpus,partial=False);(out/'decoded-regions-uart.jsonl').write_text(decoded);report['data_origin']='JSONderivedfrom17actualuint64LEbase64;casegeometryfromarchivedcompiledtable;rawUARTretained'
  partial=validate_sections(decoded,corpus,partial=True);(out/'partial-sections.json').write_text(json.dumps(partial,indent=2)+'\n');report['observed_partial_sections']=partial
  recovery=recover_collection_outcome(current,m,text);report['collector_format_recovery']=recovery
  report['numeric']=validator().validate(text,corpus);rows=[json.loads(x[len('IRIS_REGION '):])for x in decoded.splitlines()if x.startswith('IRIS_REGION ')];spec={c['id']:c for c in m['cases']}
  for r in rows:r.update(mtime_delta=r['mtime_after']-r['mtime_before'],quantized_global_window_source_core_cycles=(r['mtime_after']-r['mtime_before'])*1000,global_window_scope='encloses_CSR_ROI_with_sampling_overhead',no_overhead_subtraction=True,global_quantization_error_bound_core_cycles=1000,cycles=r['end_cycle']-r['start_cycle'],semantic_parent_case_id=spec[r['case_id']]['semantic_parent_case_id'],internal_split=spec[r['case_id']]['internal_split'],ELF_sha256=ELF,source_case_id=r['case_id'])
  phases=m['commands'];report['lifecycle']=[{k:r.get(k)for k in['task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out']}for r in phases]
  if digest(archive)!=cap['archive_sha256']:raise ValueError('Archivechangedduringanalysis')
  (out/'observed.elf').write_bytes(raw);(out/'uartlog').write_bytes(data[member]);(out/'corpus.json').write_bytes(data['job/corpus.json']);(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n');(out/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');(out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));report.update(reserved_timing_labels_root_only=True,train_regions=1410,reserved_regions=498,**{'pass':True},compiled_case_records=1908,declared_host_cases=1908,regions=1908,by_hart=dict(collections.Counter(r['hart']for r in rows)),by_kind=dict(collections.Counter(r['kind']for r in rows)),global_time_scope='CLINTbracketsall3CSRphases;quantization1000cycles;nosubtraction',mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,global_quantization_error_bound_core_cycles=1000,global_accuracy_2percent_claimed=False,counter_scope=corpus['clock_scope'],history_scope='Hartgrouped;twoMSIPwakeups;UARTafterownROIsanddrainedbeforehandoff;newhistory',requested_byte_scope='Architecturalvectorpayloadgeometry;notphysicalTLtraffic',guest_normal_exit_independently_verified=True,collection_format_failure_recovered=True,original_runner_passed=False,qualification='Postcapture compact-format adapter verifies full guestnormalsuccess/allgoldens/fourphasepasses; original runner remains FAILED for exact missing-IRIS_REGION collector error. No physicalrequest/transaction/fullSoCtimingclaim.')
  if training_export is not None:
   export=Path(training_export)
   if export.exists()or export==out or out in export.parents or job in export.parents:raise ValueError('Fresh TRAIN export outside combined analysis/job')
   selected=training_rows(rows)
   if len(selected)!=1410 or any(r['internal_split']!='train'for r in selected):raise ValueError('Strict TRAIN-only rows')
   export.mkdir(parents=True);(export/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in selected))
   packet=dict(schema='iris.rvv_identify_TRAIN_only_export.v1',status='passed',postcapture_format_recovery=True,original_runner_status='failed',original_runner_passed=False,adapter_source_sha256=digest(Path(__file__).resolve()),original_runner_error_sha256=recovery['original_runner_error_sha256'],all_four_managed_phases_passed=True,guest_normal_exit_independently_verified=True,regions=1410,reserved_timing_labels_excluded=True,absolute_timestamps_removed_to_hide_reserved_gaps=True,excluded_group_rule='ArithmeticLMUL4/memory64B/overlap128B/rowcount16/matrixjointedge16TK4',ELF_sha256=ELF,archive_sha256=cap['archive_sha256'],frozen_split_sha256=corpus['frozen_split_sha256'],regions_sha256=digest(export/'regions.jsonl'),new_exact_reference=True,source_image_association_verified=False,physical_hit_or_miss_measured=False)
   (export/'report.json').write_text(json.dumps(packet,indent=2)+'\n');report['TRAIN_export']=dict(path=str(export),report_sha256=digest(export/'report.json'),regions=1410)
 except(OSError,ValueError,AssertionError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as e:report['error']=str(e)
 report['output_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['pass','archive_verified','regions','error']}));return 0 if report['pass']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--training-export',type=Path);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve(),a.training_export))
