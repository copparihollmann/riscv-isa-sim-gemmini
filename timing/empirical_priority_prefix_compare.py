#!/usr/bin/env python3
"""Freeze common pre-FADD output prefixes without claiming a whole-run pass."""
import argparse,copy,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main(a):
 out=a.output;out.mkdir(exist_ok=False,parents=True);normalized=[];inputs={};identities=[]
 for name,directory in [('left',a.left),('right',a.right)]:
  run=json.load((directory/'run.json').open());raw=(directory/'features.jsonl').read_bytes();lines=raw[:raw.rfind(b'\n')+1].splitlines()
  if len(lines)<a.records:raise ValueError('Missing complete output prefix')
  prefix=b'\n'.join(lines[:a.records])+b'\n';(out/(name+'.prefix.jsonl')).write_bytes(prefix);(out/(name+'.run.snapshot.json')).write_bytes((directory/'run.json').read_bytes())
  records=[json.loads(s) for s in lines[:a.records]];identity={r['calibration_identity'] for r in records}
  if len(identity)!=1 or any(r['schema']!='iris.empirical.prefix.v1' for r in records):raise ValueError('Mixed/unqualified output prefix')
  identities.append(next(iter(identity)))
  for r in records:r.pop('calibration_identity')
  normalized.append(records)
  inputs.update({str(p.resolve().relative_to(ROOT)):sha(p) for p in [out/(name+'.prefix.jsonl'),out/(name+'.run.snapshot.json')]})
  for p,h in run['input_sha256'].items():
   if sha(p)!=h:raise ValueError('Actual binary/fixture/ELF input changed')
  inputs.update(run['input_sha256'])
 if normalized[0]!=normalized[1]:raise ValueError('Pre-FADD history differs beyond declared identity')
 result={'schema':'iris.empirical_priority_pre_fadd_memory_invariance.v2','pass':True,'exact_complete_CSR_prefix_dicts':a.records,'memory_route_regions':a.records//2,
  'excluded_field_only':'calibration_identity','declared_fixture_identities':identities,'other_metadata_and_all_model_cycles_features_memory_resources_exactly_equal':True,
  'whole_native_checkpoint_or_guest_completion_claimed':False,'numeric_memory_readback_not_claimed_by_this_output_comparison':True,'global_heldout_timings_consumed':False,
  'input_sha256':{**inputs,str(pathlib.Path(__file__).resolve().relative_to(ROOT)):sha(__file__)}}
 (out/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print('PASS',a.records,'SHA',sha(out/'report.json'))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--left',type=pathlib.Path,required=True);p.add_argument('--right',type=pathlib.Path,required=True);p.add_argument('--records',type=int,required=True);p.add_argument('--output',type=pathlib.Path,required=True);main(p.parse_args())
