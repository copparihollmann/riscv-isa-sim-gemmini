#!/usr/bin/env python3
"""Prepare the protected source-shaped compiler batch; never launch hardware."""
import argparse,json,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workloads'))
from model_operator_batch_validate import validate
from model_operator_batch_build import text_sections
from batch_runner import digest,prepare,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='model_operator_protected_validation_v1'
WATCHDOG,PHASE_TIMEOUT=600,780
NO_TARGET_BOUND='No +max-cycles: successful hardware startup exceeded5billion global driver cycles and the original driver parses this option with32-bit atoi. Use the owned foreground wall watchdog.'
def merge(target,source):
 for name,d in source.items():
  p=Path(name);name=str((p if p.is_absolute()else ROOT/p).resolve())
  if name in target and target[name]!=d:raise ValueError('Conflicting input identity '+name)
  target[name]=d
def admit(build,ready_sha):
 build=Path(build).resolve();ready_path=build/'ready.json'
 if digest(ready_path)!=ready_sha:raise ValueError('Exact frozen ready hash required')
 ready=json.loads(ready_path.read_text());built=json.loads((build/'build.json').read_text());q=json.loads((build/'qualification.json').read_text());proof=json.loads((build/'binary-proof.json').read_text());corpus=json.loads((build/'corpus.json').read_text());elf=build/'batch.elf'
 if ready.get('schema')!='iris.model_operator_batch_ready.v1'or ready.get('status')!='ready_for_root_managed_preparation'or ready.get('source_frozen_for_preparation')is not True or ready.get('calibration_usable')is not False or ready.get('all_cases_validation_only')is not True or ready.get('TinyLlama_protected')is not True or ready.get('exact_Llama2_checkpoint_admitted')is not False:raise ValueError('Protected validation-only ready contract')
 if (ready['required_cases'],ready['required_regions'],ready['trials'],ready['full_int32_words'],ready['full_W8A8_words'])!=(48,120,3,3072,3072)or Path(ready['elf']).resolve()!=elf or Path(ready['corpus_path']).resolve()!=build/'corpus.json':raise ValueError('Exact finite batch geometry')
 for name,key in [('batch.elf','elf_sha256'),('corpus.json','corpus_sha256'),('build.json','build_sha256'),('binary-proof.json','binary_proof_sha256'),('qualification.json','qualification_sha256')]:
  if digest(build/name)!=ready[key]:raise ValueError('Ready artifact changed '+name)
 if built['deliberate_noop_negative']or built['elf_sha256']!=digest(elf)or q.get('pass')is not True or q['elf_sha256']!=digest(elf)or q['binary_proof_sha256']!=ready['binary_proof_sha256']or q['corpus_sha256']!=ready['corpus_sha256']or not proof['pass']or proof['elf_sha256']!=digest(elf)or proof['source_instruction_bytes_unchanged']is not True:raise ValueError('Exact positive build/body/qualification')
 if len(q['negative_controls'])!=9 or any(x.get('rejected')is not True for x in q['negative_controls']):raise ValueError('All nine numerical/body/actual-noop controls required')
 if not any(x.get('failed_compute_words')==3072 for x in q['negative_controls']):raise ValueError('Actual poisoned omitted-kernel counterfactual required')
 identities={str(build/name):digest(build/name)for name in ['ready.json','build.json','qualification.json','binary-proof.json','corpus.json','batch.elf']};merge(identities,built['input_sha256']);merge(identities,q['input_sha256'])
 for g in proof['actual_MLIR_object_export_renames']:
  if g['kind']not in('model','bridge'):continue
  if digest(g['source'])!=g['source_sha256']or digest(g['renamed'])!=g['renamed_sha256']or text_sections(g['source'])!=text_sections(g['renamed']):raise ValueError('Actual compiled MLIR instruction body changed')
 functional=q['functional']
 if len(functional)!=2 or {x['seed']for x in functional}!={0,17}:raise ValueError('Both fresh actual359 schedules required')
 for entry in functional:
  report=Path(entry['report']);r=json.loads(report.read_text());directory=report.parent
  if digest(report)!=entry['report_sha256']or not r['pass']or r['returncode']!=0 or r['timed_out']or r['elf_sha256']!=digest(elf)or not r['native_sha256'].startswith('35901887')or '-p3'not in r['argv']or '--iris-schedule-seed='+str(entry['seed'])not in r['argv']:raise ValueError('Seeded actual ELF run identity')
  if digest(directory/'stdout')!=r['stdout_sha256']or digest(directory/'stderr')!=r['stderr_sha256']:raise ValueError('Seeded raw outputs changed')
  validate((directory/'stdout').read_text(),corpus);merge(identities,r['input_sha256']);merge(identities,{str(p):digest(p)for p in[report,directory/'stdout',directory/'stderr']})
 cases=[]
 for c in corpus['cases']:
  if c['validation_only']is not True or c['calibration_usable']is not False or c['active_harts']!=list(range(c['workers']))+[2]:raise ValueError('Protected case/hart scope')
  cases.append(dict(id=c['case_id'],active_harts=c['active_harts'],expected_checksums_by_hart=[c['expected_checksums'].get(str(h),0)for h in range(3)],parent_case_id=c['semantic_parent_case_id'],trial_id=c['trial_id'],suite='model_operator_validation',corpus_split=corpus['split_id']))
 validate_cases(cases,True)
 if len(cases)!=48 or sum(len(c['active_harts'])for c in cases)!=120:raise ValueError('Complete batch coverage')
 for name,d in identities.items():
  if digest(name)!=d:raise ValueError('Bound source changed '+name)
 return ready,corpus,cases,elf,identities
