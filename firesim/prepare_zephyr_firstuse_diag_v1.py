#!/usr/bin/env python3
"""Prepare the NEW firstuse diagnostic ELF; root alone launches hardware."""
import argparse,json,shlex,sys,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'zephyr'))
from firstuse_diag_validate_v1 import validate,cases as host_cases,need
from firstuse_diag_qualify_v1 import codeproof,PATCH
from batch_runner import prepare,digest,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='Zephyr_firstuse_h2_scalar_diagnostic_v1'
WATCHDOG=180
PHASE_TIMEOUT=360

def merge(target,source):
 for name,value in source.items():
  path=Path(name);path=path if path.is_absolute()else ROOT/path;name=str(path.resolve())
  need(name not in target or target[name]==value,'Conflicting input identity '+name)
  need(digest(name)==value,'Changed bound input '+name);target[name]=value

def admit(qualification,expected):
 b=Path(qualification).resolve();need(digest(b/'ready.json')==expected,'Exact diagnostic ready')
 ready=json.loads((b/'ready.json').read_text());q=json.loads((b/'qualification.json').read_text());elf=Path(q['build'])/'zephyr/zephyr.elf'
 need(ready['schema']=='iris.Zephyr_firstuse_diagnostic_ready.v1'and ready['status']=='native_qualified_pending_managed_preparation'and ready['diagnostic_only']is True,'New diagnostic scope')
 need(ready['qualification_sha256']==digest(b/'qualification.json')and ready['cases_sha256']==digest(b/'cases.json')and digest(elf)==ready['ELF_sha256']==q['ELF_sha256'],'Actual normal candidate')
 need(q['pass']is True and q['normal_regions']==9 and q['h2_application_vector']is False and q['kernel_overlay_sha256']==PATCH and q['kernel_source_changed']is False,'Unchanged kernel/scalarh2 scope')
 need(codeproof(elf)==q['code_proof'],'Actual scalar-only/hot instruction proof')
 cases=host_cases();need(json.loads((b/'cases.json').read_text())==cases,'Exact independent host cases');validate_cases(cases,True)
 ids={};merge(ids,q['input_sha256'])
 for name,h in q['input_sha256'].items():need(digest(b/'inputs'/h)==h,'Exact qualification source copy '+name)
 for negative,entries in [(False,q['normal_gates']),(True,q['forced_actual_HTIF1_controls'])]:
  need(len(entries)==2 and{g['seed']for g in entries}=={0,17},'Both normal/forced schedules')
  for gate in entries:
   p=Path(gate['report']);r=json.loads(p.read_text());need(digest(p)==gate['report_sha256']and r['pass']is True and r['expect_failure']is negative and r['exit_status']==(1 if negative else 0)and r['timed_out']is False,'Actual normal/negative execution')
   need(digest(p.parent/'stdout')==r['stdout_sha256']and digest(p.parent/'stderr')==r['stderr_sha256']and validate((p.parent/'stdout').read_text(),negative)==r['proof'],'Strict actual diagnostic bytes')
   if not negative:need(r['ELF_sha256']==digest(elf),'Exact normal ELF')
 for p in b.iterdir():
  if p.is_file():merge(ids,{str(p):digest(p)})
 corpus=dict(schema='iris.Zephyr_firstuse_diagnostic_corpus.v1',cases=cases,regions=9,functional_only=True,diagnostic_only=True,calibration_usable=False,harts=[0,1,2],hart2_application_vector=False,actual_progress_scope='Lastrecorded physical/logical/pin/sourcepoint; no currentPC or physicalcompletion claim')
 return ready,q,corpus,cases,elf,ids

