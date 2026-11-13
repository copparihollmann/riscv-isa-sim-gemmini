#!/usr/bin/env python3
"""Freeze the reviewed117cohort/234pass fitting batch; no hardware actions."""
import argparse,json,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from overlap_capture_common_v1 import validator,inspect,host_cases,ELF,PARENT_READY,SPLIT_SHA,is_reserved
from batch_runner import digest,prepare,save_manifest,validate_cases,parse_regions
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='source_overlap_completion_validation_v1';WATCHDOG=600;PHASE_TIMEOUT=780
def merge(target,other):
 for name,wanted in other.items():
  p=Path(name);key=str((p if p.is_absolute()else ROOT/p).resolve())
  if key in target and target[key]!=wanted:raise ValueError('Conflicting sourceidentity '+key)
  target[key]=wanted

def admit(build,ready_sha):
 packet=Path(build).resolve();ready=json.loads((packet/'ready.json').read_text());b=Path(ready['build']);qpath=Path(ready['qualification']);q=json.loads(qpath.read_text());built=json.loads((b/'build.json').read_text());corpus=json.loads((b/'corpus.json').read_text());layout=json.loads((b/'readback-layout.json').read_text());elf=b/'overlap.elf'
 if digest(packet/'ready.json')!=ready_sha or ready_sha!=PARENT_READY or ready.get('schema')!='iris.overlap_completion_ready.v2'or ready.get('pass')is not True or ready['ELF_sha256']!=ELF or ready['regions']!=168:raise ValueError('Exact frozen source packet')
 if digest(elf)!=ELF or digest(qpath)!=ready['qualification_sha256']or q.get('schema')!='iris.overlap_completion_console_qualification.v2'or q.get('pass')is not True or built.get('pass')is not True or built['elf_sha256']!=ELF:raise ValueError('Actual source/ELF qualification')
 if len(q['typed_corruption_controls'])!=14 or any(x['rejected']is not True for x in q['typed_corruption_controls'])or q['numeric_elements_per_run']!=19872 or q['own_timed_baseline_672_CSR_ELF_joins']is not True or q['baseline_normal_exit_claimed']is not False:raise ValueError('Exact14controls/19872elements/672ownbaseline endpoints')
 proof=inspect(elf.read_bytes(),corpus,layout);cases=host_cases(corpus);validate_cases(cases,True)
 splitpath=ROOT/'calibration/overlap-mechanism-v1/split.json';split=json.loads(splitpath.read_text())
 if digest(splitpath)!=SPLIT_SHA or split['corpus_sha256']!=digest(b/'corpus.json')or split['reserved_case_indices']!=[c['id']for c in corpus['cases']if is_reserved(c)]or split['train_regions']!=114 or split['reserved_regions']!=54:raise ValueError('Frozen complete shape-role split')
 ids={str(p):digest(p)for p in[packet/'ready.json',qpath,b/'build.json',b/'corpus.json',b/'readback-layout.json',elf,splitpath]}
 for source in[built['input_sha256'],q['input_sha256'],ready['input_sha256']]:merge(ids,source)
 if [x['seed']for x in q['functional_normal_exit_runs']]!=[0,17]:raise ValueError('Both actual functional schedules')
 for row in q['functional_normal_exit_runs']:
  p=Path(row['run']);r=json.loads(p.read_text())
  if r['pass']is not True or r['normal_HTIF_exit']is not True or r['forced_debug_quit']is not False or r['ELF_sha256']!=ELF or r['seed']!=row['seed']:raise ValueError('Actual normal console guest/seed')
  text=(p.parent/'stdout').read_text();validator().validate(text,corpus)
  parsed=parse_regions(text,cases,ELF,'0'*64,True,True)
  if len(parsed)!=168:raise ValueError('Allindependenthostchecksumjoins')
  merge(ids,r['input_sha256']);merge(ids,{str(x):digest(x)for x in[p,p.parent/'stdout',p.parent/'stderr']})
 for name,want in ids.items():
  if digest(name)!=want:raise ValueError('Frozen input changed '+name)
 return ready,corpus,cases,elf,ids

