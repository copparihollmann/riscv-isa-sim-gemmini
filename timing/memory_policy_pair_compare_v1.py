#!/usr/bin/env python3
"""Compare a frozen opt-in memory-policy epoch with exact OFF parity."""
import argparse,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser(__doc__)
 for n in('before','after','off','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);left,right=load(a.before/'report.json'),load(a.after/'report.json')
 for folder,report in((a.before,left),(a.after,right)):
  if report.get('pass')is not True or report.get('regions')!=2592 or report.get('parameter_fit_performed')is not False:raise ValueError('Complete fixed2592 reference comparison required')
  for name,value in {**report['input_sha256'],**{str(folder/k):v for k,v in report['artifact_sha256'].items()}}.items():
   if sha(name)!=value:raise ValueError('Frozen comparison/evidence changed')
 before_run=Path(left['native']['run']).parent;off_run=load(a.off/'run.json')
 if off_run.get('pass')is not True or off_run.get('regions')!=2592:raise ValueError('Actual all2592 OFF run required')
 for name in('features.jsonl','region-features.jsonl','regions.jsonl','stdout','stderr'):
  if(before_run/name).read_bytes()!=(a.off/name).read_bytes():raise ValueError('OFF no longer preserves native baseline')
 normalize=lambda f:[x for x in Path(f).read_text().splitlines()if not x.startswith(('empirical_profile ','empirical_dcache_random '))]
 if normalize(left['native']['fixture'])!=normalize(right['native']['fixture']):raise ValueError('Policy comparison changed costs or other modes')
 x=[json.loads(l)for l in(a.before/'regions.jsonl').read_text().splitlines()];y=[json.loads(l)for l in(a.after/'regions.jsonl').read_text().splitlines()];paired=[]
 for old,new in zip(x,y):
  if(old['case_id'],old['hart'],old['hardware_cycles'])!=(new['case_id'],new['hart'],new['hardware_cycles']):raise ValueError('Not the same actual memory reference')
  paired.append({'case_id':old['case_id'],'hart':old['hart'],'target':old['target'],'kind':old['kind'],'pattern':old['pattern'],'mask':old['mask'],'trial_id':old['trial_id'],'hardware_cycles':old['hardware_cycles'],'before_cycles':old['native_cycles'],'after_cycles':new['native_cycles'],'before_signed_error_pct':old['signed_error_percent'],'after_signed_error_pct':new['signed_error_percent'],'absolute_error_delta_pct':abs(new['signed_error_percent'])-abs(old['signed_error_percent'])})
 (out/'paired-regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in paired))
 result={'schema':'iris.memory_policy_actual_fixed_pair.v1','pass':True,'regions':2592,'all_numeric_goldens':True,'costs_and_other_modes_unchanged':True,'OFF_entire_prefix_and_readback_byteequal':True,'changed_cycle_spans':sum(r['before_cycles']!=r['after_cycles']for r in paired),'improved_absolute_error_rows':sum(r['absolute_error_delta_pct']<0for r in paired),'worsened_absolute_error_rows':sum(r['absolute_error_delta_pct']>0for r in paired),'unchanged_absolute_error_rows':sum(r['absolute_error_delta_pct']==0for r in paired),'before':left['metrics_all'],'after':right['metrics_all'],'parameter_fit_performed':False,'default_selection_changed':False,'global_heldout_timings_consumed':False,'hardware_contacted':False,'full_2pct_certified':False,'source_image_association_verified':False,'scope':'Source-congruent opt-in replacement mechanism with model miss-allocation phase proxy; no exact physical cache state/edge, whole-model, image or universal accuracy claim.','input_sha256':{str(x.resolve()):sha(x)for x in(Path(__file__),a.before/'report.json',a.after/'report.json',a.off/'run.json',Path(left['native']['fixture']),Path(right['native']['fixture']))},'artifact_sha256':{'paired-regions.jsonl':sha(out/'paired-regions.jsonl')}}
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'improved':result['improved_absolute_error_rows'],'worsened':result['worsened_absolute_error_rows'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
