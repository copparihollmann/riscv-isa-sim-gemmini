#!/usr/bin/env python3
"""Freeze the reviewed117cohort/234pass fitting batch; no hardware actions."""
import argparse,json,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from pow2_matrix_review import validator,inspect,flatten,ELF
from check_pow2_matrix_clint import inspect_clint_window
from batch_runner import digest,prepare,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='pow2_single_matrix_train_reserved_v1';WATCHDOG=600;PHASE_TIMEOUT=780
def merge(target,other):
 for name,wanted in other.items():
  p=Path(name);key=str((p if p.is_absolute()else ROOT/p).resolve())
  if key in target and target[key]!=wanted:raise ValueError('Conflicting sourceidentity '+key)
  target[key]=wanted

def admit(build,ready_sha):
 b=Path(build).resolve();ready=json.loads((b/'ready.json').read_text());built=json.loads((b/'build.json').read_text());q=json.loads((b/'qualification.json').read_text());corpus=json.loads((b/'corpus.json').read_text());elf=b/'matrix.elf'
 if digest(b/'ready.json')!=ready_sha or ready.get('schema')!='iris.pow2_single_matrix_ready.v1'or ready.get('status')!='ready_for_root_managed_preparation'or ready.get('source_frozen')is not True or ready.get('reserved_timing_labels_root_only')is not True or ready.get('new_exact_reference_required')is not True:raise ValueError('Exact frozen matrix packet')
 for name,want in ready['artifact_sha256'].items():
  if digest(b/name)!=want:raise ValueError('Bound artifactchanged '+name)
 if set(ready['artifact_sha256'])!={'matrix.elf','corpus.json','build.json','golden-words.bin','qualification.json','host-cases.json'}or digest(elf)!=ELF or built['negative_skip_kernel']is not False or built['status']!='passed'or q['status']!='passed'or q['ELF_sha256']!=ELF:raise ValueError('Complete positive matrix source/ELF')
 if len(q['negative_controls'])!=25 or any(x.get('rejected')is not True for x in q['negative_controls'])or q['actual_omission']['failed_regions']!=132:raise ValueError('Actual omission and25 mutations')
 if inspect(elf.read_bytes(),corpus,(b/'golden-words.bin').read_bytes())!=q['compiled_proof']:raise ValueError('Independent compiled/golden proof')
 split=ROOT/'calibration/pow2-matrix-v1/split.json'
 if digest(split)!=corpus['frozen_split_sha256']or ready['regions']!=132 or ready['train_regions']!=96 or ready['reserved_regions']!=36:raise ValueError('Frozen grouped split')
 inspect_clint_window(elf.read_bytes());cases=flatten(corpus)
 if cases!=json.loads((b/'host-cases.json').read_text()):raise ValueError('Actual canonical hostcases')
 validate_cases(cases,True);ids={str(b/n):digest(b/n)for n in['ready.json','build.json','qualification.json','corpus.json','golden-words.bin','host-cases.json','matrix.elf']}
 merge(ids,built['input_sha256']);merge(ids,q['input_sha256'])
 if {x['seed']for x in q['functional']}!={0,17}or len(q['functional'])!=2:raise ValueError('Both seeded runs')
 for row in q['functional']:
  p=Path(row['report']);r=json.loads(p.read_text())
  if digest(p)!=row['report_sha256']or r['pass']is not True or r['exit_status']!=0 or r['timed_out']is not False or r['normal_guest_exit_verified']is not True or r['elf_sha256']!=ELF or '-p3'not in r['argv']or '--iris-schedule-seed='+str(row['seed'])not in r['argv']:raise ValueError('Actual normal359 seeded execution')
  if digest(p.parent/'stdout')!=r['stdout_sha256']or digest(p.parent/'stderr')!=r['stderr_sha256']:raise ValueError('Changedrawlogs')
  validator().validate((p.parent/'stdout').read_text(),corpus);merge(ids,r['input_sha256'])
 neg=Path(q['actual_omission']['report']);n=json.loads(neg.read_text())
 if digest(neg)!=q['actual_omission']['report_sha256']or n['pass']is not True or n['expect_negative']is not True or n['exit_status']==0 or n['timed_out']is not False:raise ValueError('Actual omitted kernel nonzero')
 for name,want in ids.items():
  if digest(name)!=want:raise ValueError('Source changed '+name)
 return ready,corpus,cases,elf,ids