def freeze(a):
 import yaml
 build,output,authorization=a.build.resolve(),a.output.resolve(),a.authorization_receipt.resolve();ready,corpus,cases,elf,identities=admit(build,a.expected_ready_sha256)
 if a.validate_only:return dict(status='local_admission_passed',regions=120,hardware_contacted=False)
 receipt=json.loads(authorization.read_text())
 if receipt.get('schema')!='iris.remote_user_launch_authorization_receipt.v1':raise ValueError('Real standing-user authorization receipt required')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');deploy=fs/'deploy';manager,manifest=prepare(deploy,output,elf,cases,deploy/'config_runtime.yaml',deploy/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),output,manifest);add_observer(manager)
 watchdog=manager/'iris_workload_watchdog.py';text=watchdog.read_text()
 if text.count('SECONDS=1500')!=1:raise ValueError('Reviewed watchdog changed')
 watchdog.write_text(text.replace('SECONDS=1500','SECONDS='+str(WATCHDOG),1));runtime_path=manager/'config_runtime.yaml';runtime=yaml.safe_load(runtime_path.read_text());original=runtime['target_config'].get('plusarg_passthrough','')
 if '+fesvr-step-size'in original or '+max-cycles'in original:raise ValueError('Conflicting loader or unsafe target bound')
 runtime['target_config']['plusarg_passthrough']=(original+' +fesvr-step-size=128').strip();runtime_path.write_text(yaml.safe_dump(runtime,sort_keys=False))
 for name in ['ready.json','build.json','qualification.json','binary-proof.json','corpus.json']:(output/name).write_bytes((build/name).read_bytes())
 (output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(output/'launch-authorization.json').write_bytes(authorization.read_bytes());checklist=dict(schema='iris.model_operator_capture_checklist.v1',frozen_before_launch=True,validation_only=True,TinyLlama_protected=True,calibration_usable=False,expected_cases=48,expected_regions=120,full_int32_words=3072,full_W8A8_words=3072,trials=3,harts_online=[0,1,2],h2_role=ready['h2_role'],required=['All actual emitted MLIR object/kernel/body guards, seeded functional and negative evidence','Every raw full int32/W8A8 word and all120 compute/producer counter+checksum+failed-word records','All four managed phase timings, complete ownership/lock checks, owned cleanup and quiescent external archive','Original driver/image identity, exact plusargs, runtime/HWDB/environment, available aggregate FASED CSV'],remote_wall_watchdog_seconds=WATCHDOG,host_phase_timeout_seconds=PHASE_TIMEOUT,target_cycle_bound=None,target_cycle_bound_omission_reason=NO_TARGET_BOUND,unavailable_instrumentation=['TracerV','AutoCounter','SynthPrint'],source_image_association_verified=False,timing_accuracy_qualified=False)
 (output/'capture-checklist.json').write_text(json.dumps(checklist,indent=2)+'\n');launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(output/'launch-environment.stdout'))+' 2> '+shlex.quote(str(output/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(output),'--execute','--authorization-id',receipt['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])];(output/'launch.sh').write_text('\n'.join(launch)+'\n');(output/'launch.sh').chmod(0o700)
 env_paths=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_model_operator_batch.py',ROOT/'workloads/model_operator_batch_validate.py',ROOT/'workloads/model_operator_batch_build.py',ROOT/'workloads/check_operator_execution.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',authorization,ROOT/'build/xilinx-tool-paths-v1.json',*env_paths,Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')];merge(identities,{str(p):digest(p)for p in sources});merge(manifest['input_sha256'],identities);snapshot_inputs(output,manifest['input_sha256']);manifest.update(require_regions=True,require_goldens=True,campaign_role=ROLE,launch_authorization_receipt=receipt,corpus_sha256=digest(output/'corpus.json'),timing_perturbed=True,baseline_timing_equivalent=False,calibration_usable=False,validation_only=True,TinyLlama_protected=True,hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime_path),frozen_capture_checklist_sha256=digest(output/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env_paths},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 manifest['prepared_file_sha256']={str(p.relative_to(output)):digest(p)for p in sorted(output.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=output)};save_manifest(output,manifest);verify(output);return dict(status=manifest['status'],regions=120,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
