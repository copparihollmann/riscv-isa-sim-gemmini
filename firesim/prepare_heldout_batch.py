#!/usr/bin/env python3
"""Prepare the frozen v6 Zephyr heldout using the managed lifecycle; never launch."""
import argparse,json,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'zephyr'))
from batch_runner import digest,prepare,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from run_prepared import verify

V6='987e0b3c4e8c3f45c1549501edee6a7f1e6ba1b73f7289cb4fc877a1460e3ed2'
ELF='da2de5ef01d7030741058859162fb6286fa73baf8816ab1365bdfe3ea6785cd4'

def admit(batch,gates,controls,prediction,prediction_sha,binding):
    mp=batch/'manifest.json';m=json.loads(mp.read_text())
    if digest(mp)!=V6 or m.get('ELF_sha256')!=ELF or m.get('fitting_allowed')is not False or not m.get('global_elapsed_source')or not m.get('compact_output'):
        raise ValueError('Exact frozen independent v6 compact workload required')
    if digest(batch/'cases.json')!=m['cases_sha256']or digest(batch/'golden.json')!=m['golden_sha256']:
        raise ValueError('Declared cases or independent goldens changed')
    identities={str(mp):V6,str(batch/'cases.json'):digest(batch/'cases.json'),str(batch/'golden.json'):digest(batch/'golden.json')}
    for original,item in m['inputs'].items():
        path=batch/item['object']
        if digest(path)!=item['sha256']:raise ValueError('Frozen input changed '+original)
        identities[str(path)]=item['sha256']
    elf=Path(m['ELF'])
    if digest(elf)!=ELF:raise ValueError('Actual v6 compact ELF changed')
    cases=json.loads((batch/'cases.json').read_text());validate_cases(cases,True)
    if len(cases)!=128 or sum(len(x['active_harts'])for x in cases)!=188:raise ValueError('Complete128cases/188regions required')
    records=[json.loads((g/'report.json').read_text())for g in gates]
    if len(records)!=2 or {x.get('seed')for x in records}!={0,17}:raise ValueError('Both functional0/17 gates required')
    for directory,r in zip(gates,records):
        if r.get('pass')is not True or r.get('ELF_sha256')!=ELF or r.get('workload_manifest_sha256')!=V6 or r.get('timing_kind')!='functional' or len(r.get('regions',[]))!=188 or len(r.get('global_elapsed_windows',[]))!=8 or r.get('full_output_elements')!=491520:
            raise ValueError('Exact successful functional v6 checks required')
        identities.update(r['input_sha256'])
        for name in ['report.json','stdout','stderr']:identities[str(directory/name)]=digest(directory/name)
    c=json.loads(controls.read_text())
    if c.get('pass')is not True or len(c.get('parser_corruption_controls',[]))!=16 or any(x.get('rejected')is not True for x in c['parser_corruption_controls'])or c.get('real_omitted_kernel',{}).get('rejected')is not True:
        raise ValueError('Compiled-body/numerical-omission/adversarial controls required')
    if c.get('input_sha256',{}).get(str(mp))!=V6 or c.get('input_sha256',{}).get(str(elf))!=ELF:
        raise ValueError('Acceptance controls belong to another workload')
    identities.update(c['input_sha256']);identities[str(controls)]=digest(controls)
    pred=json.loads(prediction.read_text())
    if digest(prediction)!=prediction_sha or pred.get('pass')is not True or pred.get('timing_kind')!='experimental-empirical' or pred.get('ELF_sha256')!=ELF or pred.get('workload_manifest_sha256')!=V6 or len(pred.get('regions',[]))!=188 or len(pred.get('global_elapsed_windows',[]))!=8:
        raise ValueError('Exact complete experimental prediction must be frozen before reference timing')
    if pred.get('fitting_allowed')is not False:raise ValueError('Heldout prediction may not be fitting input')
    if pred['input_sha256'].get(str(binding))!=digest(binding):raise ValueError('Prediction does not bind selected runtime envelope')
    identities.update(pred['input_sha256']);identities[str(prediction)]=prediction_sha;identities[str(binding)]=digest(binding)
    for relative,h in pred.get('artifact_sha256',{}).items():
        path=(prediction.parent/relative).resolve()
        if prediction.parent not in path.parents or digest(path)!=h:raise ValueError('Frozen model output changed or escaped')
        identities[str(path)]=h
    for name,h in identities.items():
        if digest(name)!=h:raise ValueError('Admission input changed '+name)
    return m,cases,elf,identities

