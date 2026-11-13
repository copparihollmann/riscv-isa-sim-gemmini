#!/usr/bin/env python3
"""Close the exact optional35a dual-profile runtime and real Merlin gates."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike import empirical_provider_source_VADD35a_v1 as P
from benchmarks.validate_console import validate

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();pkg,out=a.package.resolve(),a.output.resolve();out.mkdir(exist_ok=False)
 sources=[Path(__file__).resolve(),Path(P.__file__).resolve(),ROOT/'spike/package_source_VADD35a_v1.py',ROOT/'spike/run_source_VADD35a_v1.py',ROOT/'spike/check_source_VADD35a_package_v1.py',ROOT/'spike/check_source_VADD35a_Merlin_v1.py',ROOT/'timing/empirical_time_guest_VADD35a_v1.c',ROOT/'timing/build_empirical_time_guest_VADD35a_v1.py',ROOT/'benchmarks/validate_console.py',ROOT/'benchmarks/calibration-corpus.json',ROOT/'iris_model/empirical_run.py',*P.HOST_CONTRACTS]
 ids={str(p):P.sha(p)for p in sources};profiles={}
 for name in P.PROFILES:
  mpath=pkg/name/'manifest.json';m=P.document(mpath);d=P.verify(mpath);P.need(d['available']is True and d['isa_extensions']==P.EXTENSIONS,'Both exact profiles actually available')
  P.need(all(d['qualification']is False for d in[m['qualification']]for _ in[])if False else all(v is False for v in m['qualification'].values()),'No qualification escalation')
  profiles[name]=dict(manifest=str(mpath),sha256=P.sha(mpath),native_sha256=d['native_binary_sha256'],fixture_sha256=P.PROFILES[name]['fixture_sha256'],functional_scope=d['functional_scope']);ids.update(m['input_sha256']);ids[str(mpath)]=P.sha(mpath)
  for f in(pkg/name/'verification.json',):ids[str(f)]=P.sha(f)
 for name in('C12-source-VADD35a-descriptor-controls-v1','C12-source-VADD35a-real-Merlin-gates-v1'):
  p=ROOT/'build'/name/'report.json';r=P.document(p);P.need(r.get('pass')is True,'New own package/API controls must pass');ids[str(p)]=P.sha(p)
  for f,h in r['input_sha256'].items():P.need(P.sha(f)==h,'Changed own test input '+f);ids[f]=h
  if 'positive_actual_runs'in r:
   P.need(len(r['positive_actual_runs'])==2 and len(r['refusals'])==12,'Actual two-profile Merlin routes/affinity gates')
   for run in r['positive_actual_runs']:
    P.need(run['normal_exit']and run['independent_words']==24 and run['all3harts'],'Actual realAPI three-hart words')
    for f,h in run['input_sha256'].items():P.need(P.sha(f)==h,'Changed API runtime input');ids[f]=h
    for f,h in run['output_sha256'].items():P.need(P.sha(f)==h,'Changed API raw output');ids[f]=h
  else:P.need(r['refusals']==54,'54own descriptor mutations/refusals')
 golden=P.document(ROOT/'benchmarks/calibration-corpus.json');normal=[]
 for name in('C12-source-VADD35a-generic-compute-smoke-v1','C12-source-VADD35a-profile-OS-smoke-v1'):
  b=ROOT/'build'/name;r=P.document(b/'run.json');P.need(r.get('pass')is True and r.get('exit_status')==0 and r.get('timed_out')is False and r.get('unchanged_inputs_after_execution')is True,'Actual generic/profile normal exit')
  proof=validate((b/'stdout').read_text(),golden,3,True);P.need(proof['regions']==12,'Every actual scalar smoke ROI')
  for f,h in r['input_sha256'].items():P.need(P.sha(f)==h,'Changed generic runtime input');ids[f]=h
  for f,h in r['output_sha256'].items():P.need(P.sha(f)==h,'Changed generic raw output');ids[f]=h
  ids[str(b/'run.json')]=P.sha(b/'run.json');normal.append(dict(run=str(b/'run.json'),normal_exit=True,independent_validation=proof))
 source_profiler=ROOT/'build/source-event-profile-v2-delivery-v1/manifest.json';ids[str(source_profiler)]=P.sha(source_profiler)
 root=P.document(P.ROOT_QA[0]);P.need(root['pass']and root['profiles']['source_compute']['compiler8_exercises_finite_VADD']is False,'Compiler pass cannot qualify an unexecutedVADD')
 # Opaque binding only: do not parse the independent root timing validation.
 P.need(P.sha(root['validation_report']['path'])==root['validation_report']['sha256'],'Exact root validation bytes')
 report=dict(schema='iris.optional_source_VADD35a_runtime_delivery.v1',**{'pass':True},profiles=profiles,root_QA_closure=dict(path=str(P.ROOT_QA[0]),sha256=P.ROOT_QA[1]),opaque_validation_report=root['validation_report'],validation_bytes_only_hashed_not_parsed=True,source_capsule_manifest_sha256=P.CAPSULE_SHA,native_binary_sha256=P.NATIVE_SHA,uart_sha256=P.UART_SHA,own_fatal_launcher_controls_per_profile=7,own_descriptor_refusals=54,actual_Merlin_route_runs=2,actual_Merlin_affinity_selection_refusals=12,own_smoke_and_sensitivity_three_harts_each=True,generic_profile_actual_smokes=normal,compiler_functional_regression_eight_images=True,compiler_finite_VADD_commands=0,VADD_qualified_by_own_source_directed_and_full_ASM_closure=True,OS_source_VADD_OPU_specialFENCE_enabled=False,active_source_IRQ_and_unmodeled_contexts_refuse=True,new_model_source_fixture_or_numeric_parameter_changes=False,new_hardware_or_fit_actions=False,old_providers_packages_and_default_written=False,source_image_attested=False,full_model_or_2percent_certified=False,measured_physical_utilization_claim=False,source_profiler_delivery=dict(path=str(source_profiler),sha256=P.sha(source_profiler)),input_sha256=ids)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 run='''Optional exact35a source runtime. Existing defaults and02b4 packages are unchanged.

Compute profile (finite source VADD/FPHSD/OPU; unsupported geometry/newFPflags/activeIRQ refuse):
python3 spike/run_source_VADD35a_v1.py --package PACKAGE --profile source_compute --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_DIRECTORY --timeout 600

Separately tested Zephyr/context profile:
python3 spike/run_source_VADD35a_v1.py --package PACKAGE --profile source_os --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_DIRECTORY --timeout 600
SourceOS has newsourceVADD, OPU andspecializedFENCE OFF. It retains finite sourceFADD/retry/wake. Compute timing qualification does not transfer; active perEG context/preemption is unqualified.

Generic developer CLI:
python3 -m iris_model.empirical_run --model COMPUTE_MANIFEST --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_DIRECTORY --timeout 600

Source events / JSON / Perfetto (separate additive verified frontend):
python3 -m iris_model.source_profile_run_v2 --model COMPUTE_MANIFEST --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_PROFILE_DIRECTORY --timeout 600 --region-format none
Use --region-format merlin-kernel-v1 only for the actual documented REGION markers, or provide a map joined to actualCSRprefix endpoints. No guessed regions. Sourcevalid occupancy/architecturalbytes are not physical utilization/traffic.

Merlin OOT route:
export PYTHONPATH=MERLIN_SRC
export MERLIN_TARGET_PATH=TARGET_PATH
export MERLIN_IRIS_TIMING=empirical
export MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING=1
export MERLIN_IRIS_MODEL_MANIFEST=COMPUTE_MANIFEST
build/merlin-venv/bin/python - <<'PYCODE'
from merlin.runtime.backends.zephyr_model import MatrixRouting
from merlin.runtime.backends import device_simulator
route = MatrixRouting(support_target='iris', unit='saturn_vme', config='IrisConfig')
result = device_simulator.run(route, 'YOUR_UNSTRIPPED_RV64_ELF', harts=3,
    active_hart_ids=(0,1), isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',
    memory=(0x80000000,0x100000000), timeout=600)
print(result['stdout'].decode())
assert result['returncode'] == 0
PYCODE
Use active_hart_ids=(0,) for one matrix worker. Hart2 has ordinary RVV/control but no VME, and cannot be selected for matrix work. All3physical hartISA/memory/ROM/DTB choices remain fixed by the descriptor.

Verify either profile:
python3 spike/empirical_provider_source_VADD35a_v1.py --model COMPUTE_MANIFEST

This is an optional experimental finite source runtime, not a full±2%, source-image or physical-traffic certificate. Rootvalidation is byte-bound opaque evidence. Scalar/memory/otherunit costs remain inherited effective fits; no refit occurred here. The8compilerELFs execute272OPU and0finiteVADD commands; finiteVADD qualification comes from separate source/directeds/fullASM gates. Numerical exit alone never certifies arbitraryELF timing.
'''
 run=run.replace('COMPUTE_MANIFEST',str(pkg/'source_compute/manifest.json')).replace('PACKAGE',str(pkg)).replace('MERLIN_SRC',str(ROOT/'integration/merlin/src')).replace('TARGET_PATH',str(ROOT/'integration/iris-mlir'));(out/'RUN.txt').write_text(run)
 print(json.dumps(dict(pass_=True,report_sha256=P.sha(out/'report.json'),profiles={k:v['sha256']for k,v in profiles.items()},RUN=str(out/'RUN.txt'))))
if __name__=='__main__':main()
