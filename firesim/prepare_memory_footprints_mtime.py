#!/usr/bin/env python3
"""Freeze the reviewed105cohort/210pass fitting batch; no hardware actions."""
import argparse,json,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from memory_footprints_mtime_review import validator,inspect,flatten,ELF,PARENT_READY
from check_memory_footprint_clint import inspect_clint_window
from batch_runner import digest,prepare,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='memory_footprint_global_time_fitting_v1';WATCHDOG=1200;PHASE_TIMEOUT=1380
def merge(target,other):
 for name,wanted in other.items():
  p=Path(name);key=str((p if p.is_absolute()else ROOT/p).resolve())
  if key in target and target[key]!=wanted:raise ValueError('Conflicting sourceidentity '+key)
  target[key]=wanted

def admit(build,ready_sha):
 b=Path(build).resolve();ready=json.loads((b/'ready.json').read_text());built=json.loads((b/'build.json').read_text());q=json.loads((b/'qualification.json').read_text());review=json.loads((b/'review.json').read_text());corpus=json.loads((b/'corpus.json').read_text());layout=json.loads((b/'layout.json').read_text());elf=b/'footprints.elf'
 if digest(b/'ready.json')!=ready_sha or ready.get('schema')!='iris.memory_footprint_mtime_reviewed_ready.v1'or ready.get('status')!='ready_for_root_managed_preparation'or ready.get('source_frozen')is not True or ready.get('fitting_only')is not True or ready.get('global_heldout')is not False or ready.get('new_exact_reference_required')is not True or ready.get('parent_ready_sha256')!=PARENT_READY:raise ValueError('Exact sourcefrozen reviewed fitting packet')
 for name,key in [('footprints.elf','elf_sha256'),('corpus.json','corpus_sha256'),('build.json','build_sha256'),('qualification.json','qualification_sha256'),('layout.json','layout_sha256'),('review.json','review_sha256'),('host-cases.json','host_cases_sha256')]:
  if digest(b/name)!=ready[key]:raise ValueError('Readyartifactchanged '+name)
 if digest(Path(ready['parent_ready_packet']))!=PARENT_READY or digest(elf)!=ELF or built.get('pass')is not True or built['negative_skip_kernel']is not False or built['elf_sha256']!=ELF or q['pass']is not True or q['elf_sha256']!=ELF or q['corpus_sha256']!=digest(b/'corpus.json')or review['pass']is not True or not review['no_source_or_ELF_recompile_or_change']:raise ValueError('Exact positiveparentELF/sourcequalification')
 if len(q['negative_controls'])!=25 or any(c['rejected']is not True for c in q['negative_controls'])or q['actual_omitted_kernel']['failed_regions']!=360 or q['permutation_bijections_checked']!=45 or q['permutation_indices_checked']!=758304:raise ValueError('Actual360omission/25controls/45bijections required')
 if len(review['corruption_controls'])!=8 or any(c['rejected']is not True for c in review['corruption_controls'])or inspect(elf.read_bytes(),corpus,layout)!=review['compiled_and_layout_proof']:raise ValueError('Actualcompiledtable/layout independentproof')
 if ready.get('record_bytes')!=80 or ready.get('CLINT_samples_outside_CSR_ROI')is not True or q.get('CLINT_windows_verified')!=360 or q.get('CLINT_equal_subtick_parser_control_passed')is not True:raise ValueError('Actual80B record/360CLINTwindows/equal-subtickcontrol')
 inspect_clint_window(elf.read_bytes())
 cases=flatten(corpus)
 if cases!=json.loads((b/'host-cases.json').read_text())or ready['required_cohorts']!=105 or ready['declared_cases']!=210 or ready['required_regions']!=360:raise ValueError('105cohorts*2passes=210declaredcase contract')
 validate_cases(cases,True);ids={str(b/name):digest(b/name)for name in['ready.json','parent-ready.json','build.json','qualification.json','corpus.json','layout.json','review.json','host-cases.json','footprints.elf']}
 for source in[built['input_sha256'],q['input_sha256'],review['input_sha256']]:merge(ids,source)
 if len(q['functional'])!=2 or {r['seed']for r in q['functional']}!={0,17}:raise ValueError('Bothactual359schedules')
 for row in q['functional']:
  p=Path(row['report']);r=json.loads(p.read_text());d=p.parent
  if digest(p)!=row['report_sha256']or r['pass']is not True or r['seed']!=row['seed']or r['exit_status']!=0 or r['timed_out']is not False or r['normal_guest_exit_verified']is not True or r['elf_sha256']!=ELF or '-p3'not in r['argv']or '--iris-schedule-seed='+str(row['seed'])not in r['argv']or any(x.startswith('--iris-timing-')for x in r['argv']):raise ValueError('ActualfunctionalELF/normalexit/seed identity')
  if digest(d/'stdout')!=r['stdout_sha256']or digest(d/'stderr')!=r['stderr_sha256']:raise ValueError('Seededrawoutputchanged')
  validator().validate((d/'stdout').read_text(),corpus);merge(ids,r['input_sha256']);merge(ids,{str(x):digest(x)for x in[p,d/'stdout',d/'stderr']})
 neg=Path(q['actual_omitted_kernel']['report']);n=json.loads(neg.read_text())
 if digest(neg)!=q['actual_omitted_kernel']['report_sha256']or n['pass']is not True or n['expect_negative']is not True or n['timed_out']is not False or type(n['exit_status'])is not int or n['exit_status']==0 or n['proof']!=dict(actual_omitted_kernel_detected=True,failed_regions=360):raise ValueError('Actualcompiledomissionmustfailall360ROIs')
 for name,wanted in ids.items():
  if digest(name)!=wanted:raise ValueError('Frozensourcechanged '+name)
 return ready,corpus,cases,elf,ids

