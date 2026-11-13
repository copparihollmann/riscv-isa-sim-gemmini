#!/usr/bin/env python3
"""Locally prepare the exact scalar SMP bringup; root alone launches hardware."""
import argparse,json,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'zephyr'))
from fpga_bringup_v2 import validate,host_cases,need
from batch_runner import prepare,digest,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='Zephyr_scalar6_three_hart_functional_bringup_v2'
WATCHDOG=180
PHASE_TIMEOUT=360

def merge(target,source):
 for name,value in source.items():
  path=Path(name);path=path if path.is_absolute()else ROOT/path;name=str(path.resolve())
  need(name not in target or target[name]==value,'Conflicting input identity '+name)
  need(digest(name)==value,'Changed bound input '+name);target[name]=value

def admit(qualification,expected):
 b=Path(qualification).resolve();need(digest(b/'ready.json')==expected,'Exact ready identity')
 ready=json.loads((b/'ready.json').read_text());q=json.loads((b/'qualification.json').read_text());corpus=json.loads((b/'corpus.json').read_text())
 need(ready['schema']=='iris.Zephyr_scalar6_bringup_ready.v2'and ready['status']=='ready_for_root_managed_preparation','Qualified bringup ready')
 need(ready['qualification_sha256']==digest(b/'qualification.json')and ready['corpus_sha256']==digest(b/'corpus.json'),'Ready proof binding')
 need(q['pass']is True and q['FPGA_execution_performed']is False and q['source_overlay']is None and q['compiled_kernel_dependencies']>100,'Actual native-only clean kernel qualification')
 elf=Path(q['build'])/'zephyr/zephyr.elf'
 need(digest(elf)==ready['ELF_sha256']==q['ELF_sha256'],'Actual approved ELF')
 cases=host_cases();need(corpus['cases']==cases and corpus['regions']==6 and corpus['calibration_usable']is False,'Independent finite scalar6 corpus')
 validate_cases(cases,True);ids={}
 merge(ids,q['input_sha256'])
 for name,value in q['input_sha256'].items():need(digest(b/'inputs'/value)==value,'Missing exact compiled source snapshot '+name)
 need(len(q['functional'])==2 and {x['seed']for x in q['functional']}=={0,17},'Both native schedules')
 for gate in q['functional']:
  report=Path(gate['report']);r=json.loads(report.read_text())
  need(digest(report)==gate['report_sha256']and r['exit_status']==0 and r['timed_out']is False and r['elf_sha256']==digest(elf),'Actual positive seeded run')
  need(digest(report.parent/'stdout')==r['stdout_sha256']and digest(report.parent/'stderr')==r['stderr_sha256'],'Exact seeded raw bytes')
  need(validate((report.parent/'stdout').read_text(),False)==gate['proof'],'Independent fresh checksum/role validation')
  run_inputs={r['argv'][0]:r['binary_sha256']}
  for flag,key in [('--extlib=','uart_sha256'),('--iris-bootrom=','rom_sha256'),('--dtb=','dtb_sha256')]:
   paths=[x[len(flag):]for x in r['argv']if x.startswith(flag)];need(len(paths)==1,'One exact native launch input '+flag);run_inputs[paths[0]]=r[key]
  need(r['physical_boot']is True and r['checksums_independent']is True and '-p3'in r['argv']and not any(x.startswith('--iris-timing-')for x in r['argv']),'Physical functional3hart gate')
  merge(ids,run_inputs)
 merge(ids,{str(b/name):digest(b/name)for name in ['ready.json','qualification.json','corpus.json','HTIF-exit-disassembly.txt','compiled-dependencies.txt']})
 return ready,q,corpus,cases,elf,ids

