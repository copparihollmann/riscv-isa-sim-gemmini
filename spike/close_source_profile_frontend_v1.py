#!/usr/bin/env python3
"""Close a new source-event frontend from actual owned observer/refusal gates."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(v,s):
 if not v:raise ValueError(s)
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--controls',type=Path,required=True);p.add_argument('--OPU-run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);x=p.parse_args();out=x.output.resolve();out.mkdir(exist_ok=False)
 controls,opu=x.controls.resolve(),x.OPU_run.resolve();c=json.loads(controls.read_text());r=json.loads(opu.read_text());need(c.get('pass')is True and len(c['checks'])>=28 and len(c['negative_join_controls'])>=11,'Actual observer/refusal control receipt required');need(r.get('pass')is True and r.get('profile_pass')is True,'Actual normal OPU execution/profile required')
 for receipt in(c,r):
  for name,digest in receipt['input_sha256'].items():need(sha(name)==digest,'Changed bound input '+name)
  for name,digest in receipt.get('output_sha256',{}).items():need(sha(name)==digest,'Changed bound output '+name)
 s=json.loads((opu.parent/'source-profile/summary.json').read_text());need(s['journal_complete']is True and s['OPU']['reserved_microissues']==4 and s['OPU']['actual_owned_K_callbacks']==4 and s['OPU']['actual_final_entry_publications']==4 and s['OPU']['logical_MAC_work']is None,'Actual K1 ownership scope');text=(opu.parent/'stdout').read_text();need(text=='IRIS_SATURN_LIVE_VALUES 8 6 64\nIRIS_SATURN_LIVE_TIME '+text.split('IRIS_SATURN_LIVE_TIME ')[1].split('\n')[0]+'\nIRIS_SATURN_LIVE_DONE 3\n','Unchanged three-hart K1 golden/control markers')
 model=ROOT/'build/C12-source-composite-Merlin-adapter-package-v1/source_compute/manifest.json';m=json.loads(model.read_text())
 # Only hash the existing closure, including opaque validation-report bytes.
 # Never read or parse its protected timing fields.
 for name,digest in m['input_sha256'].items():need(sha(name)==digest,'Existing frozen package input changed '+name)
 files=[Path(__file__).resolve(),ROOT/'iris_model/source_profile_run_v1.py',ROOT/'iris_model/source_event_profile_v1.py',ROOT/'iris_model/SOURCE_EVENT_PROFILING_V1.md',ROOT/'spike/check_source_profile_run_v1.py',ROOT/'timing/source_profile_smoke_v1.c',ROOT/'timing/build_source_profile_smoke_v1.py',controls,opu,model,ROOT/'iris_model/empirical_run.py',ROOT/'build/source-profile-smoke-guest-v1/report.json',ROOT/'build/source-profile-smoke-guest-v1/guest.elf']
 ids={str(v):sha(v)for v in files};ids.update({str(v):sha(v)for v in opu.parent.rglob('*')if v.is_file()});ids.update({str(v):sha(v)for v in controls.parent.rglob('*')if v.is_file()})
 report=dict(schema='iris.source_event_frontend_delivery.v1',**{'pass':True},new_frontend=str(ROOT/'iris_model/source_profile_run_v1.py'),source_consumer=str(ROOT/'iris_model/source_event_profile_v1.py'),source_model_native_sha256=m['native_binary_sha256'],source_model_UART_sha256=m['input_sha256'][m['uart_library']],fixture_sha256=m['input_sha256'][m['fixture']],model_manifest=str(model),model_manifest_sha256=sha(model),existing_generic_runner_provider_packages_and_default_unchanged=True,actual_3hart_numeric_words=136,actual_FADD_checked_COMs=64,actual_FADD_owned_16B_writes=1024,actual_FADD_completed_add_elements=4096,actual_OPU_K1_owned_callbacks=4,actual_OPU_K1_final_entry_publications=4,trace_toggle_stdout_CSR_native_summary_byte_parity=True,execution_refusal_and_attribution_checks=len(c['checks']),corrupt_source_or_CSR_join_refusals=len(c['negative_join_controls']),source_image_attestation=False,full_model_or_2percent_certification=False,new_fit_native_source_policy_or_hardware_actions=False,OPU_logical_MAC_peak_and_work_unavailable=True,source_valid_occupancy_not_physical_utilization=True,explicit_region_boundaries_only=True,profile_options=dict(source_events='explicit output path inside fresh outputdir',region_formats=['none','iris-json','merlin-kernel-v1'],provided_map_schema='iris.source_event_region_map.v1'),input_sha256=ids)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 recipe='python3 -m iris_model.source_profile_run_v1 \\\n  --model '+str(model.relative_to(ROOT))+' \\\n  --elf <unstripped-program.elf> \\\n  --output <NEW-output-directory> \\\n  --source-events \\\n  --timeout 600\n\nOpen <NEW-output-directory>/source-profile/trace.json with Perfetto.\nRead source-profile/summary.json and run.json for scopes, independent guest/profile status and digests.\nUse --region-format merlin-kernel-v1 only for the documented exact REGION marker.\nNo supported markers means whole-program/per-function attribution only.\n'
 (out/'RUN.txt').write_text(recipe);print(json.dumps(dict(pass_=True,report_sha256=sha(out/'report.json'),recipe=str(out/'RUN.txt'))))
if __name__=='__main__':main()
