#!/usr/bin/env python3
"""Freeze only exact Rocket eligible SETUP/WORK zero adjustment; no labels."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
FAMILIES=['rvv.integer','rvv.fadd.fp16','rvv.fadd.fp32','rvv.fadd.fp64','memory.vector.load','memory.vector.store']
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 parent=ROOT/'build/warm-OPU-inputs-v2/baseline.fixture';original=parent.read_text();base=[];zero=[];changes=[];present=[]
 for i,line in enumerate(original.splitlines()):
  fields=line.split();z=list(fields)
  if fields and fields[0]=='empirical_profile':
   assert len(fields)==4 and fields[3]=='bounded';fields[2]='iris-rvv-hart2-only-7108-inherited-v1';z[2]='iris-rvv-hart2-only-7108-ownzero-v1'
  elif len(fields)==10 and fields[0]=='empirical_family' and fields[1]=='2' and fields[2]in FAMILIES:
   present.append(fields[2]);z[4:6]=['0','0'];changes.append(dict(line=i+1,hart=2,family=fields[2],old_setup=fields[4],old_work=fields[5],new_setup=z[4],new_work=z[5],other_tokens_identical=True))
  base.append(' '.join(fields)if fields else line);zero.append(' '.join(z)if z else line)
 assert sorted(present)==sorted(FAMILIES[1:]) and len(changes)==5
 for a,b in zip(base,zero):
  aa=a.split();bb=b.split()
  if a==b:continue
  if aa[0]=='empirical_profile':assert aa[:2]==bb[:2]and aa[3:]==bb[3:];continue
  assert aa[:4]==bb[:4]and aa[6:]==bb[6:]and aa[0]=='empirical_family'and aa[1]=='2'and aa[2]in FAMILIES
 (out/'inherited.fixture').write_text('\n'.join(base)+'\n');(out/'ownzero.fixture').write_text('\n'.join(zero)+'\n')
 inputs=[Path(__file__).resolve(),ROOT/'pipeline/replay_rvv_hart2_only_v1.py',parent,ROOT/'build/warm-OPU-frozen-7108a6ec-v1/manifest.json',ROOT/'build/rvv-hart2-only-v1/ready.json',ROOT/'build/rvv-hart2-only-v1/corpus.json',ROOT/'calibration/rvv-identify-compact-v1/fit-plan.json',ROOT/'calibration/rvv-identify-compact-v1/split.json']
 proof=dict(schema='iris.rvv_hart2_only_zero_adjustment_proof.v1',**{'pass':True},eligible_families=FAMILIES,exact_changed_lines=changes,explicit_changed_setup_work_tokens=10,implicit_integer_setup_work=[0,0],integer_rule_absent_and_native_default_resource_II_preserved=True,all_other_directives_resources_intervals_services_modes_unchanged=True,only_additional_difference='empirical_profile identity token',native_binary_sha256='7108a6ecfd98e6d8c4c983f7b089dbda99d4a143e7e189a7b99eedc322d79d27',inherited_parameters_not_fitted_to_this_new_ELF=True,hardware_timing_labels_consumed=False,fit_performed=False,input_sha256={str(p):sha(p)for p in inputs},artifact_sha256={n:sha(out/n)for n in('inherited.fixture','ownzero.fixture')})
 (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 plan=dict(schema='iris.rvv_hart2_only_frozen_fit_plan.v1',frozen_before_new_hardware_labels=True,hardware_timing_labels_consumed=False,fit_authorized=False,eligible_families=FAMILIES,parameters=12,rows_TRAIN_required=432,reserved_rows_root_only=156,all_repetitions_and_rows_retained=True,baseline='actual ownzero replay of exact52ab5cf8 ELF/native7108; no posthoc subtraction',features='actual retained native family instruction/work prefix differences; group byfamily andRocket only',estimator='Deterministic joint nonnegative relative least-squares on total begin-to-drain cycles, targetHWminus actualownzero; coordinate descent tolerance1e-12/max10000 iterations; no intercept,negativecost,PC/case/triallookup,rowfilter ormodegrid; rank deficiency failsclosed',phase_policy='Total window only for fit; issue anddrain separately reported, no invented perphaseinstret',nonlinear_validation='Freeze parameters then actual sameELF replay; include all432TRAIN; root-only156reserved never usedforfit/selection',unchanged='CPU/cache/outer/controller/clock/IRQ/resources/II/h0h1/otherfamilies',source_floor='WholeVRF owner serialization, sharedFPU and conservative vector-memory boundaries maymakepositive residualunfit; report, neverhide',source_identity_sha256=sha(ROOT/'build/warm-OPU-frozen-7108a6ec-v1/manifest.json'),ELF_sha256='52ab5cf8515989d2dfddf79c89e7c4802abf6344f2d21c41b9c9cfa46cfad8c3',parent_fit_plan_sha256=sha(ROOT/'calibration/rvv-identify-compact-v1/fit-plan.json'),proof_sha256=sha(out/'proof.json'))
 (out/'fit-plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps(dict(fixture_sha256=proof['artifact_sha256'],fit_plan_sha256=sha(out/'fit-plan.json'),proof_sha256=sha(out/'proof.json'))))
if __name__=='__main__':main()
