#!/usr/bin/env python3
"""Prepare only; root alone may invoke the unchanged managed four-phase runner."""
import argparse,json,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from pow2_memory_isolated_review import validator,inspect,flatten,inspect_clint_window,ELF,ROLE
from batch_runner import digest,prepare,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
WATCHDOG=1200;PHASE_TIMEOUT=1380
def merge(target,other):
 for p,h in other.items():
  p=str(Path(p).resolve())
  if p in target and target[p]!=h:raise ValueError('Conflicting bound source '+p)
  target[p]=h
def admit(build,expected):
 b=Path(build).resolve();ready=json.loads((b/'ready.json').read_text());built=json.loads((b/'build.json').read_text());q=json.loads((b/'qualification.json').read_text());corpus=json.loads((b/'corpus.json').read_text());layout=json.loads((b/'layout.json').read_text());elf=b/'footprints.elf'
 if digest(b/'ready.json')!=expected or ready['schema']!='iris.pow2_isolated_memory_ready.v3'or ready['status']!='ready_for_root_managed_preparation'or ready['source_frozen']is not True or ready['new_exact_reference_required']is not True:raise ValueError('Exact new frozen ready required')
 for name,want in ready['artifact_sha256'].items():
  if digest(b/name)!=want:raise ValueError('Changed readyartifact '+name)
 if digest(elf)!=ELF or ready['elf_sha256']!=ELF or built['elf_sha256']!=ELF or built['negative_skip_kernel']is not False or q['pass']is not True:raise ValueError('Actual positive ELF/qualification')
 validator().validate_corpus(corpus);binary=inspect(elf.read_bytes(),corpus,layout);inspect_clint_window(elf.read_bytes())
 if binary!=q['compiled_and_layout_proof']or len(q['negative_controls'])!=22 or any(x['rejected']is not True for x in q['negative_controls']):raise ValueError('Compiled table/layout/22 corruptions')
 if q['actual_omitted_kernel']['failed_regions']!=234 or q['protocol_proof']['foreign_writes_during_window']!=0 or q['protocol_proof']['states']!=51 or q['protocol_proof']['delayed_wake_consumed_before_next_ack']is not True:raise ValueError('Actual omission and isolated WFI protocol')
 cases=flatten(corpus);validate_cases(cases,True)
 if cases!=json.loads((b/'host-cases.json').read_text()):raise ValueError('Canonical host case order')
 ids={str(b/name):digest(b/name)for name in['ready.json','build.json','qualification.json','corpus.json','layout.json','review.json','host-cases.json','protocol-proof.json','footprints.elf']}
 merge(ids,built['input_sha256']);merge(ids,q['input_sha256'])
 if {r['seed']for r in q['functional']}!={0,17}or len(q['functional'])!=2:raise ValueError('Both actual functional schedules')
 for row in q['functional']:
  p=Path(row['report']);r=json.loads(p.read_text());d=p.parent
  if digest(p)!=row['report_sha256']or r['pass']is not True or r['normal_guest_exit_verified']is not True or r['exit_status']!=0 or r['timed_out']is not False or r['elf_sha256']!=ELF or any(x.startswith('--iris-timing-')for x in r['argv']):raise ValueError('Actual functional exit/source')
  if digest(d/'stdout')!=r['stdout_sha256']or digest(d/'stderr')!=r['stderr_sha256']:raise ValueError('Changed functional output')
  validator().validate((d/'stdout').read_text(),corpus);merge(ids,r['input_sha256'])
 neg=Path(q['actual_omitted_kernel']['report']);r=json.loads(neg.read_text())
 if digest(neg)!=q['actual_omitted_kernel']['report_sha256']or r['pass']is not True or r['expect_negative']is not True or r['timed_out']is not False or r['proof']!=dict(actual_omitted_kernel_detected=True,failed_regions=234):raise ValueError('Real compiled skip must fail all234')
 for p,h in ids.items():
  if digest(p)!=h:raise ValueError('Bound input changed '+p)
 return ready,corpus,cases,elf,ids
