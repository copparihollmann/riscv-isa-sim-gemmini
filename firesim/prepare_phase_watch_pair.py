#!/usr/bin/env python3
"""Prepare one member of the one-byte watchdog pair; never contact hardware."""
import argparse,json,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'));sys.path.insert(0,str(ROOT/'firesim'))
from heldout_phase_watch_pair_validate import validate
from heldout_phase_watch_pair_qualify import verify_pair
from batch_runner import digest,prepare,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='phase_watch_one_byte_control_v1'
WATCHDOG,PHASE_TIMEOUT=600,780
NO_TARGET_BOUND='No targetmax: originaldriveratoi32 and loadercanexceed5billion cycles; ownedwallwatchdog only.'
def merge(target,source):
 for name,d in source.items():
  p=Path(name);name=str((p if p.is_absolute()else ROOT/p).resolve())
  if name in target and target[name]!=d:raise ValueError('Conflicting input identity')
  target[name]=d
def admit(build,ready_sha,variant):
 b=Path(build).resolve();rp=b/'ready.json'
 if digest(rp)!=ready_sha:raise ValueError('Exact pair readyhash')
 ready=json.loads(rp.read_text());m=json.loads((b/'manifest.json').read_text());q=json.loads((b/'qualification.json').read_text());cases=json.loads((b/'cases.json').read_text());gold=json.loads((b/'golden.json').read_text());elf=Path(m['variants'][variant]['path'])
 if ready.get('schema')!='iris.phase_watch_one_byte_pair_ready.v1'or ready.get('status')!='ready_for_root_managed_preparation'or ready.get('source_frozen')is not True or ready.get('diagnostic_only')is not True or ready.get('fitting_allowed')is not False or ready.get('all4seeded_positives_pass')is not True or ready.get('both_forced_counterfactuals_pass')is not True or m['force_stall_negative']:raise ValueError('Positive paired diagnostic-only packet')
 for path,key in[(b/'manifest.json','manifest_sha256'),(b/'qualification.json','qualification_sha256'),(b/'pair-proof.json','pair_proof_sha256'),(b/'cases.json','cases_sha256'),(b/'golden.json','golden_sha256')]:
  if digest(path)!=ready[key]:raise ValueError('Readyartifact changed')
 if ready['variants']!=m['variants']or digest(elf)!=m['variants'][variant]['sha256']or not q['pass']or verify_pair(m)!=q['pair']or len(cases)!=32 or ready['phases']!=2 or ready['regions']!=32:raise ValueError('Exact one-byte/32ROI pair')
 if len(q['negative_controls'])!=4 or any(x['rejected']is not True for x in q['negative_controls'])or len(q['forced_counterfactuals'])!=2:raise ValueError('Allwatchpresence/forcedstall controls')
 if {(r['variant'],r['seed'])for r in q['functional']}!={(v,s)for v in['enabled','disabled']for s in[0,17]}:raise ValueError('All4actual359positives')
 ids={str(p):digest(p)for p in[rp,b/'manifest.json',b/'qualification.json',b/'pair-proof.json',b/'cases.json',b/'golden.json',elf]};merge(ids,m['input_sha256']);merge(ids,q['input_sha256'])
 for entry in q['functional']:
  p=Path(entry['report']);r=json.loads(p.read_text());d=p.parent;v=entry['variant']
  if digest(p)!=entry['report_sha256']or not r['pass']or r['timed_out']or r['exit_status']!=0 or r['ELF_sha256']!=m['variants'][v]['sha256']or not r['native_sha256'].startswith('35901887'):raise ValueError('Actualpaired359run identity')
  if digest(d/'stdout')!=r['stdout_sha256']or digest(d/'stderr')!=r['stderr_sha256']:raise ValueError('Rawpositiveoutputs changed')
  validate((d/'stdout').read_text(),dict(m,ELF_sha256=r['ELF_sha256']),cases,gold,v=='enabled');merge(ids,r['input_sha256'])
 validate_cases(cases,True)
 for path,digest_expected in ids.items():
  if digest(path)!=digest_expected:raise ValueError('Frozeninput changed '+path)
 corpus=dict(schema='iris.phase_watch_byte_pair_corpus.v1',manifest=dict(m,ELF_sha256=digest(elf)),cases=cases,goldens=gold,variant=variant,watchdog_enabled=variant=='enabled',diagnostic_only=True,fitting_allowed=False)
 return ready,corpus,cases,elf,ids
