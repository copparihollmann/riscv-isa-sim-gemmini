#!/usr/bin/env python3
"""Prepare only; root alone may invoke the unchanged managed four-phase runner."""
import argparse,json,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from rvv_compute1320_review import validator,inspect,flatten,inspect_clint_window,ELF,ROLE
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
 b=Path(build).resolve();ready=json.loads((b/'ready.json').read_text());built=json.loads((b/'build.json').read_text());q=json.loads((b/'qualification.json').read_text());corpus=json.loads((b/'corpus.json').read_text());layout=json.loads((b/'layout.json').read_text());elf=b/'guest.elf'
 if digest(b/'ready.json')!=expected or ready['schema']!='iris.rvv_identify_ready.v1' or ready['source_frozen']is not True or ready['new_exact_reference_required']is not True:raise ValueError('Exact new frozen RVV ready')
 for name,want in ready['artifact_sha256'].items():
  if digest(b/name)!=want:raise ValueError('Changed ready artifact '+name)
 if json.loads((b/'scope-proof.json').read_text())['retained_hart01_reserved_case_IDs_identical']is not True or 'all hart2 calibration cases excluded'not in corpus['scope_exclusion']:raise ValueError('Explicit new1320 scope exclusion')
 if digest(elf)!=ELF or built['ELF_sha256']!=ELF or ready['ELF_sha256']!=ELF or built['skip_kernel']is not False or q['pass']is not True:raise ValueError('Exact positive ELF')
 validator().validate_corpus(corpus);binary=inspect(elf.read_bytes(),corpus,layout);phase=inspect_clint_window(elf.read_bytes())
 if binary!=q['compiled_and_layout_proof'] or phase!=q['compiled_counter_phase_proof'] or len(q['corruption_controls'])!=40 or any(x['rejected']is not True for x in q['corruption_controls']):raise ValueError('Compiled case/count/layout/phase and40refusals')
 if q['actual_omitted_kernel']['failed_regions']!=1320 or q['per_element_words_checked_per_schedule']!=184128 or q['quiet_hart_protocol']['MSIP_wakeups']!=1 or q['quiet_hart_protocol']['deadlocks']!=0:raise ValueError('Actual omission/word/quiet protocol')
 cases=flatten(corpus);validate_cases(cases,True)
 if cases!=json.loads((b/'host-cases.json').read_text()):raise ValueError('Host role/golden/order mismatch')
 ids={str(b/name):digest(b/name)for name in['scope-proof.json','ready.json','build.json','qualification.json','corpus.json','layout.json','review.json','host-cases.json','protocol-proof.json','phase-proof.json','guest.elf']};merge(ids,built['input_sha256']);merge(ids,q['input_sha256'])
 if {r['seed']for r in q['functional']}!={0,17}or len(q['functional'])!=2:raise ValueError('Both real359schedules')
 for row in q['functional']:
  p=Path(row['report']);r=json.loads(p.read_text());d=p.parent
  if digest(p)!=row['report_sha256'] or r['pass']is not True or r['exit_status']!=0 or r['timed_out']is not False or r['normal_guest_exit_verified']is not True or r['elf_sha256']!=ELF or any(x.startswith('--iris-timing-')for x in r['argv']):raise ValueError('Actual normal functional run')
  if digest(d/'stdout')!=r['stdout_sha256']or digest(d/'stderr')!=r['stderr_sha256']:raise ValueError('Changed seeded raw output')
  validator().validate((d/'stdout').read_text(),corpus);merge(ids,r['input_sha256'])
 neg=Path(q['actual_omitted_kernel']['report']);n=json.loads(neg.read_text())
 if digest(neg)!=q['actual_omitted_kernel']['report_sha256']or n['pass']is not True or n['expect_negative']is not True or n['timed_out']is not False or n['exit_status']==0 or n['proof']!=dict(actual_omitted_kernel_detected=True,failed_regions=1320):raise ValueError('Real compiled omission')
 for p,h in ids.items():
  if digest(p)!=h:raise ValueError('Bound source changed '+p)
 return ready,corpus,cases,elf,ids