def freeze(a):
 import yaml
 b=a.qualification.resolve();out=a.output.resolve();ready,q,corpus,cases,elf,ids=admit(b,a.expected_ready_sha256)
 if a.validate_only:return dict(status='admitted_locally',regions=6,hardware_contacted=False)
 auth=a.authorization_receipt.resolve();grant=json.loads(auth.read_text())
 need(grant['schema']=='iris.remote_user_launch_authorization_receipt.v1','Actual standing user authorization receipt')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');d=fs/'deploy'
 manager,m=prepare(d,out,elf,cases,d/'config_runtime.yaml',d/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),out,m);add_observer(manager)
 watchdog=manager/'iris_workload_watchdog.py';s=watchdog.read_text();need(s.count('SECONDS=1500')==1,'Reviewed watchdog parameter');watchdog.write_text(s.replace('SECONDS=1500','SECONDS=180',1))
 runtime=manager/'config_runtime.yaml';r=yaml.safe_load(runtime.read_text());old=r['target_config'].get('plusarg_passthrough','')
 need('+max-cycles'not in old and '+fesvr-step-size'not in old,'No conflicting target bound/loader override')
 r['target_config']['plusarg_passthrough']=(old+' +fesvr-step-size=128').strip();runtime.write_text(yaml.safe_dump(r,sort_keys=False))
 for name in ['ready.json','qualification.json','corpus.json','HTIF-exit-disassembly.txt']:(out/name).write_bytes((b/name).read_bytes())
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'launch-authorization.json').write_bytes(auth.read_bytes())
 check=dict(schema='iris.Zephyr_scalar6_bringup_capture_checklist.v2',frozen_before_launch=True,expected_regions=6,cases=2,harts_online=[0,1,2],worker_mask=7,role='scalar.compute',functional_only=True,calibration_usable=False,timing_certified=False,source_image_association_verified=False,wall_watchdog_seconds=WATCHDOG,phase_timeout_seconds=PHASE_TIMEOUT,target_max_cycles=None,UART_profile=ready['UART_profile'],completion='Actual six checked IRIS_REGION objects, unchanged IRIS_BATCH_DONE{failed:0}, COMMAND_EXIT_CODE0 and driver PASSED; no fabricated records.',interrupt_scope='Three pinned workers complete mutex/yield and two1ms sleeps each. No per-hart IRQ/IPI counters are emitted.',previous_stall_scope='Original285 image stopped after25 repeatedly; several perturbed285 images completed. Cause unproved; no inferred actual stall PC.',no_target_cycle_bound_reason='Original signed32 max-cycles parser can overflow; successful boot/loading can exceed5B global driver cycles.',required=['Full owned kill/setup/workload/kill, fresh complete inspection/auth/boot/group lock before each phase, cleanup and archive on both outcomes','Actual guest UART, raw counters/checksums/profile/footer and normal process exit','Exact compiled kernel dependency/source/ELF/driver/image/runtime/observer identities','Preinit read-only and optional postdriver five-config-register observation; observation error separate from guest result'],unavailable_claims=['No explicit per-hart IRQ/IPI counts','No RVV/VME/context-switch coverage in scalar6','No whole source/image equivalence or timing certification'])
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n')
 launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])]
 (out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh']
 sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_zephyr_bringup_v2.py',ROOT/'firesim/test_zephyr_bringup_v2.py',ROOT/'zephyr/fpga_bringup_v2.py',ROOT/'zephyr/fpga_bringup_audit_v1.py',ROOT/'zephyr/FPGA_BRINGUP_V2.md',ROOT/'timing/fp8_format_functional_audit_v1.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/setup_phase_observer.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'build/zephyr-fpga-functional-status-audit-v1/report.json',ROOT/'build/zephyr-fpga-bringup-helper-tests-v2/report.json',ROOT/'build/xilinx-tool-paths-v1.json',auth,*env]
 merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256'])
 m.update(require_regions=True,require_goldens=True,campaign_role=ROLE,functional_only=True,expected_regions=6,calibration_usable=False,hardware_source_association_verified=False,launch_authorization_receipt=grant,reviewed_ready_sha256=digest(out/'ready.json'),corpus_sha256=digest(out/'corpus.json'),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(x.is_symlink()for x in p.parents if x!=out)}
 save_manifest(out,m);verify(out)
 from memory_observation_postrun_v2 import install
 post=install(out,digest(out/'run.json'),a.postrun_probe_build.resolve(),'sohumpc')
 return dict(status='prepared',regions=6,ELF_sha256=digest(elf),prepared_manifest_sha256=digest(out/'run.json'),postrun_plan_sha256=post['plan_sha256'],hardware_contacted=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--postrun-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
