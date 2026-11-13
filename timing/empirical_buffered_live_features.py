#!/usr/bin/env python3
"""Join a qualified full/partial buffered native readback to its fresh FPGA ELF reference."""
import argparse,collections,hashlib,json,pathlib
from empirical_live_features_v2 import join,read_complete
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def require_receipt(receipt,regions,features,expected_elf):
 schema=receipt.get('schema')
 if receipt.get('pass')is not True:raise ValueError('Native readback is not qualified')
 if schema=='iris.buffered_campaign_checkpoint_replay.v1':
  if receipt.get('all_prefix_goldens_passed')is not True or receipt.get('status')!='passed_completed_case_prefix':raise ValueError('Incomplete native checkpoint')
 elif schema=='iris.buffered_campaign_native_readback.v1':
  if receipt.get('all_numeric_goldens_passed')is not True or receipt.get('status')!='completed_measured_regions_with_intentional_debugger_stop':raise ValueError('Incomplete native measurement run')
 elif schema=='iris.buffered_campaign_readback_validation.v2':
  if receipt.get('all_numeric_goldens_passed')is not True:raise ValueError('Reader repair did not qualify all goldens')
 else:raise ValueError('Unknown native readback contract')
 if receipt.get('normal_guest_exit_verified')is not False or receipt.get('hardware_contacted')is not False:raise ValueError('Wrong local post-ROI scope')
 hashes={**receipt.get('input_sha256',{}),**receipt.get('output_sha256',{})}
 for p,digest in hashes.items():
  if sha(p)!=digest:raise ValueError('Native input/output changed '+p)
 for path in (regions,features):
  if hashes.get(str(path.resolve()))!=sha(path):raise ValueError('Unbound readback artifact '+str(path))
 argv=receipt['argv']
 if sha(argv[-1])!=expected_elf:raise ValueError('Native and reference ELF differ')
 return hashes

def main(a):
 q=json.load(a.receipt.open());ref=json.load(a.reference_report.open())
 if ref.get('schema')!='iris.empirical_buffered_observation_normalization.v1' or ref.get('status')!='passed' or ref.get('observations_sha256')!=sha(a.observations):raise ValueError('Unqualified buffered reference observations')
 if ref.get('global_heldout_timings_consumed')is not False:raise ValueError('Global heldout contamination')
 corpus=json.load(a.corpus.open());elf_key='build/campaign-buffered-fit-v1/campaign.elf';expected_elf=ref['input_sha256'][elf_key]
 if sha(a.corpus)!=ref['input_sha256']['build/campaign-buffered-fit-v1/corpus.json']:raise ValueError('Reference corpus identity')
 hashes=require_receipt(q,a.regions,a.features,expected_elf)
 observations=[json.loads(s) for s in a.observations.read_text().splitlines()];native=[json.loads(s) for s in a.regions.read_text().splitlines()]
 if q['regions']!=len(native):raise ValueError('Qualified region count changed')
 raw,lines=read_complete(a.features);prefixes=[json.loads(s) for s in lines]
 for p in prefixes:
  if type(p.get('result_discarded'))is not bool:raise ValueError('Missing actual CSR return/discard status')
 returning=[p for p in prefixes if not p['result_discarded']]
 rows,stats=join(observations,native,returning,True)
 if len(rows)!=len(native):raise ValueError('Some qualified regions lack unique actual CSR endpoints')
 out=a.output;out.mkdir(parents=True,exist_ok=False)
 (out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows));(out/'native-receipt.snapshot.json').write_bytes(a.receipt.read_bytes())
 # This canonical baseline receipt is a fitting input, not a guest-exit claim.
 canonical={'schema':'iris.empirical_training_native_replay.v1','status':'qualified_partial_measured_regions' if stats['partial'] else 'qualified_all_measured_regions_post_ROI_stop',
  'argv':q['argv'],'input_sha256':{**q['input_sha256'],str(a.receipt.resolve()):sha(a.receipt),str(a.regions.resolve()):sha(a.regions),str(a.features.resolve()):sha(a.features)},
  'all_observed_numeric_goldens_passed':True,'normal_guest_exit_verified':False,'hardware_contacted':False,'global_heldout_timings_consumed':False,'native_region_count':len(rows)}
 (out/'native-baseline.json').write_text(json.dumps(canonical,indent=2,sort_keys=True)+'\n')
 families=collections.Counter();reporting=collections.Counter()
 for r in rows:
  reporting[r['family_for_reporting_only']]+=1
  for family,v in r['features'].items():families[family]+=v['instructions']
 report={'schema':'iris.empirical_buffered_runtime_feature_join.v1','status':'qualified_partial' if stats['partial'] else 'passed_all_measured_regions','joined_regions':len(rows),
   'reference_regions':4050,'partial':stats['partial'],'runtime_family_instruction_coverage':dict(families),'reporting_family_region_coverage':dict(reporting),
   'reference_archive_sha256':ref['reference_archive_sha256'],'input_sha256':{str(p.resolve().relative_to(ROOT)):sha(p) for p in [pathlib.Path(__file__).resolve(),ROOT/'timing/empirical_live_features_v2.py',a.observations,a.reference_report,a.receipt,a.regions,a.features,a.corpus]},
   'regions_sha256':sha(out/'regions.jsonl'),'native_baseline_sha256':sha(out/'native-baseline.json'),'reader_scope':'Actual completed case prefix; intentional post-ROI debugger stop; no whole guest exit or full end-to-end timing claim.',
   'labels_or_case_ids_are_runtime_features':False,'global_heldout_timings_consumed':False,'actual_parameter_fit_performed':False,'full_2pct_certified':False,'source_image_association_verified':False}
 (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--receipt',type=pathlib.Path,required=True);p.add_argument('--regions',type=pathlib.Path,required=True);p.add_argument('--features',type=pathlib.Path,required=True);p.add_argument('--corpus',type=pathlib.Path,default=ROOT/'build/campaign-buffered-fit-v1/corpus.json');p.add_argument('--observations',type=pathlib.Path,default=ROOT/'calibration/empirical-buffered-reference-v1/observations.jsonl');p.add_argument('--reference-report',type=pathlib.Path,default=ROOT/'calibration/empirical-buffered-reference-v1/report.json');p.add_argument('--output',type=pathlib.Path,required=True);main(p.parse_args())
