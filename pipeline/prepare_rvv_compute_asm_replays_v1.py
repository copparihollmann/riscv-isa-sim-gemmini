#!/usr/bin/env python3
"""Source-selected C12TK124 primary and exact eligible h0/1-only zero baseline."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FAMILIES=['rvv.integer','rvv.fadd.fp16','rvv.fadd.fp32','rvv.fadd.fp64','memory.vector.load','memory.vector.store','vme.row_move']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 parent=ROOT/'build/warm-OPU-TK124-inputs-v1/OPU-TK124-ON.fixture';original=parent.read_text();assert sha(parent)=='63006e95a9367c1e559ea025f2ceb8cbc1c3587ab82a28ceb0daa79b25287562';base=[];zero=[];changes=[];present=[]
 for i,line in enumerate(original.splitlines()):
  t=line.split();z=list(t)
  if t and t[0]=='empirical_profile':
   assert len(t)==4 and t[3]=='bounded';t[2]='iris-rvv-compute-asm-C12TK124-inherited-v1';z[2]='iris-rvv-compute-asm-C12TK124-ownzero-v1'
  elif len(t)==10 and t[0]=='empirical_family'and t[1]in('0','1')and t[2]in FAMILIES:
   present.append((int(t[1]),t[2]));z[4:6]=['0','0'];changes.append(dict(line=i+1,hart=int(t[1]),family=t[2],old_setup=t[4],old_work=t[5],new_setup='0',new_work='0',other_tokens_identical=True))
  base.append(' '.join(t)if t else line);zero.append(' '.join(z)if z else line)
 assert sorted(present)==sorted((h,f)for h in(0,1)for f in FAMILIES)and len(changes)==14
 for a,b in zip(base,zero):
  if a==b:continue
  x,y=a.split(),b.split()
  if x[0]=='empirical_profile':assert x[:2]+x[3:]==y[:2]+y[3:];continue
  assert x[:4]+x[6:]==y[:4]+y[6:]and x[0]=='empirical_family'and x[1]in('0','1')and x[2]in FAMILIES
 assert [l for l in base if l.startswith('empirical_opu_entry ')]==['empirical_opu_entry source-VDQ4-IQ3-entry-MM-TK124-COMplus1-v3']
 for name,lines in [('inherited.fixture',base),('ownzero.fixture',zero)]:(out/name).write_text('\n'.join(lines)+'\n')
 files=[Path(__file__).resolve(),ROOT/'pipeline/replay_rvv_compute_asm_v1.py',parent,ROOT/'build/warm-OPU-TK124-frozen-c12a08f7-v1/manifest.json',ROOT/'build/rvv-compute-asm-v5/ready.json',ROOT/'build/rvv-compute-asm-v5/corpus.json',ROOT/'build/rvv-compute-asm-v5/cache-history.json',ROOT/'calibration/rvv-compute1320-v1/split.json',ROOT/'calibration/rvv-identify-compact-v1/fit-plan.json',ROOT/'build/rvv-compute-asm-v5-independent-audit-v1/report.json']
 proof=dict(schema='iris.rvv_compute_asm_C12_zero_adjustment.v1',**{'pass':True},PRIMARY_native_source_choice='FrozenC12TK124ON chosenfromsourceVMEcontrollergeometry, notnewlabelsmodecomparison',native_binary_sha256='c12a08f77ad429c5ffbbbb48c92c3953a3b26564ab1defe9dc0f2b1fd38033d7',UART_sha256='e02f1a319e7bee44aab5b8440e24a51db10172bfe5a9f69fa09902757773f639',eligible_harts=[0,1],eligible_families=FAMILIES,exact_eligible_rule_changes=changes,eligible_rule_lines=14,setup_work_slots_set_zero=28,only_other_difference='experimental_profile identity',all_CPU_cache_hart2_controller_resources_intervals_OPU_MM_modes_preserved=True,hardware_timing_labels_consumed=False,fit_performed=False,new_exact_ELF_and_history=True,input_sha256={str(p):sha(p)for p in files},artifact_sha256={n:sha(out/n)for n in('inherited.fixture','ownzero.fixture')})
 (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 plan=dict(schema='iris.rvv_compute_asm_C12_frozen_fit_plan.v1',frozen_before_new_hardware_labels_consumed=True,hardware_timing_labels_consumed=False,fit_authorized=False,native='C12TK124 source-driven primary ONLY; no modegrid/selection',eligible_harts=[0,1],shared_coreclass=True,eligible_families=FAMILIES,parameters=13,rowmove_WORK_fixed_zero=True,TRAIN_rows_required=978,reserved_rows_root_only=342,all_TRAIN_rows_and_repetitions_retained=True,MM_zero_feature_control_rows_retained=True,baseline='Own completed exact44c983ELF/C12 eligible-zero replay; useactualtotalmcycleandownactualprefixcounts, never subtract oldcosts posthoc',columns=[dict(family=f,basis=k)for f in FAMILIES for k in(['instructions']if f=='vme.row_move'else['instructions','work'])],estimator='One deterministic joint nonnegative relativeleast-squares on totalbegin-to-drain cycles, targetHWminus actualownzero; coordinate descenttolerance1e-12/max10000iterations; require fullrank13; no intercept,negativecost,PC/case/triallookup,rowfilter ormodegrid',nonlinear_validation='Freeze coefficients, emitownfixture, actualsameELF replay; reportall978TRAINandallnumeric/CSRjoins; rootonly342reservedunusedforfit/selection',phase_policy='Fit totalonly; separatelyreportissue/drain from3actualmcycleendpoints. No inventedphaseinstret or doubledoverlappingwindowweights.',unchanged='MM/VMEcontrollerlatencies/resources/II/CPU/cache/hart2/IRQ/sourceclocks/functionalvalues',cache_history='Selectedbodypreexecutedonce thenfulloperand/tile/poisonreset+fence; notphysicalhitguarantee. All3trials retained; noUARTbetweenharts; newexactprogramreference.',structural_floor='WholeVRFowner/chaining/CPU→unitCOMplus1/sourcebusy/FENCE and vectormemory phases mayremaininfeasible; reportnegative residuals/zero-basis/higherror, no penaltyhiding',source_actor_change_policy='Anyfutureingress/per-EG/CPU-fix epoch needsownfreshpredictor/zero baseline; no transfer tothisone',ELF_sha256='44c983d8495fb274a260b5d9b376d05458ff94d7365153b71cefb607fd624aaa',native_manifest_sha256=sha(ROOT/'build/warm-OPU-TK124-frozen-c12a08f7-v1/manifest.json'),frozen_split_sha256=sha(ROOT/'calibration/rvv-compute1320-v1/split.json'),parent_estimator_plan_sha256=sha(ROOT/'calibration/rvv-identify-compact-v1/fit-plan.json'),zero_mapping_proof_sha256=sha(out/'proof.json'))
 (out/'fit-plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps(dict(fixtures=proof['artifact_sha256'],proof_sha256=sha(out/'proof.json'),plan_sha256=sha(out/'fit-plan.json'))))
if __name__=='__main__':main()
