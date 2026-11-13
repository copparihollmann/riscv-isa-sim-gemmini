#!/usr/bin/env python3
"""Freeze both emitted compiler kernels, three repetitions and all three harts."""
import argparse
import json
from pathlib import Path
import shlex
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from batch_runner import digest, prepare, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from run_prepared import verify


def freeze(build,gates,acceptance,authorization,output,memory_probe):
    import yaml
    built=json.loads((build/'build.json').read_text())
    corpus_path=build/'corpus.json'; corpus=json.loads(corpus_path.read_text())
    elf=build/'combined.elf'
    if (built.get('schema')!='iris.compiler_i8_wrap_build.v1' or built.get('status')!='built'
            or built.get('deliberate_noop_negative_control')is not False
            or digest(elf)!=built['binaries']['combined']['sha256']
            or digest(corpus_path)!=built['corpus_sha256']
            or corpus.get('split_id')!='iris-compiler-i8-wrapping-functional-v1'
            or len(corpus['cases'])!=7 or corpus.get('calibration_usable')is not False):
        raise ValueError('Exact independent compiler wrapping corpus and combined ELF required')
    records=[json.loads((g/'report.json').read_text())for g in gates]
    admitted=json.loads(acceptance.read_text())
    if (len(records)!=2 or {r['seed']for r in records}!={0,17}
            or admitted.get('schema')!='iris.compiler_i8_wrap_acceptance.v1'
            or admitted.get('pass')is not True or admitted['elf_sha256']!=digest(elf)
            or admitted.get('fresh_output_noop_control',{}).get('pass')is not True
            or admitted['fresh_output_noop_control'].get('failed_compute_words')!=63984
            or len(admitted['negative_controls'])!=19
            or any(c['rejected']is not True for c in admitted['negative_controls'])):
        raise ValueError('Both seeded executions and every adversarial control required')
    if {(r['seed'],r['report_sha256'])for r in admitted['gates']}!={
            (r['seed'],digest(g/'report.json'))for r,g in zip(records,gates)}:
        raise ValueError('Acceptance and functional gates disagree')
    identities=dict(built['input_sha256']); identities.update(admitted['input_sha256'])
    for gate,record in zip(gates,records):
        if (record.get('pass')is not True or record.get('variant')!='combined'
                or record['elf_sha256']!=digest(elf) or record['corpus_sha256']!=digest(corpus_path)
                or record['proof']['regions']!=126 or record['proof']['trials']!=3):
            raise ValueError('Exact combined kernel/twin functional execution required')
        identities.update(record['input_sha256'])
        identities.update({str(gate/name):digest(gate/name)for name in ('report.json','stdout','stderr')})
    for name,expected in identities.items():
        if digest(name)!=expected:raise ValueError('Build/gate source changed: '+name)
    cases=[]
    for trial in range(3):
        for variant in ('vme','twin'):
            for c in corpus['cases']:
                parent=c['case_id']+'.variant-'+variant
                cases.append(dict(id=parent+'.trial'+str(trial),active_harts=[0,1,2],
                    expected_checksums_by_hart=[c['expected_checksums'][str(h)]for h in range(3)],
                    parent_case_id=parent,trial_id=trial,suite='compiler_i8_wrap',region='kernel',
                    corpus_split=corpus['split_id']))
    validate_cases(cases,True)
    fs=Path('/scratch/eygao/iris-cy/sims/firesim'); deploy=fs/'deploy'
    manager,manifest=prepare(deploy,output,elf,cases,deploy/'config_runtime.yaml',deploy/'config_hwdb.yaml',
        ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
    if memory_probe is not None:
        from memory_observation import freeze as freeze_memory
        freeze_memory(memory_probe,output,manifest)
    add_observer(manager)
    watchdog=manager/'iris_workload_watchdog.py'; text=watchdog.read_text()
    if text.count('SECONDS=1500')!=1:raise ValueError('Foreground watchdog changed')
    watchdog.write_text(text.replace('SECONDS=1500','SECONDS=180',1))
    path=manager/'config_runtime.yaml'; runtime=yaml.safe_load(path.read_text())
    original=runtime['target_config'].get('plusarg_passthrough','')
    if '+fesvr-step-size'in original or '+max-cycles'in original:raise ValueError('Conflicting loader/cycle bound')
    runtime['target_config']['plusarg_passthrough']=(original+' +fesvr-step-size=128').strip()
    path.write_text(yaml.safe_dump(runtime,sort_keys=False))
    receipt=json.loads(authorization.read_text())
    if receipt.get('schema')!='iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Actual standing-user authorization receipt required')
    for name,source in [('launch-authorization.json',authorization),('corpus.json',corpus_path),('acceptance.json',acceptance)]:
        (output/name).write_bytes(source.read_bytes())
    (output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    checklist={'schema':'iris.compiler_i8_wrap_capture_checklist.v1','frozen_before_launch':True,
        'purpose':'Cross-check actual emitted VME and corrected scalar twin modulo32 outputs against independent Python integer goldens.',
        'expected_regions':126,'unique_cases':7,'variants':['vme','twin'],'trials':3,'harts_online':[0,1,2],
        'matrix_harts':[0,1],'hart2_role':corpus['hart2_role'],'heldout':False,
        'full_word_checks':64152,'parser_negative_controls':19,
        'every_output_freshly_poisoned_before_every_invocation':True,
        'actual_deliberate_noop_negative_control':admitted['fresh_output_noop_control'],
        'required':['Raw manager stdout/stderr/UART and every failure; all126region cycles/minstret/checksums/failed-word counts',
            'Exact independent per-word goldens embedded in guest; guest compares all64152words, host independently checks every region checksum',
            'Four managed phase timings, transfer/programming observer, owned cleanup/shared-lock release and external archive',
            'Exact source patches/toolchain/ELF/image/driver/runtime/HWDB/plusargs/environment sources',
            'Available heartbeat and aggregate FASED CSV; no invented per-hart memory attribution'],
        'unavailable_instrumentation':['TracerV','AutoCounter','SynthPrint'],
        'remote_wall_watchdog_seconds':180,'host_phase_timeout_seconds':360,'foreground':True,
        'calibration_usable':False,'full_functional_certified':False,'source_image_association_verified':False}
    (output/'capture-checklist.json').write_text(json.dumps(checklist,indent=2)+'\n')
    launch=['#!/usr/bin/env bash','export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH',
        'cd '+shlex.quote(str(fs))+' || exit 1',
        'source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(output/'launch-environment.stdout'))
            +' 2> '+shlex.quote(str(output/'launch-environment.stderr')),
        'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),
            str(output),'--execute','--authorization-id',receipt['authorization']['authorization_id'],'--timeout','360'])]
    (output/'launch.sh').write_text('\n'.join(launch)+'\n');(output/'launch.sh').chmod(0o700)
    env_paths=[fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh']
    paths=[Path(__file__).resolve(),ROOT/'firesim/analyze_i8_wrap.py',ROOT/'firesim/run_prepared.py',
        ROOT/'firesim/prepare_managed_campaign.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/workload_watchdog.py',
        ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',
        ROOT/'benchmarks/compiler_i8_wrap/acceptance.py',ROOT/'benchmarks/compiler_i8_wrap/validate.py',
        ROOT/'benchmarks/compiler_i8_wrap/cases.py',build/'build.json',corpus_path,acceptance,authorization,
        ROOT/'integration/iris-mlir/provenance.json',ROOT/'integration/iris-mlir/README.md',
        ROOT/'build/xilinx-tool-paths-v1.json',*env_paths,
        Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    manifest['input_sha256'].update(identities);manifest['input_sha256'].update({str(p):digest(p)for p in paths})
    snapshot_inputs(output,manifest['input_sha256'])
    manifest.update(require_regions=True,require_goldens=True,campaign_role='compiler_i8_wrapping_functional',
        launch_authorization_receipt=receipt,corpus_sha256=digest(output/'corpus.json'),
        timing_perturbed=True,baseline_timing_equivalent=False,calibration_usable=False,
        hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),
        prepared_runtime_sha256=digest(path),frozen_capture_checklist_sha256=digest(output/'capture-checklist.json'),
        environment_source_sha256={str(p):digest(p)for p in env_paths},
        loader_override={'fesvr_step_size_target_cycles':128,'target_cycle_bound':None,
            'remote_wall_watchdog_seconds':180,'foreground':True,'driver_binary_unchanged':True})
    manifest['prepared_file_sha256']={str(p.relative_to(output)):digest(p)for p in sorted(output.rglob('*'))
        if p.is_file()and p.name!='run.json'and not p.is_symlink()
        and not any(parent.is_symlink()for parent in p.parents if parent!=output)}
    save_manifest(output,manifest);verify(output)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--gate',type=Path,action='append',required=True)
    p.add_argument('--acceptance-report',type=Path,required=True);p.add_argument('--authorization-receipt',type=Path,required=True)
    p.add_argument('--memory-probe-build',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=freeze(a.build.resolve(),[g.resolve()for g in a.gate],a.acceptance_report.resolve(),
        a.authorization_receipt.resolve(),a.output.resolve(),a.memory_probe_build.resolve()if a.memory_probe_build else None)
    print(json.dumps({'status':result['status'],'expected_regions':126,'hardware_contacted':False}))