def freeze(a):
 import yaml
 b=a.build.resolve();out=a.output.resolve();ready,corpus,cases,elf,ids=admit(b,a.expected_ready_sha256)
 if a.validate_only:return dict(status='localadmissionpassed',cohorts=117,regions=234,hardware_contacted=False)
 auth=a.authorization_receipt.resolve();grant=json.loads(auth.read_text())
 if grant['schema']!='iris.remote_user_launch_authorization_receipt.v1':raise ValueError('Actual user authorization receipt')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');d=fs/'deploy';manager,m=prepare(d,out,elf,cases,d/'config_runtime.yaml',d/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),out,m);add_observer(manager);watch=manager/'iris_workload_watchdog.py';text=watch.read_text()
 if text.count('SECONDS=1500')!=1:raise ValueError('Reviewed watchdog source changed')
 watch.write_text(text.replace('SECONDS=1500','SECONDS=1200',1));runtime=manager/'config_runtime.yaml';r=yaml.safe_load(runtime.read_text());old=r['target_config'].get('plusarg_passthrough','')
 if '+fesvr-step-size'in old or '+max-cycles'in old:raise ValueError('Conflicting loader/target-cycle bound')
 r['target_config']['plusarg_passthrough']=(old+' +fesvr-step-size=128').strip();runtime.write_text(yaml.safe_dump(r,sort_keys=False))
 for name in['ready.json','build.json','qualification.json','corpus.json','layout.json','review.json','host-cases.json','protocol-proof.json']:(out/name).write_bytes((b/name).read_bytes())
 (out/'CLINT-assembly-proof.json').write_text(json.dumps(inspect_clint_window(elf.read_bytes()),indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'launch-authorization.json').write_bytes(auth.read_bytes())
 check=dict(schema='iris.pow2_isolated_memory_capture_checklist.v3',frozen_before_launch=True,fitting_only=True,global_heldout=False,new_exact_reference_required=True,cohorts=117,declared_cases=234,expected_regions=234,trials=3,passes=2,harts_online=[0,1,2],active_masks=[1,2,4],single_active_hart=True,min_dependent_loads=1024,whole_laps=True,eviction_bytes=8388608,history=corpus['protocol'],cold_definition=corpus['cold_definition'],steady_definition=corpus['steady_definition'],all_output_after_measurements=True,record_bytes=128,physical_hit_or_miss_measured=False,source_image_association_verified=False,calibration_usable=False,wall_watchdog_seconds=WATCHDOG,phase_timeout_seconds=PHASE_TIMEOUT,target_max_cycles=None,required=['All234typedroles/pointers/counts/conditioning/MSIP/countergoldens andnormalexit','Allfourmanagedphases andownership/lock/cleanup/quiescentcapture','ExactELF/compiledtable/layout/oracles/source/driver/image/runtime/observers/authorization','No oldtiming transfer or physical cold/miss/traffic assertion'])
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n');launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])];(out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_pow2_memory_isolated.py',ROOT/'firesim/pow2_memory_isolated_review.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',ROOT/'calibration/pow2-memory-isolated-v2/split.json',auth,ROOT/'build/xilinx-tool-paths-v1.json',*env]
 sources += list((ROOT/'benchmarks/pow2_memory_isolated_v3').glob('*.py'))+[ROOT/'benchmarks/pow2_memory_isolated_v3/guest.c'];merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256'])
 m.update(reserved_timing_labels_root_only=True,train_regions=180,reserved_regions=54,frozen_split_sha256=corpus['frozen_split_sha256'],require_regions=True,require_goldens=True,campaign_role=ROLE,fitting_only=True,global_heldout=False,new_exact_reference_required=True,old_campaign_timings_applicable=False,cohorts=117,expected_regions=234,launch_authorization_receipt=grant,corpus_sha256=digest(out/'corpus.json'),reviewed_ready_sha256=digest(out/'ready.json'),calibration_usable=False,physical_hit_or_miss_measured=False,hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=out)};save_manifest(out,m);verify(out);return dict(status=m['status'],cohorts=117,regions=234,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