def freeze(a):
    import yaml
    batch=a.batch.resolve();gates=[g.resolve()for g in a.gate];controls=a.controls.resolve();prediction=a.prediction.resolve();binding=a.runtime_binding.resolve()
    m,cases,elf,identities=admit(batch,gates,controls,prediction,a.expected_prediction_sha256,binding)
    output=a.output.resolve();authorization=a.authorization_receipt.resolve();receipt=json.loads(authorization.read_text())
    if receipt.get('schema')!='iris.remote_user_launch_authorization_receipt.v1':raise ValueError('Actual standing-user authorization receipt required')
    if a.validate_only:return {'status':'local_admission_validated_no_job_or_hardware','expected_regions':188,'hardware_contacted':False}
    fs=Path('/scratch/eygao/iris-cy/sims/firesim');deploy=fs/'deploy'
    manager,manifest=prepare(deploy,output,elf,cases,deploy/'config_runtime.yaml',deploy/'config_hwdb.yaml',
        ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
    if a.memory_probe_build:
        from memory_observation import freeze as freeze_memory
        freeze_memory(a.memory_probe_build.resolve(),output,manifest)
    add_observer(manager)
    watchdog=manager/'iris_workload_watchdog.py';text=watchdog.read_text()
    if text.count('SECONDS=1500')!=1:raise ValueError('Reviewed foreground watchdog changed')
    watchdog.write_text(text.replace('SECONDS=1500','SECONDS='+str(a.workload_timeout),1))
    runtime_path=manager/'config_runtime.yaml';runtime=yaml.safe_load(runtime_path.read_text());original=runtime['target_config'].get('plusarg_passthrough','')
    if '+fesvr-step-size'in original or '+max-cycles'in original:raise ValueError('Conflicting loader/cycle bound')
    runtime['target_config']['plusarg_passthrough']=(original+' +fesvr-step-size=128').strip();runtime_path.write_text(yaml.safe_dump(runtime,sort_keys=False))
    copies={'launch-authorization.json':authorization,'corpus.json':batch/'manifest.json','cases.json':batch/'cases.json',
        'golden.json':batch/'golden.json','prediction.json':prediction,'runtime-binding.json':binding,'acceptance-controls.json':controls}
    for name,path in copies.items():(output/name).write_bytes(path.read_bytes())
    for name,key in [('model-summary.json','native_summary_sha256'),('model-prefix.jsonl','feature_prefix_sha256')]:
        source=prediction.parent/('native-summary.json'if name.endswith('.json')else'features.jsonl')
        if digest(source)!=json.loads(prediction.read_text())[key]:raise ValueError('Frozen model profile output changed')
        (output/name).write_bytes(source.read_bytes())
    checklist={'schema':'iris.independent_heldout_Zephyr_batch_capture_checklist.v1','frozen_before_launch':True,
        'heldout':True,'fitting_allowed':False,'workload_manifest_sha256':V6,'ELF_sha256':ELF,
        'prediction_sha256':a.expected_prediction_sha256,'runtime_binding_sha256':digest(binding),
        'expected_regions':188,'unique_cases':128,'phases':8,'global_elapsed_windows':8,'trials':5,'datasets':3,
        'harts_online':[0,1,2],'matrix_harts':[0,1],'hart2_role':'Pinned RVV producer, VME refusal, separate globalCLINT data samples',
        'full_INT32_output_words_checked':491520,'full_W8A8_output_words_checked':491520,'console_mode':'Onebyteflagcompact; fullindependentwordchecks outsideROI',
        'required':['All188rawmcycle/minstret/checksums and8CLINT500kHzglobalwindows, all120numericalhashrecords',
            'RawUART/managerstdout/stderr/heartbeats/availableFASEDCSV onbothsuccessandfailure',
            'Fourmanagedphases,completeownershipchecks/sharedlock/ownedcleanup/externalarchive',
            'ExactELF/source/toolchains/independentgoldens/image/driver/runtime/HWDB/parameterenvelope/frozenprediction'],
        'unavailable_instrumentation':['TracerV','AutoCounter','SynthPrint'],'remote_wall_watchdog_seconds':a.workload_timeout,
        'host_phase_timeout_seconds':a.workload_timeout+180,'source_image_association_verified':False,'timing_certified':False,
        'known_exclusions':'Original25regionZephyr/hart2 and1174regionpage-store failures remainknown; thisELF doesnotcertifythem.'}
    (output/'capture-checklist.json').write_text(json.dumps(checklist,indent=2)+'\n')
    env_paths=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh']
    launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH','cd '+shlex.quote(str(fs))+' || exit 1',
        'source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(output/'launch-environment.stdout'))+' 2> '+shlex.quote(str(output/'launch-environment.stderr')),
        'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(output),'--execute',
            '--authorization-id',receipt['authorization']['authorization_id'],'--timeout',str(a.workload_timeout+180)])]
    (output/'launch.sh').write_text('\n'.join(launch)+'\n');(output/'launch.sh').chmod(0o700)
    sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_heldout_batch.py',ROOT/'firesim/analyze_campaign.py',
        ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/run_prepared.py',ROOT/'firesim/workload_watchdog.py',
        ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',ROOT/'zephyr/heldout_batch_run.py',
        ROOT/'zephyr/heldout_batch_compare.py',ROOT/'zephyr/uart_profiles.py',ROOT/'zephyr/compiler_pipeline.py',
        ROOT/'zephyr/freeze_heldouts.py',authorization,*env_paths,ROOT/'build/xilinx-tool-paths-v1.json',
        Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    identities.update({str(path):digest(path)for path in sources});manifest['input_sha256'].update(identities)
    snapshot_inputs(output,manifest['input_sha256'])
    manifest.update(require_regions=True,require_goldens=True,campaign_role='independent_heldout_zephyr_Merlin_batch_v6',
        launch_authorization_receipt=receipt,corpus_sha256=V6,frozen_prediction_sha256=a.expected_prediction_sha256,
        runtime_binding_sha256=digest(binding),fitting_allowed=False,calibration_usable=False,timing_accuracy_certified=False,
        hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),prepared_runtime_sha256=digest(runtime_path),
        frozen_capture_checklist_sha256=digest(output/'capture-checklist.json'),environment_source_sha256={str(p):digest(p)for p in env_paths},
        loader_override={'fesvr_step_size_target_cycles':128,'target_cycle_bound':None,'remote_wall_watchdog_seconds':a.workload_timeout,
            'foreground':True,'driver_binary_unchanged':True})
    manifest['prepared_file_sha256']={str(p.relative_to(output)):digest(p)for p in sorted(output.rglob('*'))
        if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(parent.is_symlink()for parent in p.parents if parent!=output)}
    save_manifest(output,manifest);verify(output)
    return {'status':manifest['status'],'expected_regions':188,'hardware_contacted':False,'job':str(output)}

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--batch',type=Path,default=ROOT/'build/fast-heldout-zephyr-compact-v6')
    p.add_argument('--gate',type=Path,action='append',required=True);p.add_argument('--controls',type=Path,required=True)
    p.add_argument('--prediction',type=Path,required=True);p.add_argument('--expected-prediction-sha256',required=True)
    p.add_argument('--runtime-binding',type=Path,required=True);p.add_argument('--authorization-receipt',type=Path,required=True)
    p.add_argument('--memory-probe-build',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workload-timeout',type=int,default=1200);p.add_argument('--validate-only',action='store_true')
    a=p.parse_args()
    if not 180<=a.workload_timeout<=1500:p.error('Explicit bounded watchdog180..1500seconds required')
    print(json.dumps(freeze(a)))