def freeze(a):
 import yaml
 build,output,authorization=a.build.resolve(),a.output.resolve(),a.authorization_receipt.resolve();ready,corpus,cases,elf,identities=admit(build,a.expected_ready_sha256,a.variant)
 if a.validate_only:return dict(status='local_admission_passed',regions=32,hardware_contacted=False)
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
 for name in ['ready.json','manifest.json','qualification.json','pair-proof.json','golden.json']:(output/name).write_bytes((build/name).read_bytes())
 (output/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n');(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(output/'launch-authorization.json').write_bytes(authorization.read_bytes());checklist=dict(schema='iris.phase_watch_byte_pair_capture_checklist.v1',frozen_before_launch=True,diagnostic_only=True,calibration_usable=False,expected_cases=32,expected_regions=32,embedded_int32_words=122880,embedded_W8A8_words=122880,trials=5,harts_online=[0,1,2],h2_role='Original RVV producer onhart2',watch_pair_variant=a.variant,watchdog_enabled=a.variant=='enabled',required=['Exact parent compiledobjects and sourceoverlay; two actual seeded positives plus actual forced-stall/watchdog HTIF1 control','Both phases, all32 compute/producer regions+30compact fullwordhash outputs; all diagnostic mailboxes and failure logs even on timeout','All four managed phase timings, complete ownership/lock checks, owned cleanup and quiescent external archive','Original driver/image identity, exact plusargs, runtime/HWDB/environment, available aggregate FASED CSV'],remote_wall_watchdog_seconds=WATCHDOG,host_phase_timeout_seconds=PHASE_TIMEOUT,target_cycle_bound=None,target_cycle_bound_omission_reason=NO_TARGET_BOUND,unavailable_instrumentation=['TracerV','AutoCounter','SynthPrint'],source_image_association_verified=False,timing_accuracy_qualified=False)
 (output/'capture-checklist.json').write_text(json.dumps(checklist,indent=2)+'\n');launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(output/'launch-environment.stdout'))+' 2> '+shlex.quote(str(output/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(output),'--execute','--authorization-id',receipt['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])];(output/'launch.sh').write_text('\n'.join(launch)+'\n');(output/'launch.sh').chmod(0o700)
 env_paths=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_phase_watch_pair.py',ROOT/'zephyr/heldout_phase_diagnostic_validate.py',ROOT/'zephyr/heldout_phase_diagnostic_run.py',ROOT/'zephyr/heldout_phase_watch_pair_build.py',ROOT/'zephyr/heldout_phase_watch_pair_run.py',ROOT/'zephyr/heldout_phase_watch_pair_validate.py',ROOT/'zephyr/heldout_phase_watch_pair_qualify.py',ROOT/'zephyr/compiler_pipeline.py',ROOT/'zephyr/freeze_heldouts.py',ROOT/'zephyr/uart_profiles.py',ROOT/'spike/run_functional.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',authorization,ROOT/'build/xilinx-tool-paths-v1.json',*env_paths,Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')];merge(identities,{str(p):digest(p)for p in sources});merge(manifest['input_sha256'],identities);snapshot_inputs(output,manifest['input_sha256']);manifest.update(require_regions=True,require_goldens=True,campaign_role=ROLE,launch_authorization_receipt=receipt,corpus_sha256=digest(output/'corpus.json'),timing_perturbed=True,baseline_timing_equivalent=False,calibration_usable=False,diagnostic_only=True,watch_pair_variant=a.variant,watchdog_enabled=a.variant=='enabled',hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime_path),frozen_capture_checklist_sha256=digest(output/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env_paths},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 manifest['prepared_file_sha256']={str(p.relative_to(output)):digest(p)for p in sorted(output.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=output)};save_manifest(output,manifest);verify(output);return dict(status=manifest['status'],regions=32,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--variant',choices=['enabled','disabled'],required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