def freeze(a):
 import yaml
 b=a.qualification.resolve();out=a.output.resolve();ready,q,corpus,cases,elf,ids=admit(b,a.expected_ready_sha256)
 if a.validate_only:return dict(status='admitted_locally',regions=9,hardware_contacted=False)
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
 for p in b.iterdir():
  if p.is_file():(out/p.name).write_bytes(p.read_bytes())
 (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'launch-authorization.json').write_bytes(auth.read_bytes())
 check=dict(schema='iris.Zephyr_firstuse_diagnostic_capture_checklist.v1',frozen_before_launch=True,expected_regions=9,cases=3,harts_online=[0,1,2],worker_mask=7,roles=['scalar.compute','vme.compute','scalar.control'],functional_only=True,calibration_usable=False,timing_certified=False,source_image_association_verified=False,wall_watchdog_seconds=WATCHDOG,phase_timeout_seconds=PHASE_TIMEOUT,target_max_cycles=None,UART_profile=dict(requested_baud=3676470,clock_hz=500000000,divisor=135),completion='Actual nine checked IRIS_REGION objects, unchanged IRIS_BATCH_DONE{failed:0}, exact dated script header/command/footer exit0 and driver PASSED; no fabricated records.',interrupt_scope='Three pinned workers complete mutex/yield and two1ms sleeps each. No per-hart IRQ/IPI counters are emitted.',previous_stall_scope='Original93a mixed9 stopped afterscalar6; original285 stoppedafter25. NoactualstallPC/firstuse execution proved. Newh2scalarobserver andmarkers perturbhistory.',no_target_cycle_bound_reason='Original signed32 max-cycles parser can overflow; successful boot/loading can exceed5B global driver cycles.',required=['Full owned kill/setup/workload/kill, fresh complete inspection/auth/boot/group lock before each phase, cleanup and archive on both outcomes','Actual guest UART, raw counters/checksums/profile/footer and normal process exit','Exact compiled kernel dependency/source/ELF/driver/image/runtime/observer identities','Preinit read-only and optional postdriver five-config-register observation; observation error separate from guest result'],unavailable_claims=['No explicit per-hart IRQ/IPI counts; h2 application FP/vector absent','One VME owner per compute hart; no competing-owner, migration or actual context-count claim','No whole source/image equivalence or timing certification'])
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n')
 launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout',str(PHASE_TIMEOUT)])]
 (out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh']
 sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_zephyr_firstuse_diag_v1.py',ROOT/'firesim/test_zephyr_firstuse_diag_v1.py',ROOT/'zephyr/firstuse_diag_validate_v1.py',ROOT/'zephyr/firstuse_diag_run_v1.py',ROOT/'zephyr/firstuse_diag_qualify_v1.py',ROOT/'zephyr/mixed9_failed_frontier_audit_v1.py',ROOT/'zephyr/script_envelope_v3.py',ROOT/'zephyr/fpga_bringup_audit_v1.py',ROOT/'zephyr/FIRSTUSE_DIAGNOSTIC_V1.md',ROOT/'timing/fp8_format_functional_audit_v1.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/setup_phase_observer.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'build/zephyr-fpga-functional-status-audit-v1/report.json',ROOT/'build/zephyr-firstuse-diag-helper-tests-v1/report.json',ROOT/'build/xilinx-tool-paths-v1.json',auth,*env]
 merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256'])
 m.update(require_regions=True,require_goldens=True,campaign_role=ROLE,functional_only=True,diagnostic_only=True,expected_regions=9,calibration_usable=False,hardware_source_association_verified=False,launch_authorization_receipt=grant,reviewed_ready_sha256=digest(out/'ready.json'),corpus_sha256=digest(out/'corpus.json'),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=WATCHDOG,foreground=True,driver_binary_unchanged=True))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(x.is_symlink()for x in p.parents if x!=out)}
 save_manifest(out,m);verify(out)
 from memory_observation_postrun_v2 import install
 post=install(out,digest(out/'run.json'),a.postrun_probe_build.resolve(),'sohumpc')
 return dict(status='prepared',regions=9,ELF_sha256=digest(elf),prepared_manifest_sha256=digest(out/'run.json'),postrun_plan_sha256=post['plan_sha256'],hardware_contacted=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--postrun-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
