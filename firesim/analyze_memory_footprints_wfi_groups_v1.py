#!/usr/bin/env python3
"""Validate the exact captured footprint experiment without assuming DRAMmisses."""
import argparse,collections,hashlib,json,sys,tarfile,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from analyze_campaign import read_archive as verified_archive,select_guest_uart
from check_memory_footprint_wfi_groups_clint_v1 import inspect_clint_window
from batch_runner import digest
from memory_footprints_wfi_groups_review_v1 import validator,inspect,flatten,ELF
ROLE='memory_footprint_WFI_global_time_groups_fitting_v1'
PRELAUNCH_ANALYZER=ROOT/'firesim/analyze_memory_footprints_wfi_groups_v1.py'
def ready_member(archive,identities):
 name='job/ready.json'
 if name not in identities:raise ValueError('Archived ready member missing')
 with tarfile.open(archive,'r:gz')as t:
  m=t.getmember(name)
  if not m.isfile()or m.size>1048576:raise ValueError('Ready must be bounded regular JSON')
  raw=t.extractfile(m).read()
 if hashlib.sha256(raw).hexdigest()!=identities[name]:raise ValueError('Archived ready member changed')
 return raw
def read_archive(archive,expected_manifest):
 data,identities=verified_archive(archive,expected_manifest)
 data['job/ready.json']=ready_member(archive,identities)
 return data,identities
def partial_groups(text,corpus):
 validator().validate_corpus(corpus);seen=[];groups=[];prior={};expected=validator().canonical()
 for line in text.splitlines():
  if line.startswith('IRIS_REGION '):
   r=json.loads(line[len('IRIS_REGION '):]);i=len(seen)
   if i>=360:raise ValueError('Partial prefix exceeds canonical360')
   c=expected[i]
   if any(type(r.get(k))is not type(v)or r.get(k)!=v for k,v in c.items()):raise ValueError('Partial prefix semantic/golden identity')
   if any(type(r.get(k))is not int or not 0<=r[k]<2**64 for k in['start_cycle','end_cycle','instret_delta','mtime_before','mtime_after']):raise ValueError('Partial typed counters')
   if r['end_cycle']<=r['start_cycle']or r['start_cycle']<prior.get(r['hart'],0)or r['instret_delta']<3*r['body_loads']+1 or r['mtime_after']<r['mtime_before']:raise ValueError('Partial counter/window progress')
   for k,v in[('mtime_hz',500000),('source_core_cycles_per_mtime_tick',1000),('mtime_quantization_error_bound_core_cycles',1000),('mtime_scope','encloses_CSR_ROI_with_sampling_overhead')]:
    if type(r.get(k))is not type(v)or r.get(k)!=v:raise ValueError('Partial CLINT scope')
   prior[r['hart']]=r['end_cycle'];seen.append(r)
  if line.startswith('IRIS_FOOTPRINT_GROUP '):
   g=json.loads(line[len('IRIS_FOOTPRINT_GROUP '):])
   if g!=dict(group=len(groups),records=len(seen))or type(g.get('group'))is not int or type(g.get('records'))is not int or len(seen)!=24*(len(groups)+1):raise ValueError('Partial group frontier/order')
   groups.append(g)
 if not groups:raise ValueError('No fully emitted group frontier')
 return seen[:len(groups)*24],dict(normal_completion=False,full_run_passed=False,complete_groups=len(groups),qualified_prefix_regions=len(groups)*24,unqualified_trailing_rows=len(seen)-len(groups)*24,source_case_only=True,calibration_usable=False)