def freeze(a):
 import yaml
 b=a.build.resolve();out=a.output.resolve();authorization=a.authorization_receipt.resolve();ready,corpus,cases,elf,ids=admit(b,a.expected_ready_sha256)
 if a.validate_only:return dict(status='localadmissionpassed',cohorts=132,declared_cases=132,regions=132,hardware_contacted=False)
 grant=json.loads(authorization.read_text())
 if grant.get('schema')!='iris.remote_user_launch_authorization_receipt.v1':raise ValueError('Actualstandinguserreceipt')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');d=fs/'deploy';manager,m=prepare(d,out,elf,cases,d/'config_runtime.yaml',d/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),out,m);add_observer(manager);watch=manager/'iris_workload_watchdog.py';text=watch.read_text()
 if text.count('SECONDS=1500')!=1:raise ValueError('Reviewedwatchdogchanged')
 watch.write_text(text.replace('SECONDS=1500','SECONDS=600',1));runtime=manager/'config_runtime.yaml';r=yaml.safe_load(runtime.read_text());old=r['target_config'].get('plusarg_passthrough','')
 if '+fesvr-step-size'in old or '+max-cycles'in old:raise ValueError('Conflictingloader/unsafe targetbound')
 r['target_config']['plusarg_passthrough']=(old+' +fesvr-step-size=128').strip();runtime.write_text(yaml.safe_dump(r,sort_keys=False))
 for name in['ready.json','build.json','qualification.json','corpus.json','golden-words.bin']:(out/name).write_bytes((b/name).read_bytes())
 (out/'CLINT-assembly-proof.json').write_text(json.dumps(inspect_clint_window(elf.read_bytes()),indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'launch-authorization.json').write_bytes(authorization.read_bytes());check=dict(schema='iris.pow2_matrix_capture_checklist.v1',frozen_before_launch=True,regions=132,trials=3,all3harts_boot=True,active_compute_harts=[0,1],hart2_VME_refusal_required=True,dtypes=['signed-int8-to-int32','E4M3-E4M3-to-FP32'],source_tile_edge=32,TK=1,all_words_checked=1109760,poisoned_destination=True,console_between_cases_only=True,reserved_timing_labels_root_only=True,reserved_shapes=[[16,16,16],[128,128,128],[32,32,64]],train_regions=96,reserved_regions=36,no_hardware_cold_or_miss_claim=True,source_image_association_verified=False,source_core_cycles_per_mtime_tick=1000,mtime_hz=500000,quantization_error_bound_core_cycles=1000,overhead_subtracted=False,wall_watchdog_seconds=WATCHDOG,phase_timeout_seconds=PHASE_TIMEOUT,target_max_cycles=None,target_bound_omission_reason='Successfulloaderexceeded5billioncycles; originaldriveratoi32. Useownedwallwatchdog.',unavailable_instrumentation=['TracerV','AutoCounter','SynthPrint'],calibration_usable=False)
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n');launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])];(out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[ROOT/'calibration/pow2-matrix-v1/split.json',Path(__file__).resolve(),ROOT/'firesim/analyze_pow2_matrix.py',ROOT/'firesim/pow2_matrix_review.py',ROOT/'firesim/check_pow2_matrix_clint.py',ROOT/'benchmarks/pow2_matrix_v1/validate.py',ROOT/'benchmarks/pow2_matrix_v1/build.py',ROOT/'benchmarks/pow2_matrix_v1/guest.c',ROOT/'benchmarks/pow2_matrix_v1/run.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',authorization,ROOT/'build/xilinx-tool-paths-v1.json',*env,Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')];merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256']);m.update(reserved_timing_labels_root_only=True,train_regions=96,reserved_regions=36,frozen_split_sha256=corpus['frozen_split_sha256'],require_regions=True,require_goldens=True,campaign_role=ROLE,fitting_only=True,global_heldout=False,new_exact_reference_required=True,old_campaign_timings_applicable=False,cohorts=132,expected_regions=132,launch_authorization_receipt=grant,corpus_sha256=digest(out/'corpus.json'),reviewed_ready_sha256=digest(out/'ready.json'),timing_perturbed=True,calibration_usable=False,physical_hit_or_miss_measured=False,hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=out)};save_manifest(out,m);verify(out);return dict(status=m['status'],cohorts=132,declared_cases=132,regions=132,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
