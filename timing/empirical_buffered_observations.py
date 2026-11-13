#!/usr/bin/env python3
"""Normalize only a complete, archived exact-ELF buffered FPGA reference."""
import argparse,csv,hashlib,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def uint(x,key):
 if type(x)is int:n=x
 elif type(x)is str and re.fullmatch(r'[0-9]+',x):n=int(x)
 else:raise ValueError('Unsigned integer required '+key)
 if not 0<=n<2**64:raise ValueError('Unsigned integer out of range '+key)
 return n

def normalize_rows(raw,corpus,split):
 expected={(c['case_id'],h):c for c in corpus['cases'] for h in range(3) if c['mask']&(1<<h)};seen=set();rows=[]
 for row in raw:
  r=dict(row)
  for k in ('hart','mask','trial_id','start_cycle','end_cycle','cycles','instret_delta','checksum','expected_checksum'):r[k]=uint(r[k],k)
  key=(r['case_id'],r['hart'])
  if key not in expected or key in seen:raise ValueError('Unknown/inactive/duplicate reference row')
  seen.add(key);c=expected[key];parent=c['parent_case_id'];s=split['split'][parent]
  for k in ('parent_case_id','semantic_parent_case_id','suite','trial_id','mask'):
   if r[k]!=c[k]:raise ValueError('Reference case metadata differs '+k)
  if s['semantic_parent_case_id']!=c['semantic_parent_case_id']:raise ValueError('Split semantic mismatch')
  if r['end_cycle']<=r['start_cycle'] or r['cycles']!=r['end_cycle']-r['start_cycle']:raise ValueError('Counter span mismatch/nonpositive')
  golden=c['expected_checksums'][r['hart']]
  if r['checksum']!=golden or r['expected_checksum']!=golden:raise ValueError('Reference golden mismatch')
  rows.append({'schema':'iris.empirical_fitting_observation.v1','dataset':'buffered.v1','case_id':r['case_id'],'parent_case_id':parent,
   'semantic_parent_case_id':c['semantic_parent_case_id'],'semantic_group':s['semantic_group'],'hart':r['hart'],'trial_id':r['trial_id'],
   'suite':r['suite'],'family':s['family'],'partition':s['partition'],'cycles':r['cycles'],'start_cycle':r['start_cycle'],'end_cycle':r['end_cycle'],
   'instret_delta':r['instret_delta'],'checksum':r['checksum'],'expected_checksum':golden,'actual_FPGA_reference':True,
   'labels_are_not_runtime_features':True,'global_heldout':False})
 if seen!=set(expected) or len(rows)!=4050:raise ValueError('Incomplete reference coverage')
 return sorted(rows,key=lambda r:(r['case_id'],r['hart']))

def main(a):
 analysis=a.analysis;report=json.load((analysis/'report.json').open());corpuspath=a.build/'corpus.json';corpus=json.load(corpuspath.open());split=json.load(a.split.open());elf=a.build/'campaign.elf'
 if report.get('schema')!='iris.buffered_fitting_archive_analysis.v1':raise ValueError('Not a new buffered reference')
 for k in ('pass','archive_verified','functional_checks_passed','managed_run_passed','fitting_observations_available','fitting_only'):
  if report.get(k)is not True:raise ValueError('Unqualified reference '+k)
 if report.get('global_heldout')is not False or report.get('old_campaign_timings_applicable')is not False:raise ValueError('Wrong reference split/source scope')
 if report.get('cleanup_status')!='passed' or report.get('capture_status')!='captured':raise ValueError('Missing owned cleanup/capture')
 if sha(report['archive'])!=report['archive_sha256']:raise ValueError('Reference archive changed')
 for name in ('regions.csv','corpus.json','campaign.elf'):
  if sha(analysis/name)!=report['artifact_sha256'][name]:raise ValueError('Analysis artifact changed '+name)
 if sha(analysis/'corpus.json')!=sha(corpuspath) or sha(analysis/'campaign.elf')!=sha(elf):raise ValueError('Reference labels from different ELF/corpus')
 if split['input_sha256'][str(corpuspath.resolve().relative_to(ROOT))]!=sha(corpuspath):raise ValueError('Prelaunch split corpus changed')
 rows=normalize_rows(list(csv.DictReader((analysis/'regions.csv').open())),corpus,split);out=a.output;out.mkdir(exist_ok=False,parents=True)
 data=''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows);(out/'observations.jsonl').write_text(data)
 result={'schema':'iris.empirical_buffered_observation_normalization.v1','status':'passed','rows':len(rows),'reference_archive_sha256':report['archive_sha256'],
  'runtime_identity':report['runtime_identity'],'input_sha256':{str(p.resolve().relative_to(ROOT)):sha(p) for p in [pathlib.Path(__file__).resolve(),analysis/'report.json',analysis/'regions.csv',corpuspath,a.split,elf]},
  'observations_sha256':sha(out/'observations.jsonl'),'old_ELF_cycles_transferred':False,'global_heldout_timings_consumed':False,'source_image_association_verified':False,'full_2pct_certified':False}
 (out/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--analysis',type=pathlib.Path,required=True);p.add_argument('--build',type=pathlib.Path,default=ROOT/'build/campaign-buffered-fit-v1');p.add_argument('--split',type=pathlib.Path,default=ROOT/'calibration/empirical-buffered-v1/split.json');p.add_argument('--output',type=pathlib.Path,required=True);main(p.parse_args())
