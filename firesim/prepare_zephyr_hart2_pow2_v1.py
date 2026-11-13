#!/usr/bin/env python3
"""Locally prepare the648word-checked SMP packet; root alone launches."""
import argparse,json,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from hart2_pow2_managed_protocol_v1 import cases as host_cases,validate_console,need
from batch_runner import prepare,digest,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify
ROLE='Zephyr_hart2_control_pow2_functional_v1';WATCHDOG=180;PHASE_TIMEOUT=360
ELF='d47bec0012e4beea0df17b8f1d1c0aa0dc53f07f2a2dc9e8ed0fd5b5bbb49430'
INDEPENDENT='f8b813fd2d7a99b442cde7c997760ab60e7285b0f4c160f75e9e94253ee62b55'
def merge(target,source):
 for name,h in source.items():
  p=Path(name);p=p if p.is_absolute()else ROOT/p;p=p.resolve();key=str(p)
  need(key not in target or target[key]==h,'Conflicting input '+key);need(digest(p)==h,'Changed input '+key);target[key]=h

def admit(folder,expected):
 b=Path(folder).resolve();need(digest(b/'ready.json')==expected,'Exact reviewed ready');r=json.loads((b/'ready.json').read_text());q=json.loads((b/'qualification.json').read_text())
 need(r['schema']=='iris.zephyr_hart2_pow2_ready.v1'and r['status']=='source_functional_qualified'and r['pass']is True,'Exact source-qualified epoch')
 need(q['schema']=='iris.zephyr_hart2_pow2_qualification.v2'and q['pass']is True and q['hardware_prepared']is False and q['calibration_authorized']is False,'Functional-only qualification')
 for k,n in [('required_regions',648),('dispatch_groups',486),('required_elements',181440),('training_eligible',456),('protected_validation',192)]:need(type(r[k])is int and r[k]==n,'Typed exact coverage '+k)
 need(r['qualification_sha256']==digest(b/'qualification.json')and r['elf_sha256']==q['ELF_sha256']==ELF,'Qualification/exactELF')
 elf=Path(r['elf']);need(digest(elf)==ELF and digest(r['corpus_path'])==r['corpus_sha256']and digest(r['split_path'])==r['split_sha256'],'Current compiled/corpus/split')
 review=q['independent_review'];need(review['sha256']==INDEPENDENT and digest(review['path'])==INDEPENDENT,'Separate full source/RTL/ELF review')
 ids={};merge(ids,q['input_sha256'])
 for name,h in q['input_sha256'].items():need(digest(b/'input-snapshot'/h[:2]/h)==h,'Standalone qualified input '+name)
 for run in q['functional_runs']:
  p=Path(run['results']);obj=json.loads(p.read_text());need(digest(p)==run['results_sha256']and obj['pass']is True and type(obj['exit_status'])is int,'Actual bound native proof')
  if run['mode']=='normal':need(validate_console((p.parent/'stdout').read_text())==obj['proof']and obj['exit_status']==0,'Strict actual normal word/protocol proof')
 cases=host_cases();validate_cases(cases,True);need(sum(len(c['active_harts'])for c in cases)==648,'Declared actual regions')
 for p in b.iterdir():
  if p.is_file():merge(ids,{str(p):digest(p)})
 corpus=json.loads(Path(r['corpus_path']).read_text());need(corpus['calibration_authorized']is False,'No fitting authorization')
 return r,q,corpus,cases,elf,ids

