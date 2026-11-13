#!/usr/bin/env python3
"""Evaluate a new native epoch with frozen inherited costs; never refit them."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'firesim'))
from analyze_campaign import read_archive,select_guest_uart

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def quantile(values,f):
 v=sorted(values);p=f*(len(v)-1);a=int(p);return v[a]+(v[min(a+1,len(v)-1)]-v[a])*(p-a)
def metrics(rows):
 signed=[r['signed_error_percent']for r in rows];absolute=list(map(abs,signed))
 return {'regions':len(rows),'absolute_median_pct':statistics.median(absolute),'absolute_p90_pct':quantile(absolute,.9),'absolute_max_pct':max(absolute),
  'signed_median_pct':statistics.median(signed),'signed_mean_pct':statistics.mean(signed),'within_2pct_count':sum(x<=2for x in absolute),'within_2pct_fraction':sum(x<=2for x in absolute)/len(rows),'instret_mismatches':sum(not x['instret_matches']for x in rows)}


def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 run=ROOT/'build/compute-fit-7bd5-hybrid28-inherited-v1';build=ROOT/'build/compute-fit-v3';reference=ROOT/'build/fpga-compute-fit-v1-001-analysis';package=ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f'
 fixture=ROOT/'build/empirical-V8-hybrid28-inputs-v1/hybrid.fixture';origin=ROOT/'calibration/empirical-priority-28a0-binding-v2/runtime-binding.json';parameters=ROOT/'calibration/empirical-priority-28a0-runtime-v2/parameters.json'
 native=load(run/'run.json');ref=load(reference/'report.json');binding=load(origin);manifest=load(package/'manifest.json');corpus=load(build/'corpus.json');split=load(build/'split.json')['split']
 if native.get('pass')is not True or native.get('regions')!=1008 or native.get('actual_CSR_ELF_boundary_joins')!=2016 or native.get('normal_guest_exit_verified')is not False:raise ValueError('Own new-native all1008 measurement required')
 for path,value in {**native['input_sha256'],**native['output_sha256']}.items():
  if sha(path)!=value:raise ValueError('Native replay source/evidence changed')
 for key in('pass','archive_verified','functional_checks_passed','managed_run_passed','fitting_only','fitting_observations_available'):
  if ref.get(key)is not True:raise ValueError('Qualified compute fitting reference required')
 if ref.get('schema')!='iris.compute_fitting_archive_analysis.v1'or ref.get('global_heldout')is not False or ref.get('archive_sha256')!='326faca74b31737342acc176157e4afa2c062b28c43904b7e42cf8a1a4dd77c7':raise ValueError('Wrong independent compute fitting reference')
 for name,value in ref['artifact_sha256'].items():
  if sha(reference/name)!=value:raise ValueError('Reference artifact changed')
 job=Path(ref['job']);current=load(job/'run.json');archive=Path(ref['archive'])
 if sha(job/'run.json')!=ref['current_run_manifest_sha256']or sha(archive)!=ref['archive_sha256']:raise ValueError('Actual managed reference changed')
 data,ids=read_archive(archive,current['capture']['captured_run_manifest_sha256']);frozen=load(job/'run.json')
 if ids['job/corpus.json']!=sha(build/'corpus.json')or ids['job/manager/workloads/iris-batch/batch.elf']!=sha(build/'campaign.elf'):raise ValueError('Hardware/new-native source ELF mismatch')
 member,uart=select_guest_uart(data,ids);hardware=[json.loads(x.split(' ',1)[1])for x in data[member].decode().splitlines()if x.startswith('IRIS_REGION ')]
 if hardware!=load(reference/'regions.json'):raise ValueError('Derived hardware regions differ from archived UART')
 predicted=[json.loads(x)for x in(run/'regions.jsonl').read_text().splitlines()];cases={x['case_id']:x for x in corpus['cases']}
 if len(predicted)!=1008 or len(hardware)!=1008:raise ValueError('All1008 rows required without filtering')
 if sha(parameters)!=binding['parameters_sha256']:raise ValueError('Inherited parameter provenance changed')
 old_fixture=ROOT/'calibration/empirical-priority-28a0-runtime-v2/runtime.fixture'
 canonical=lambda text:[x for x in text.splitlines()if not x.startswith(('empirical_profile ','empirical_read_overlap '))]
 if canonical(fixture.read_text())!=canonical(old_fixture.read_text()):raise ValueError('Coefficient transfer changed values or unrelated model rules')
 rows=[];groups=collections.defaultdict(list)
 for n,h in zip(predicted,hardware):
  if(n['case_id'],n['hart'])!=(h['case_id'],h['hart']):raise ValueError('Prediction/reference case/hart order differs')
  c=cases[n['case_id']];s=split[c['parent_case_id']];hart=n['hart']
  for r in(n,h):
   if any(type(r.get(k))is not int for k in('hart','start_cycle','end_cycle','instret_delta','checksum','expected_checksum'))or not 0<=r['start_cycle']<r['end_cycle']<1<<64 or r['instret_delta']<=0 or r.get('pass')is not True:raise ValueError('Typed complete actual region required')
   if r['checksum']!=c['expected_checksums'][hart]or r['expected_checksum']!=c['expected_checksums'][hart]:raise ValueError('Independent source golden differs')
  rc=h['end_cycle']-h['start_cycle'];mc=n['end_cycle']-n['start_cycle']
  row={k:n[k]for k in('case_id','parent_case_id','trial_id','hart')};row.update(family=s['family'],partition=s['partition'],hardware_cycles=rc,native_cycles=mc,signed_error_percent=100*(mc-rc)/rc,hardware_instret=h['instret_delta'],native_instret=n['instret_delta'],instret_matches=h['instret_delta']==n['instret_delta'])
  rows.append(row);groups[row['parent_case_id'],hart].append(row)
 parent_rows=[]
 for(parent,hart),values in sorted(groups.items()):
  if sorted(x['trial_id']for x in values)!=[0,1,2]:raise ValueError('All trials remain grouped')
  hm=statistics.median(x['hardware_cycles']for x in values);nm=statistics.median(x['native_cycles']for x in values)
  parent_rows.append({'parent_case_id':parent,'hart':hart,'family':values[0]['family'],'partition':values[0]['partition'],'hardware_median_cycles':hm,'native_median_cycles':nm,'signed_error_percent':100*(nm-hm)/hm,'instret_matches':all(x['instret_matches']for x in values)})
 by_family=collections.defaultdict(list)
 for row in rows:by_family[row['family']].append(row)
 validation={part:metrics([r for r in rows if r['partition']==part])for part in('train','internal_validation')}
 (out/'regions.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n'for x in rows));(out/'parent-groups.json').write_text(json.dumps(parent_rows,indent=2)+'\n')
 with(out/'regions.csv').open('w')as stream:
  w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 paths=[Path(__file__).resolve(),run/'run.json',run/'regions.jsonl',run/'features.jsonl',build/'campaign.elf',build/'corpus.json',build/'split.json',reference/'report.json',reference/'regions.json',job/'run.json',archive,fixture,old_fixture,origin,parameters,package/'manifest.json',ROOT/'build/memory-routes-current-7bd5-causal-review-v1/report.json']
 result={'schema':'iris.empirical_inherited_runtime_evaluation.v1','pass':True,'actual_own_native_replay_completed':True,'regions':1008,'actual_CSR_ELF_boundary_joins':2016,
  'all_numeric_goldens_passed':True,'normal_guest_exit_verified':False,'timed_scope':'all measured regions via intentional post-ROI debugger stop',
  'native_binary_sha256':manifest['binary_sha256'],'uart_library_sha256':manifest['uart_sha256'],'fixture_sha256':sha(fixture),
  'parameter_refit_for_this_native_performed':False,'coefficient_selection_for_this_native_performed':False,'parameters_changed':False,'global_heldout_timings_consumed':False,
  'inherited_parameters':{'parameters':str(parameters),'parameters_sha256':sha(parameters),'binding':str(origin),'binding_sha256':sha(origin),'origin_native_sha256':binding['native_binary_sha256'],'origin_fit_report_sha256':binding['fit_report_sha256'],'origin_actual_parameter_fit_performed':True,'qualified_by_transfer':False},
  'reference':{'analysis':str(reference/'report.json'),'analysis_sha256':sha(reference/'report.json'),'run_manifest':str(job/'run.json'),'run_manifest_sha256':sha(job/'run.json'),'capture_archive_sha256':ref['archive_sha256'],'elf_sha256':sha(build/'campaign.elf')},'additional_parameter_origin_reference':binding['reference'],'validation_metrics':validation,'overall':metrics(rows),'family_metrics':{k:metrics(v)for k,v in sorted(by_family.items())},
  'all_TRAIN_parent_group_normalized_MSE':statistics.mean((r['signed_error_percent']/100)**2 for r in parent_rows if r['partition']=='train'),
  'instret_mismatch_scope':dict(collections.Counter(x['family']for x in rows if not x['instret_matches'])),
  'methodology':'Fixed inherited coefficients chosen before this new native evaluation; all1008 fitting/development rows retained. Parent split inherited from pre-hardware frozen compute packet; internal validation has been viewed in development and is not blind acceptance.',
  'readiness':{'own_compute_numeric_and_CSR_joins':True,'own_memory2592_causal_evaluation':True,'source_frontend_flags_enabled':False,'frontend_scope':'explicit legacy28 approximation; source RAS model not selected','default_promotion_allowed':False,'OS_compiler_qualification':'Owned by root/other agent; not inferred by this evaluation.'},
  'full_model_certified':False,'full_2pct_certified':False,'source_image_association_verified':False,'hardware_contacted':False,'input_sha256':{str(x):sha(x)for x in paths}}
 result['artifact_sha256']={x.name:sha(x)for x in out.iterdir()if x.is_file()};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 envelope={'schema':'iris.empirical_inherited_runtime_binding.v1','calibration_identity':native['calibration_identity'],'native_binary_sha256':manifest['binary_sha256'],'uart_library_sha256':manifest['uart_sha256'],'fixture_sha256':sha(fixture),'parameters_sha256':sha(parameters),'parameters_origin_binding_sha256':sha(origin),'evaluation_report_sha256':sha(out/'report.json'),'actual_parameter_fit_performed_for_this_native':False,'actual_native_evaluation_performed':True,'global_heldout_timings_consumed':False,'fixed_inherited_coefficients':True,'base_hz':500000000,'rtc_divider':1000,'counter_policy':'source-ungated-stall','split':binding['split'],'reference':{'analysis':str(reference/'report.json'),'analysis_sha256':sha(reference/'report.json'),'run_manifest':str(job/'run.json'),'run_manifest_sha256':sha(job/'run.json'),'capture_archive_sha256':ref['archive_sha256'],'elf_sha256':sha(build/'campaign.elf')},'additional_parameter_origin_reference':binding['reference'],'validation_metrics':validation,'publication_scope':'Nondefault mechanism successor only; inherited parameters explicitly identified, no own-native refit or qualification transfer. Explicit legacy28 approximate frontend mode; this is not the source-frontend qualification.','full_model_certified':False,'full_2pct_certified':False,'source_image_association_verified':False,'input_sha256':{**result['input_sha256'],str(out/'report.json'):sha(out/'report.json')}}
 (out/'runtime-evaluation-binding.json').write_text(json.dumps(envelope,indent=2)+'\n');print(json.dumps({'pass':True,'validation_metrics':validation,'output':str(out),'binding_sha256':sha(out/'runtime-evaluation-binding.json')}))


if __name__=='__main__':main()
