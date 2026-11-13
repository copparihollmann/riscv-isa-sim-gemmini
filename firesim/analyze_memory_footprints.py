#!/usr/bin/env python3
"""Validate the exact captured footprint experiment without assuming DRAMmisses."""
import argparse,collections,hashlib,json,sys,tarfile,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import digest
from memory_footprints_review import validator,inspect,flatten,ELF
ROLE='memory_footprint_large_fitting_v1'
def analyze(job,out):
 if out.exists()or job==out or job in out.parents:raise ValueError('Freshanalysisoutsidejob')
 out.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[Path(__file__).resolve(),ROOT/'firesim/memory_footprints_review.py',ROOT/'benchmarks/memory_footprints/validate.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.memory_footprint_archive_analysis.v1',**{'pass':False},hardware_contacted=False,fitting_only=True,global_heldout=False,new_exact_reference=True,physical_hit_or_miss_measured=False,physical_memory_traffic_measured=False,source_image_association_verified=False,timing_accuracy_certified=False,calibration_usable=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'))
 try:
  cap=current['capture'];archive=Path(cap['archive'])
  if cap['status']!='captured'or cap['returncode']!=0 or digest(archive)!=cap['archive_sha256']:raise ValueError('Exactquiescentcapture')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_verified=True,archive_sha256=cap['archive_sha256'])
  if m.get('campaign_role')!=ROLE or m.get('fitting_only')is not True or m.get('global_heldout')is not False or m.get('new_exact_reference_required')is not True or m.get('old_campaign_timings_applicable')is not False or m.get('require_goldens')is not True or m.get('require_regions')is not True or m.get('cohorts')!=105 or m.get('expected_regions')!=360 or len(m['cases'])!=210:raise ValueError('Exactnew105cohort/210pass fittingexperiment')
  for p in sources:
   want=m['runner_sha256']if p.name=='batch_runner.py'else m['input_sha256'].get(str(p))
   if want!=digest(p)or want not in ids.values():raise ValueError('Archivedanalysissourcemismatch '+str(p))
  if ids['job/ready.json']!=m['reviewed_ready_sha256']or ids['job/corpus.json']!=m['corpus_sha256']or ids['job/manager/workloads/iris-batch/batch.elf']!=m['elf_sha256']or m['elf_sha256']!=ELF:raise ValueError('Exactapprovedready/corpus/ELFbinding')
  ready=json.loads(data['job/ready.json']);corpus=json.loads(data['job/corpus.json'])
  with tarfile.open(archive,'r:gz')as t:
   raw=t.extractfile('job/manager/workloads/iris-batch/batch.elf').read();layout=json.load(t.extractfile('job/layout.json'));review=json.load(t.extractfile('job/review.json'))
  if hashlib.sha256(raw).hexdigest()!=ELF or ids['job/layout.json']!=ready['layout_sha256']or ids['job/review.json']!=ready['review_sha256']or ready['elf_sha256']!=ELF:raise ValueError('Actualbinary/layout/reviewidentity')
  binary=inspect(raw,corpus,layout)
  if binary!=review['compiled_and_layout_proof']or flatten(corpus)!=m['cases']:raise ValueError('Independentactualcompiledtable/layout/flattenedhostcases')
  member,report['guest_uart']=select_guest_uart(data,ids);text=data[member].decode('utf-8','strict');report['numeric']=validator().validate(text,corpus);rows=[json.loads(x[len('IRIS_REGION '):])for x in text.splitlines()if x.startswith('IRIS_REGION ')];spec={c['id']:c for c in m['cases']}
  for r in rows:r.update(cycles=r['end_cycle']-r['start_cycle'],semantic_parent_case_id=spec[r['case_id']]['semantic_parent_case_id'],internal_split=spec[r['case_id']]['internal_split'],ELF_sha256=ELF,source_case_id=r['case_id'])
  phases=m['commands'];report['lifecycle']=[{k:r.get(k)for k in['task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out']}for r in phases]
  if [(r['task'],r['status'])for r in phases]!=[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]or any(r['returncode']!=0 or r['timed_out']is not False for r in phases)or current['status']!='completed_uncertified'or current['cleanup_status']!='passed'or current.get('error')is not None or current.get('cleanup_error')is not None or m['status']!=current['status']or m['cleanup_status']!=current['cleanup_status']:raise ValueError('Completeownedfourphase success+cleanup required')
  if digest(archive)!=cap['archive_sha256']:raise ValueError('Archivechangedduringanalysis')
  (out/'observed.elf').write_bytes(raw);(out/'uartlog').write_bytes(data[member]);(out/'corpus.json').write_bytes(data['job/corpus.json']);(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n');(out/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');(out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));report.update(**{'pass':True},compiled_case_records=105,declared_host_cases=210,regions=360,by_hart=dict(collections.Counter(r['hart']for r in rows)),by_footprint_bytes=dict(collections.Counter(r['footprint_bytes']for r in rows)),counter_scope=corpus['counter_scope'],history_scope=corpus['protocol'],requested_byte_scope=corpus['requested_byte_scope'],qualification='ActualnewinstrumentedELF footprint scaling observations only; nocacheflush/coldpass/physicalDRAMmiss/traffic orfullSoCtimingclaim.')
 except(OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as e:report['error']=str(e)
 report['output_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['pass','archive_verified','regions','error']}));return 0 if report['pass']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve()))