def freeze(a):
 import yaml
 b=a.qualification.resolve();out=a.output.resolve();r,q,corpus,cases,elf,ids=admit(b,a.expected_ready_sha256)
 if a.validate_only:return dict(status='admitted_locally',regions=648,full_elements=181440,hardware_contacted=False)
 auth=a.authorization_receipt.resolve();grant=json.loads(auth.read_text());need(grant['schema']=='iris.remote_user_launch_authorization_receipt.v1','Actual standing user receipt')
 fs=Path('/scratch/eygao/iris-cy/sims/firesim');d=fs/'deploy';manager,m=prepare(d,out,elf,cases,d/'config_runtime.yaml',d/'config_hwdb.yaml',ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
 from memory_observation import freeze as freeze_memory
 freeze_memory(a.memory_probe_build.resolve(),out,m);add_observer(manager)
 watchdog=manager/'iris_workload_watchdog.py';text=watchdog.read_text();need(text.count('SECONDS=1500')==1,'Reviewed watchdog source');watchdog.write_text(text.replace('SECONDS=1500','SECONDS=180',1))
 runtime=manager/'config_runtime.yaml';rt=yaml.safe_load(runtime.read_text());old=rt['target_config'].get('plusarg_passthrough','');need('+max-cycles'not in old and'+fesvr-step-size'not in old,'No target bound or conflicting loader override');rt['target_config']['plusarg_passthrough']=(old+' +fesvr-step-size=128').strip();runtime.write_text(yaml.safe_dump(rt,sort_keys=False))
 for p in b.iterdir():
  if p.is_file():(out/p.name).write_bytes(p.read_bytes())
 (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(out/'split.json').write_bytes(Path(r['split_path']).read_bytes());(out/'layout.json').write_bytes(Path(q['actual_ELF_layout']['path']).read_bytes());(out/'launch-authorization.json').write_bytes(auth.read_bytes())
 check=dict(schema='iris.Zephyr_hart2_pow2_capture_checklist.v1',frozen_before_launch=True,functional_only=True,calibration_usable=False,regions=648,dispatch_groups=486,full_active_elements=181440,guard_regions=648,full_little_endian_data_capture_required=True,training_eligible=456,protected_validation=192,performance_labels_sealed_until_root_prediction_freeze=True,worker_harts=[0,1],controller_hart=2,worker_masks=[1,2,3],hart2_application_FP_vector=False,wall_watchdog_seconds=180,phase_timeout_seconds=360,target_max_cycles=None,loader_quantum=128,normal_completion='All648actualIRIS_REGION+all181440wordchecks+648guards, allIRIS_DATA chunks, scalarh2READY/DONE+exactBATCH_DONE, exactsource-boundscriptheader/command/exit0; normalHTIF+fullfourphases+cleanup/capture',console_scope='Startup readiness precedes ROIs; ALL result/data output follows ALL measurements. Failure before emit may have no ROI output; preserve rawprefix/timeout without fabricating rows.',source_FENCE_scope='Requested rw,rw source predicate; not a pure-unit or absolute backend/memory completion certificate',mask3_scope='Real peers and hart2 controller memory/other-worker readout may contend; no isolated-unit throughput claim',timing_scope='PerhartMCYCLE windows, rawMINSTRET differences; no crosshart global alignment/clock/memory-latency/2percent certificate',no_target_cycle_bound_reason='Original atoi32 maxcycles parser and successful loader >5Bglobaldrivercycles; use hostforegroundwallbound',required=['fresh current user authorization/boot/alluser/device inspection and sharedlock before EACH phase','managed kill,infrasetup,runworkload,ownedkill including failure cleanup','full rawmanager/UART/autocounters/FASED/artifact/source archive','original driver/image exact source identities; preinit and optional postdriver5config observation separated from guest outcome'])
 (out/'capture-checklist.json').write_text(json.dumps(check,indent=2)+'\n')
 launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1','source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(out/'launch-environment.stdout'))+' 2> '+shlex.quote(str(out/'launch-environment.stderr')),'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(out),'--execute','--authorization-id',grant['authorization']['authorization_id'],'--timeout','360'])];(out/'launch.sh').write_text('\n'.join(launch)+'\n');(out/'launch.sh').chmod(0o700)
 env=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh'];sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_zephyr_hart2_pow2_v1.py',ROOT/'firesim/test_zephyr_hart2_pow2_v1.py',ROOT/'zephyr/hart2_pow2_managed_protocol_v1.py',ROOT/'zephyr/hart2_pow2_validate_v4.py',ROOT/'zephyr/hart2_pow2_run_v4.py',ROOT/'zephyr/hart2_pow2_qualify_v2.py',ROOT/'zephyr/hart2_pow2_layout_v1.py',ROOT/'zephyr/script_envelope_v3.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/complete_input_snapshots_v1.py',ROOT/'build/prepared-input-snapshot-completion-controls-v1/report.json',ROOT/'build/zephyr-hart2-pow2-managed-tests-v1/report.json',ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/setup_phase_observer.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'build/xilinx-tool-paths-v1.json',ROOT/'AGENTS.md',ROOT/'firesim/OPERATING_RULES.md',ROOT/'firesim/CAMPAIGN_POLICY.md',auth,*env]
 merge(ids,{str(p):digest(p)for p in sources});merge(m['input_sha256'],ids);snapshot_inputs(out,m['input_sha256'])
 m.update(require_regions=True,require_goldens=True,campaign_role=ROLE,functional_only=True,expected_regions=648,required_elements=181440,calibration_usable=False,hardware_source_association_verified=False,training_eligible=456,protected_validation=192,seal_timing_labels=True,launch_authorization_receipt=grant,reviewed_ready_sha256=digest(out/'ready.json'),corpus_sha256=digest(out/'corpus.json'),frozen_capture_checklist_sha256=digest(out/'capture-checklist.json'),prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime),environment_source_sha256={str(p):digest(p)for p in env},loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,remote_wall_watchdog_seconds=180,foreground=True,driver_binary_unchanged=True))
 m['prepared_file_sha256']={str(p.relative_to(out)):digest(p)for p in sorted(out.rglob('*'))if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(x.is_symlink()for x in p.parents if x!=out)};save_manifest(out,m);verify(out)
 from memory_observation_postrun_v2 import install
 post=install(out,digest(out/'run.json'),a.postrun_probe_build.resolve(),'sohumpc')
 command=[sys.executable,str(ROOT/'firesim/complete_input_snapshots_v1.py'),str(out),'--expected-prepared-manifest-sha256',digest(out/'run.json')];done=subprocess.run(command,capture_output=True,text=True);need(done.returncode==0,'Final snapshotcompletion: '+done.stderr);completion=json.loads(done.stdout);verify(out)
 return dict(status='prepared',regions=648,full_elements=181440,ELF_sha256=ELF,prepared_manifest_sha256=digest(out/'run.json'),postrun_plan_sha256=post['plan_sha256'],final_input_snapshots=completion,hardware_contacted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--expected-ready-sha256',required=True);p.add_argument('--authorization-receipt',type=Path,required=True);p.add_argument('--memory-probe-build',type=Path,required=True);p.add_argument('--postrun-probe-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();print(json.dumps(freeze(a)))
