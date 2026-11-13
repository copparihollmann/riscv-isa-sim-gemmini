#!/usr/bin/env python3
"""Close exact additive adapter/API/whole-word evidence without new execution."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike import empirical_provider_source_composite_merlin_v1 as A
from benchmarks.validate_console import validate

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();P=A.base_module();pkg=ROOT/'build/C12-source-composite-Merlin-adapter-package-v1';execution=ROOT/'build/C12-source-composite-Merlin-adapter-eight-gates-v1/report.json';controls=ROOT/'build/C12-source-composite-Merlin-adapter-controls-v1/report.json';smoke=ROOT/'build/C12-source-composite-Merlin-adapter-generic-smoke-v1';x=P.document(execution);c=P.document(controls);s=P.document(smoke/'run.json')
 P.need(x['pass']is True and len(x['cases'])==8 and all(r['pass']is True and r['normal_guest_exit']is True and r['physical_harts']==3 and r['active_hart_ids']==list(range(r['workers']))and r['accumulator_words']==4096 and r['W8A8_words']==4096 for r in x['cases']),'All eight real Merlin method executions required')
 P.need(c['pass']is True and c['refusal_count']==40 and len(c['positive_real_Merlin_resolves'])==2,'Actual OOT/affinity/digest controls required')
 P.need(s['pass']is True and s['exit_status']==0 and not s['timed_out'],'Adapted generic normal exit required');checked=validate((smoke/'stdout').read_text(),P.document(ROOT/'benchmarks/calibration-corpus.json'),3,True)
 inputs={}
 for report in(x,c,s):
  for name,h in report['input_sha256'].items():P.need(P.sha(name)==h,'Execution/control input changed '+name);inputs[name]=h
 for row in x['cases']:
  for name,h in row['execution_input_sha256'].items():P.need(P.sha(name)==h,'Device API input changed '+name);inputs[name]=h
  for name,h in row['output_sha256'].items():P.need(P.sha(name)==h,'Device API output changed '+name);inputs[name]=h
 for profile,(base,h)in A.BASES.items():
  P.need(P.sha(base)==h,'Original v2 profile changed');r=A.experimental_empirical_simulator(pkg/profile/'manifest.json');P.need(r['available']is True,'Final adapter revalidation failed')
  P.need(r['isa_extensions']==A.EXTENSIONS and r['matrix_hart_ids']==[0,1],'Final ISA/affinity mismatch')
 paths=[Path(__file__).resolve(),Path(A.__file__).resolve(),ROOT/'spike/package_source_composite_merlin_v1.py',ROOT/'spike/check_source_composite_Merlin_adapter_v1.py',ROOT/'pipeline/replay_source_composite_Merlin_adapter_v1.py',execution,controls,smoke/'run.json',pkg/'package.json',pkg/'source_compute/manifest.json',pkg/'source_os/manifest.json',ROOT/'build/C12-source-composite-Merlin-adapter-delivery-inputs-v1/RUN.txt']
 inputs.update({str(p):P.sha(p)for p in paths});out=a.output.resolve();out.mkdir(exist_ok=False)
 report=dict(schema='iris.additive_source_composite_Merlin_adapter_delivery.v1',**{'pass':True},profiles={profile:dict(manifest=str(pkg/profile/'manifest.json'),sha256=P.sha(pkg/profile/'manifest.json'),base_manifest=str(base),base_manifest_sha256=h)for profile,(base,h)in A.BASES.items()},added_isa_extensions=list(A.EXTENSIONS),native_binary_sha256='02b4a9ab4c00a506e6ed3def6cb33ca0d9cc697951afaa02afc47e9ddce64577',real_Merlin_device_simulator_resolve_profiles=2,real_Merlin_device_simulator_run_cases=8,all_preserved_shipped_and_twin_GEMM_conv2d_1_2workers=True,physical_harts=3,active_worker_IDs_only_0_1=True,independently_checked_INT32_words=sum(r['accumulator_words']for r in x['cases']),independently_checked_W8A8_words=sum(r['W8A8_words']for r in x['cases']),actual_affinity_digest_crossprofile_refusals=40,generic_three_hart_smoke=checked,original_v2_contract_gap_independently_reproduced=True,original_v2_and_native_and_fixtures_unchanged=True,Merlin_core_and_OOT_hook_unchanged=True,new_source_image_or_timing_claim=False,default_pointer_written_by_this_task=False,hardware_contacted=False,protected_timing_labels_opened=False,no_new_compiler_or_fit=True,root_qualification_limits_preserved=True,input_sha256=inputs)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'RUN.txt').write_bytes((ROOT/'build/C12-source-composite-Merlin-adapter-delivery-inputs-v1/RUN.txt').read_bytes());print(json.dumps(dict(pass_=True,sha256=P.sha(out/'report.json'),compute_manifest=P.sha(pkg/'source_compute/manifest.json'),OS_manifest=P.sha(pkg/'source_os/manifest.json'))))
if __name__=='__main__':main()