def freeze(a):
 import yaml
 b=a.build.resolve();out=a.output.resolve();authorization=a.authorization_receipt.resolve();ready,corpus,cases,elf,ids=admit(b,a.expected_ready_sha256)
 if a.validate_only:return dict(status='localadmissionpassed',cohorts=105,declared_cases=210,regions=360,hardware_contacted=False)
 grant=json.loads(authorization.read_text())
 if grant.get('schema')!='iris.remote_user_launch_authorization_receipt.v1':raise ValueError('Actualstandinguserreceipt')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');d=fs/'deploy';manager,m=prepare(d,out,elf,cases,d/'config_runtime.yaml',d/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),out,m);add_observer(manager);watch=manager/'iris_workload_watchdog.py';text=watch.read_text()
 if text.count('SECONDS=1500')!=1:raise ValueError('Reviewedwatchdogchanged')
 watch.write_text(text.replace('SECONDS=1500','SECONDS=1200',1));runtime=manager/'config_runtime.yaml';r=yaml.safe_load(runtime.read_text());old=r['target_config'].get('plusarg_passthrough','')
 if '+fesvr-step-size'in old or '+max-cycles'in old:raise ValueError('Conflictingloader/unsafe targetbound')
 r['target_config']['plusarg_passthrough']=(old+' +fesvr-step-size=128').strip();runtime.write_text(yaml.safe_dump(r,sort_keys=False))
 for name in['ready.json','parent-ready.json','build.json','qualification.json','corpus.json','layout.json','review.json']:(out/name).write_bytes((b/name).read_bytes())
 (out/'CLINT-assembly-proof.json').write_text(json.dumps(inspect_clint_window(elf.read_bytes()),indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'launch-authorization.json').write_bytes(authorization.read_bytes());check=dict(schema='iris.memory_footprints_mtime_capture_checklist.v1',frozen_before_launch=True,fitting_only=True,global_heldout=False,new_exact_reference_required=True,cohorts=105,declared_cases=210,expected_regions=360,passes=2,trials=3,harts_online=[0,1,2],all7hartmasks=True,footprint_bytes=[2048,16384,131072,1048576,4194304],history='All3prepareoncepersize/trial, masks1..7, eachtwoorderedpasses; noflush; earlierpasses/masks affecthistory',requested_byte_scope='8perarchitecturalLD;64Baddresslinefootprint is geometry, NOTphysicaltraffic',physical_hit_or_miss_measured=False,record_bytes=80,CLINT_scope='encloses_CSR_ROI_with_sampling_overhead',mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,quantization_error_bound_core_cycles=1000,overhead_subtracted=False,global_accuracy_2percent_claimed=False,compiled_CLINT_sampling_order_verified=True,required=['All360typedrawcounter/checksum/size/loadcount/pass/trial/hartrecords and exactnormalcompletion','Actual105-entrycompiledtable/16Bloop/bufferlayout/source/ELF/goldens/twoseeds/realomission+corruptionproofs','Allfourmanagedphases/ownershipchecks/lock/ownedcleanup/quiescentarchive and availableFASEDaggregateCSV','Exactdriver/image/runtime/HWDB/plusargs/environment; nooldtimingtransfer orcachemissclaim'],wall_watchdog_seconds=WATCHDOG,phase_timeout_seconds=PHASE_TIMEOUT,target_max_cycles=None,target_bound_omission_reason='Successfulloaderexceeded5billioncycles; originaldriveratoi32. Useownedwallwatchdog.',unavailable_instrumentation=['TracerV','AutoCounter','SynthPrint'],source_image_association_verified=False,calibration_usable=False)
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n');launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])];(out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_memory_footprints_mtime.py',ROOT/'firesim/memory_footprints_mtime_review.py',ROOT/'firesim/check_memory_footprint_clint.py',ROOT/'benchmarks/memory_footprints_mtime_v5/validate.py',ROOT/'benchmarks/memory_footprints_mtime_v5/build.py',ROOT/'benchmarks/memory_footprints_mtime_v5/guest.c',ROOT/'benchmarks/memory_footprints_mtime_v5/run.py',ROOT/'benchmarks/memory_footprints_mtime_v5/qualify.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',authorization,ROOT/'build/xilinx-tool-paths-v1.json',*env,Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')];merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256']);m.update(require_regions=True,require_goldens=True,campaign_role=ROLE,fitting_only=True,global_heldout=False,new_exact_reference_required=True,old_campaign_timings_applicable=False,cohorts=105,expected_regions=360,launch_authorization_receipt=grant,corpus_sha256=digest(out/'corpus.json'),reviewed_ready_sha256=digest(out/'ready.json'),timing_perturbed=True,calibration_usable=False,physical_hit_or_miss_measured=False,hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=out)};save_manifest(out,m);verify(out);return dict(status=m['status'],cohorts=105,declared_cases=210,regions=360,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
