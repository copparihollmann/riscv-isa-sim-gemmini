#!/usr/bin/env python3
"""Fair same-ELF comparison after fitting froze; no fitting or reselection."""
import collections,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def measure(rows):
 e=[r['signed_error_pct']for r in rows];a=sorted(map(abs,e));n=len(a);q=.9*(n-1);i=int(q)
 return{'regions':n,'median_absolute_error_pct':statistics.median(a),'p90_absolute_error_pct':a[i]+(a[min(i+1,n-1)]-a[i])*(q-i),'max_absolute_error_pct':max(a),'within2':sum(x<=2for x in a),'signed_median_pct':statistics.median(e),'instret_mismatches':sum(not x['instret_matches']for x in rows)}
out=ROOT/'build/hybrid7bd5-vs-selected28-sameELF-compute-v1';out.mkdir(exist_ok=False);reference=ROOT/'build/fpga-compute-fit-v1-001-analysis/regions.json';hw={(x['case_id'],x['hart']):x for x in load(reference)};split_path=ROOT/'build/compute-fit-v3/split.json';split=load(split_path)['split'];inputs={str(Path(__file__).resolve()):sha(__file__),str(reference):sha(reference),str(split_path):sha(split_path)}
models={};runs={'selected28':ROOT/'build/compute-fit-selected28-sameELF-baseline-v1','new_hybrid7bd5':ROOT/'build/compute-fit-7bd5-hybrid-selected-v1'}
for name,folder in runs.items():
 receipt=load(folder/'run.json')
 if receipt.get('pass')is not True or receipt.get('regions')!=1008 or receipt.get('actual_CSR_ELF_boundary_joins')!=2016:raise ValueError('Actual all1008 complete numeric/CSR run required')
 for path,h in {**receipt['input_sha256'],**receipt['output_sha256']}.items():
  if sha(path)!=h:raise ValueError('Baseline evidence changed')
 rows=[];groups=collections.defaultdict(list)
 for n in map(json.loads,(folder/'regions.jsonl').read_text().splitlines()):
  h=hw[n['case_id'],n['hart']];entry=split[n['parent_case_id']]
  if n['checksum']!=h['checksum']or n['expected_checksum']!=h['expected_checksum']:raise ValueError('Numerical outcome differs')
  rc=h['end_cycle']-h['start_cycle'];mc=n['end_cycle']-n['start_cycle'];r={'case_id':n['case_id'],'parent_case_id':n['parent_case_id'],'hart':n['hart'],'partition':entry['partition'],'family':entry['family'],'reference_cycles':rc,'native_cycles':mc,'signed_error_pct':100*(mc-rc)/rc,'instret_matches':n['instret_delta']==h['instret_delta']};rows.append(r)
  if entry['partition']=='train':groups[n['parent_case_id'],n['hart']].append(r['signed_error_pct']/100)
 if len(groups)!=272:raise ValueError('AllTRAIN groups required')
 by=collections.defaultdict(list)
 for r in rows:by[r['family']].append(r)
 models[name]={'run':str(folder/'run.json'),'all1008':measure(rows),'train':measure([r for r in rows if r['partition']=='train']),'developmentCV':measure([r for r in rows if r['partition']=='internal_validation']),'per_family':{k:measure(v)for k,v in sorted(by.items())},'ALL_TRAIN_objective':statistics.mean(statistics.median(v)**2for v in groups.values())}
 (out/(name+'-regions.jsonl')).write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));inputs[str(folder/'run.json')]=sha(folder/'run.json');inputs[str(folder/'regions.jsonl')]=sha(folder/'regions.jsonl')
old,new=models['selected28'],models['new_hybrid7bd5'];report={'schema':'iris.same_ELF_default_model_comparison.v1','pass':True,'all_numeric_goldens_passed':True,'same_source_ELF':True,'all1008_regions_and2016_CSRjoins_per_native':True,'models':models,'TRAIN_objective_relative_reduction_percent':100*(1-new['ALL_TRAIN_objective']/old['ALL_TRAIN_objective']),'non_regression_on_every_region':False,'default_selection_changed':False,'new_parameter_fit_performed_by_comparison':False,'parameter_reselection_performed':False,'internal_CV_is_development_only':True,'global_heldout_timings_consumed':False,'hardware_contacted':False,'full_2pct_certified':False,'source_image_association_verified':False,'input_sha256':inputs,'artifact_sha256':{p.name:sha(p)for p in out.iterdir()if p.is_file()}}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'TRAIN_reduction_pct':report['TRAIN_objective_relative_reduction_percent'],'selected28':old['all1008'],'hybrid':new['all1008'],'report_sha256':sha(out/'report.json')}))