def freeze(a):
 import yaml
 packet=a.build.resolve();out=a.output.resolve();authorization=a.authorization_receipt.resolve();ready,corpus,cases,elf,ids=admit(packet,a.expected_ready_sha256);b=Path(ready['build'])
 if a.validate_only:return dict(status='localadmissionpassed',cohorts=168,declared_cases=168,regions=168,hardware_contacted=False)
 grant=json.loads(authorization.read_text())
 if grant.get('schema')!='iris.remote_user_launch_authorization_receipt.v1':raise ValueError('Actualstandinguserreceipt')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');d=fs/'deploy';manager,m=prepare(d,out,elf,cases,d/'config_runtime.yaml',d/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),out,m);add_observer(manager);watch=manager/'iris_workload_watchdog.py';text=watch.read_text()
 if text.count('SECONDS=1500')!=1:raise ValueError('Reviewedwatchdogchanged')
 watch.write_text(text.replace('SECONDS=1500','SECONDS=600',1));runtime=manager/'config_runtime.yaml';r=yaml.safe_load(runtime.read_text());old=r['target_config'].get('plusarg_passthrough','')
 if '+fesvr-step-size'in old or '+max-cycles'in old:raise ValueError('Conflictingloader/unsafe targetbound')
 r['target_config']['plusarg_passthrough']=(old+' +fesvr-step-size=128').strip();runtime.write_text(yaml.safe_dump(r,sort_keys=False))
 for name in['build.json','corpus.json','readback-layout.json']:(out/name).write_bytes((b/name).read_bytes())
 (out/'ready.json').write_bytes((packet/'ready.json').read_bytes());(out/'qualification.json').write_bytes(Path(ready['qualification']).read_bytes());(out/'frozen-split.json').write_bytes((ROOT/'calibration/overlap-mechanism-v1/split.json').read_bytes());(out/'compiled-proof.json').write_text(json.dumps(inspect(elf.read_bytes(),corpus,json.loads((b/'readback-layout.json').read_text())),indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'launch-authorization.json').write_bytes(authorization.read_bytes());check=dict(schema='iris.source_overlap_capture_checklist.v1',frozen_before_launch=True,regions=168,trials=3,all3harts_boot=True,single_active_hart=True,all_others_WFI=True,compute_harts=[0,1],hart2_positive_RVV_and_VME_refusal=True,compute_operand_dtypes=['unsigned-int8-to-int32','E4M3-E4M3-to-FP32'],numeric_elements=19872,matrix_coverage='row0of4tiles;32wordseachincludinginactivecolumns; NOTallMRFrows',vector_console_coverage='activeVLbytesonly; nopaddingclaim',four_timestamps_per_region=['start','issue_end','fence_end','dependent_drain_end'],boundary_values=672,instret_scope='TOTAL region delta only; no fabricated per-boundary instret',all_console_output_after_last_measured_case=True,no_incremental_ROI_progress_before_measurement_completion=True,warmup_and_known_reset_before_each_case=True,reserved_timing_labels_root_only=True,reserved_rule='computeedge16 +DMA-VL64 allotherparameters/trials',train_regions=114,reserved_regions=54,source_mechanism_validation=True,new_exact_reference_required=True,no_old_timing_transfer=True,source_image_association_verified=False,CLINT_samples_available=False,physical_traffic_or_MAC_count_measured=False,all4managed_phases_required=True,wall_watchdog_seconds=WATCHDOG,phase_timeout_seconds=PHASE_TIMEOUT,target_max_cycles=None,target_bound_omission_reason='Successfulloaderexceeded5billioncycles; originaldriveratoi32. Useownedwallwatchdog.',unavailable_instrumentation=['TracerV','AutoCounter','SynthPrint'],calibration_usable=False)
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n');launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])];(out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_overlap_completion_v1.py',ROOT/'firesim/overlap_capture_common_v1.py',ROOT/'benchmarks/overlap_completion_v1/validate_console.py',ROOT/'calibration/overlap-mechanism-v1/split.json',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',authorization,ROOT/'build/xilinx-tool-paths-v1.json',*env,Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')];merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256']);m.update(reserved_timing_labels_root_only=True,train_regions=114,reserved_regions=54,frozen_split_sha256=SPLIT_SHA,require_regions=True,require_goldens=True,campaign_role=ROLE,fitting_only=False,global_heldout=False,new_exact_reference_required=True,old_campaign_timings_applicable=False,cohorts=168,expected_regions=168,launch_authorization_receipt=grant,corpus_sha256=digest(out/'corpus.json'),reviewed_ready_sha256=digest(out/'ready.json'),timing_perturbed=True,calibration_usable=False,physical_hit_or_miss_measured=False,hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=out)};save_manifest(out,m);verify(out);return dict(status=m['status'],cohorts=168,declared_cases=168,regions=168,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
