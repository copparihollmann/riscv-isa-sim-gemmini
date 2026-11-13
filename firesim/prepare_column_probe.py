#!/usr/bin/env python3
"""Prepare a managed observation of unknown column behavior, with known row controls."""
import argparse
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch_runner import digest, prepare, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from run_prepared import verify


def freeze(build, admission, authorization, output, memory_probe):
    import yaml
    built = json.loads((build/'build.json').read_text())
    corpus_path = build/'corpus.json'
    corpus = json.loads(corpus_path.read_text())
    admitted = json.loads(admission.read_text())
    elf = build/'probe.elf'
    if (built.get('schema') != 'iris.vme_column_probe_build.v1' or built.get('status') != 'built'
            or digest(elf) != built['elf_sha256'] or digest(corpus_path) != built['corpus_sha256']
            or corpus.get('split_id') != 'iris-vme-column-observation-fit-v1'
            or len(corpus['cases']) != 384 or corpus.get('column_observations') != 384):
        raise ValueError('Exact built column observation and independent row controls required')
    if (admitted.get('schema') != 'iris.vme_column_parser_admission.v1' or admitted.get('pass') is not True
            or admitted.get('admission_fixture_only') is not True
            or admitted.get('functional_positive_full_probe_claimed') is not False
            or admitted.get('native_full_probe_capability_refusal_verified') is not True
            or admitted['elf_sha256'] != digest(elf) or len(admitted['negative_controls']) != 16
            or any(row['rejected'] is not True for row in admitted['negative_controls'])):
        raise ValueError('Explicitly scoped parser controls and actual native refusal required')
    identities = dict(built['input_sha256'])
    identities.update(admitted['input_sha256'])
    for name, expected in identities.items():
        if digest(name) != expected:
            raise ValueError('Build/admission input changed: '+name)
    cases = [dict(id=c['case_id'], active_harts=[0,1],
        expected_checksums_by_hart=[c['expected_checksums']['0'],c['expected_checksums']['1'],0],
        parent_case_id=c['parent_case_id'], trial_id=c['trial_id'], suite='vme_column_probe',
        region='kernel', corpus_split=corpus['split_id']) for c in corpus['cases']]
    validate_cases(cases, True)
    fs = Path('/scratch/eygao/iris-cy/sims/firesim')
    deploy = fs/'deploy'
    manager, manifest = prepare(deploy,output,elf,cases,deploy/'config_runtime.yaml',deploy/'config_hwdb.yaml',
        ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json',profile_interval=1000000)
    if memory_probe is not None:
        from memory_observation import freeze as freeze_memory
        freeze_memory(memory_probe,output,manifest)
    add_observer(manager)
    watchdog = manager/'iris_workload_watchdog.py'
    text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1:
        raise ValueError('Foreground watchdog source changed')
    watchdog.write_text(text.replace('SECONDS=1500','SECONDS=180',1))
    path = manager/'config_runtime.yaml'
    runtime = yaml.safe_load(path.read_text())
    plusargs = runtime['target_config'].get('plusarg_passthrough','')
    if '+fesvr-step-size' in plusargs or '+max-cycles' in plusargs:
        raise ValueError('Conflicting manual loader/cycle bound')
    runtime['target_config']['plusarg_passthrough']=(plusargs+' +fesvr-step-size=128').strip()
    path.write_text(yaml.safe_dump(runtime,sort_keys=False))
    receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Actual current user authorization receipt required')
    for name,source in [('launch-authorization.json',authorization),('corpus.json',corpus_path),('parser-admission.json',admission)]:
        (output/name).write_bytes(source.read_bytes())
    (output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    checklist = {'schema':'iris.vme_column_capture_checklist.v1','frozen_before_launch':True,
        'purpose':'Measure unknown column encoding behavior; independently check initialized tile rows before/after every attempt.',
        'expected_regions':768,'additional_raw_column_observations':384,'trials':3,'harts_online':[0,1,2],
        'idle_policy':corpus['idle_policy'],'heldout':False,'column_golden_assumed':False,
        'native_full_probe':'Expected explicit unsupported-column model refusal; not a positive full-probe execution.',
        'admission_fixture_only':True,'parser_negative_controls':16,
        'required':['Raw stdout/stderr/UART, all768row checksums/cycles/instret,384raw32word column outcomes and precise traps if any',
                    'Full four-phase setup/transfer/programming/cleanup timing and owned external archive',
                    'Exact ELF/toolchain/driver/image/source/config/plusarg identities and dirty patches',
                    'Available heartbeat/FASED counters and frozen environment source files; no fabricated traces'],
        'unavailable_instrumentation':['TracerV','AutoCounter','SynthPrint'],
        'remote_wall_watchdog_seconds':180,'foreground':True,'calibration_usable':False,
        'source_image_association_verified':False}
    (output/'capture-checklist.json').write_text(json.dumps(checklist,indent=2)+'\n')
    # Source environment from its actual root. Capture its logs inside the job;
    # these paths are created only at execution, after preparation is frozen.
    launch = ['#!/usr/bin/env bash',
        'export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH',
        'cd '+shlex.quote(str(fs))+' || exit 1',
        'source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(output/'launch-environment.stdout'))+' 2> '+shlex.quote(str(output/'launch-environment.stderr')),
        'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),
            str(output),'--execute','--authorization-id',receipt['authorization']['authorization_id'],'--timeout','360'])]
    (output/'launch.sh').write_text('\n'.join(launch)+'\n')
    (output/'launch.sh').chmod(0o700)
    paths = [Path(__file__).resolve(),ROOT/'firesim/run_prepared.py',ROOT/'firesim/prepare_managed_campaign.py',
        ROOT/'firesim/workload_watchdog.py',ROOT/'firesim/managed_programming_tools.py',ROOT/'firesim/setup_phase_observer.py',
        ROOT/'firesim/analyze_campaign.py',ROOT/'benchmarks/vme_column_probe/console_validate.py',
        ROOT/'benchmarks/vme_column_probe/validate.py',ROOT/'benchmarks/vme_column_probe/cases.py',
        build/'build.json',corpus_path,admission,authorization,ROOT/'build/xilinx-tool-paths-v1.json',
        fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh',
        Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    manifest['input_sha256'].update(identities)
    manifest['input_sha256'].update({str(p):digest(p) for p in paths})
    snapshot_inputs(output,manifest['input_sha256'])
    manifest.update(require_regions=True,require_goldens=True,campaign_role='vme_column_observation_diagnostic',
        launch_authorization_receipt=receipt,corpus_sha256=digest(output/'corpus.json'),
        timing_perturbed=True,baseline_timing_equivalent=False,calibration_usable=False,
        hardware_source_association_verified=False,prepared_manager_sha256=digest(manager/'firesim'),
        prepared_runtime_sha256=digest(path),frozen_capture_checklist_sha256=digest(output/'capture-checklist.json'),
        unknown_column_outcome_is_observation_not_golden=True,
        native_full_positive_execution_claimed=False,
        environment_source_sha256={str(p):digest(p) for p in [fs/'sourceme-manager.sh',fs/'env.sh',fs.parent.parent/'env.sh']},
        loader_override={'fesvr_step_size_target_cycles':128,'target_cycle_bound':None,
            'remote_wall_watchdog_seconds':180,'foreground':True,'driver_binary_unchanged':True})
    manifest['prepared_file_sha256']={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name!='run.json' and not p.is_symlink()
        and not any(parent.is_symlink() for parent in p.parents if parent!=output)}
    save_manifest(output,manifest)
    verify(output)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--parser-admission',type=Path,required=True)
    p.add_argument('--authorization-receipt',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--memory-probe-build',type=Path)
    a=p.parse_args()
    r=freeze(a.build.resolve(),a.parser_admission.resolve(),a.authorization_receipt.resolve(),a.output.resolve(),
             a.memory_probe_build.resolve() if a.memory_probe_build else None)
    print(json.dumps({'status':r['status'],'known_row_regions':768,'column_observations':384,'hardware_contacted':False}))