def freeze(a):
 import yaml
 b=a.build.resolve();out=a.output.resolve();ready,corpus,cases,elf,ids=admit(b,a.expected_ready_sha256)
 if a.validate_only:return dict(status='localadmissionpassed',cohorts=1320,regions=1320,hardware_contacted=False)
 auth=a.authorization_receipt.resolve();grant=json.loads(auth.read_text())
 if grant['schema']!='iris.remote_user_launch_authorization_receipt.v1':raise ValueError('Actual user authorization receipt')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');d=fs/'deploy';manager,m=prepare(d,out,elf,cases,d/'config_runtime.yaml',d/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),out,m);add_observer(manager);watch=manager/'iris_workload_watchdog.py';text=watch.read_text()
 if text.count('SECONDS=1500')!=1:raise ValueError('Reviewed watchdog source changed')
 watch.write_text(text.replace('SECONDS=1500','SECONDS=1200',1));runtime=manager/'config_runtime.yaml';r=yaml.safe_load(runtime.read_text());old=r['target_config'].get('plusarg_passthrough','')
 if '+fesvr-step-size'in old or '+max-cycles'in old:raise ValueError('Conflicting loader/target-cycle bound')
 r['target_config']['plusarg_passthrough']=(old+' +fesvr-step-size=128').strip();runtime.write_text(yaml.safe_dump(r,sort_keys=False))
 for name in['scope-proof.json','ready.json','build.json','qualification.json','corpus.json','layout.json','review.json','host-cases.json','protocol-proof.json','phase-proof.json']:(out/name).write_bytes((b/name).read_bytes())
 (out/'CLINT-assembly-proof.json').write_text(json.dumps(inspect_clint_window(elf.read_bytes()),indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'launch-authorization.json').write_bytes(auth.read_bytes())
 check=dict(schema='iris.rvv_identify_capture_checklist.v1',frozen_before_launch=True,fitting_only=True,global_heldout=False,new_exact_reference_required=True,cohorts=1320,declared_cases=1320,expected_regions=1320,trials=3,harts_online=[0,1,2],single_active_hart=True,all_output_after_measurements=False,all_output_after_own_hart_measurements=True,phase_handoffs=1,record_bytes=192,exact_words_checked_per_schedule=184128,source_counter_windows='actualbefore/issue/drainMCYCLE+MINSTRET;CLINToutside;nosubtraction',source_geometry='VLEN256;DLEN128compute/256Rocket;externalATL256compute/64Rocket;LSUrequests/TLtransactionsnotmeasured',rowmove_scope=corpus['rowmove'],scope_exclusion=corpus['scope_exclusion'],wire_format=corpus['wire_format'],history='Compact17Qbase64;grouped0then1;hart2permanentpark;oneMSIPwake;no-percaseIPI/WFI;ownsectionUARTdrainedbeforehandoff;newELF/history',physical_hit_or_miss_measured=False,physical_traffic_measured=False,source_image_association_verified=False,calibration_usable=False,wall_watchdog_seconds=WATCHDOG,phase_timeout_seconds=PHASE_TIMEOUT,target_max_cycles=None,required=['All1320typedrawphase/role/word/countgoldens+normalexit','Completeownedfourphase/inspection/lock/cleanup/archive','Exactsource/ELF/compiledcase/layout/counterphase/driver/image/runtime/observers','Nooldtimingsorphysicaltraffic/cold/sourceimageclaim'])
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n');launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])];(out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_rvv_compute1320.py',ROOT/'firesim/rvv_compute1320_review.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',ROOT/'calibration/rvv-compute1320-v1/split.json',auth,ROOT/'build/xilinx-tool-paths-v1.json',*env]
 sources += [ROOT/'calibration/rvv-compute1320-v1/fit-plan.json'];sources += list((ROOT/'benchmarks/rvv_compute1320_v1').glob('*.py'))+[ROOT/'benchmarks/rvv_compute1320_v1/guest.c'];merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256'])
 m.update(reserved_timing_labels_root_only=True,train_regions=978,reserved_regions=342,frozen_split_sha256=corpus['frozen_split_sha256'],require_regions=True,require_goldens=True,campaign_role=ROLE,fitting_only=True,global_heldout=False,new_exact_reference_required=True,old_campaign_timings_applicable=False,cohorts=1320,expected_regions=1320,launch_authorization_receipt=grant,corpus_sha256=digest(out/'corpus.json'),reviewed_ready_sha256=digest(out/'ready.json'),calibration_usable=False,physical_hit_or_miss_measured=False,hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 m['compact_collector']=dict(format='IRIS_BIN_17Q_LE_base64_v1',review_path=str(ROOT/'firesim/rvv_compute1320_review.py'),review_sha256=digest(ROOT/'firesim/rvv_compute1320_review.py'),corpus_sha256=digest(out/'corpus.json'),ELF_sha256=digest(elf),ready_sha256=digest(out/'ready.json'))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=out)};save_manifest(out,m);verify(out);return dict(status=m['status'],cohorts=1320,regions=1320,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