def analyze(job,out):
 if out.exists()or job==out or job in out.parents:raise ValueError('Freshanalysisoutsidejob')
 out.mkdir(parents=True);current=json.loads((job/'run.json').read_text());sources=[PRELAUNCH_ANALYZER,ROOT/'firesim/memory_footprints_wfi_groups_review_v1.py',ROOT/'firesim/check_memory_footprint_wfi_groups_clint_v1.py',ROOT/'benchmarks/memory_footprints_mtime_wfi_groups_v8/validate.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py'];report=dict(schema='iris.memory_footprint_mtime_archive_analysis.v1',**{'pass':False},hardware_contacted=False,fitting_only=True,global_heldout=False,new_exact_reference=True,physical_hit_or_miss_measured=False,physical_memory_traffic_measured=False,source_image_association_verified=False,timing_accuracy_certified=False,calibration_usable=False,input_sha256={str(p):digest(p)for p in sources},current_manifest_sha256=digest(job/'run.json'))
 try:
  report['input_sha256'][str(Path(__file__).resolve())]=digest(__file__)
  report['analysis_identity']={'prelaunch_source':str(PRELAUNCH_ANALYZER),'prelaunch_source_sha256':digest(PRELAUNCH_ANALYZER),'executed_source':str(Path(__file__).resolve()),'executed_source_sha256':digest(__file__),'postrun_change':'Read and verify ready.json bytes from inventory-verified archive; all prelaunch validators and numeric checks unchanged.'}
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
  binary=inspect(raw,corpus,layout);report['compiled_CLINT_window']=inspect_clint_window(raw)
  if binary!=review['compiled_and_layout_proof']or flatten(corpus)!=m['cases']:raise ValueError('Independentactualcompiledtable/layout/flattenedhostcases')
  member,report['guest_uart']=select_guest_uart(data,ids);text=data[member].decode('utf-8','strict');(out/'uartlog').write_bytes(data[member]);(out/'observed.elf').write_bytes(raw)
  if current['status']!='completed_uncertified':
   prefix,proof=partial_groups(text,corpus);(out/'partial-qualified-groups.json').write_text(json.dumps(prefix,indent=2)+'\n');report['partial_diagnostic']=proof;raise ValueError('Hardware run failed; complete emitted group prefix retained, NOT normal completion')
  report['numeric']=validator().validate(text,corpus);rows=[json.loads(x[len('IRIS_REGION '):])for x in text.splitlines()if x.startswith('IRIS_REGION ')];spec={c['id']:c for c in m['cases']}
  for r in rows:r.update(mtime_delta=r['mtime_after']-r['mtime_before'],quantized_global_window_source_core_cycles=(r['mtime_after']-r['mtime_before'])*1000,global_window_scope='encloses_CSR_ROI_with_sampling_overhead',no_overhead_subtraction=True,global_quantization_error_bound_core_cycles=1000,cycles=r['end_cycle']-r['start_cycle'],semantic_parent_case_id=spec[r['case_id']]['semantic_parent_case_id'],internal_split=spec[r['case_id']]['internal_split'],ELF_sha256=ELF,source_case_id=r['case_id'])
  phases=m['commands'];report['lifecycle']=[{k:r.get(k)for k in['task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out']}for r in phases]
  if [(r['task'],r['status'])for r in phases]!=[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]or any(r['returncode']!=0 or r['timed_out']is not False for r in phases)or current['status']!='completed_uncertified'or current['cleanup_status']!='passed'or current.get('error')is not None or current.get('cleanup_error')is not None or m['status']!=current['status']or m['cleanup_status']!=current['cleanup_status']:raise ValueError('Completeownedfourphase success+cleanup required')
  if digest(archive)!=cap['archive_sha256']:raise ValueError('Archivechangedduringanalysis')
  (out/'observed.elf').write_bytes(raw);(out/'uartlog').write_bytes(data[member]);(out/'corpus.json').write_bytes(data['job/corpus.json']);(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n');(out/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');(out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));report.update(**{'pass':True},compiled_case_records=105,declared_host_cases=210,regions=360,by_hart=dict(collections.Counter(r['hart']for r in rows)),by_footprint_bytes=dict(collections.Counter(r['footprint_bytes']for r in rows)),global_time_scope=corpus['mtime_scope'],mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,global_quantization_error_bound_core_cycles=1000,global_accuracy_2percent_claimed=False,counter_scope=corpus['counter_scope'],history_scope=corpus['protocol'],requested_byte_scope=corpus['requested_byte_scope'],qualification='ActualnewinstrumentedELF footprint scaling observations only; nocacheflush/coldpass/physicalDRAMmiss/traffic orfullSoCtimingclaim.')
 except(OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as e:report['error']=str(e)
 report['output_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['pass','archive_verified','regions','error']}));return 0 if report['pass']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve()))
