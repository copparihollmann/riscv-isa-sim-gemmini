#!/usr/bin/env python3
"""Freeze an independently checked scalar BF16 batch for the managed lifecycle."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch_runner import digest, prepare, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from run_prepared import verify


def freeze(build, gates, acceptance, authorization, output, memory_probe):
    import yaml
    built = json.loads((build / 'build.json').read_text())
    corpus_path = build / 'corpus.json'
    corpus = json.loads(corpus_path.read_text())
    elf = build / 'probe.elf'
    if (built.get('schema') != 'iris.scalar_bf16_probe_build.v1' or built.get('status') != 'built'
            or digest(elf) != built['elf_sha256'] or digest(corpus_path) != built['corpus_sha256']
            or corpus.get('split_id') != 'iris-scalar-bf16-decoder-fit-v1'
            or corpus.get('regions') != 720 or len(corpus['cases']) != 240):
        raise ValueError('Exact built scalar BF16 corpus required')
    records = [json.loads((g / 'report.json').read_text()) for g in gates]
    admitted = json.loads(acceptance.read_text())
    if (len(records) != 2 or {r['seed'] for r in records} != {0, 17}
            or admitted.get('schema') != 'iris.scalar_bf16_acceptance.v1'
            or admitted.get('pass') is not True or admitted['elf_sha256'] != digest(elf)
            or len(admitted['negative_controls']) != 16
            or any(c['rejected'] is not True for c in admitted['negative_controls'])):
        raise ValueError('Both seeds and all adversarial controls required')
    if {(r['seed'], r['report_sha256']) for r in admitted['gates']} != {
            (r['seed'], digest(g / 'report.json')) for r, g in zip(records, gates)}:
        raise ValueError('Acceptance and functional gates disagree')
    identities = dict(built['input_sha256'])
    identities.update(admitted['input_sha256'])
    for gate, record in zip(gates, records):
        if (record.get('pass') is not True or record['elf_sha256'] != digest(elf)
                or record['corpus_sha256'] != digest(corpus_path) or record['proof']['regions'] != 720):
            raise ValueError('Exact positive functional ELF/corpus gate required')
        identities.update(record['input_sha256'])
        identities.update({str(gate / name): digest(gate / name) for name in ('report.json', 'stdout', 'stderr')})
    for name, expected in identities.items():
        if digest(name) != expected:
            raise ValueError('Gate/build evidence changed: ' + name)
    cases = [dict(id=c['case_id'], active_harts=[0, 1, 2],
                  expected_checksums_by_hart=[c['expected_checksums'][str(h)] for h in range(3)],
                  parent_case_id=c['parent_case_id'], trial_id=c['trial_id'],
                  suite='scalar_bf16_decode', region='kernel', corpus_split=corpus['split_id'])
             for c in corpus['cases']]
    validate_cases(cases, True)
    deploy = Path('/scratch/eygao/iris-cy/sims/firesim/deploy')
    manager, manifest = prepare(deploy, output, elf, cases, deploy / 'config_runtime.yaml',
        deploy / 'config_hwdb.yaml', ROOT / 'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT / 'build/firesim-observability-archived-driver-v3/report.json',
        profile_interval=1000000)
    if memory_probe is not None:
        from memory_observation import freeze as freeze_observer
        freeze_observer(memory_probe, output, manifest)
    add_observer(manager)
    watchdog = manager / 'iris_workload_watchdog.py'
    text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1:
        raise ValueError('Foreground watchdog changed')
    watchdog.write_text(text.replace('SECONDS=1500', 'SECONDS=180', 1))
    path = manager / 'config_runtime.yaml'
    runtime = yaml.safe_load(path.read_text())
    original = runtime['target_config'].get('plusarg_passthrough', '')
    if '+fesvr-step-size' in original or '+max-cycles' in original:
        raise ValueError('Conflicting manual loader/cycle bound')
    runtime['target_config']['plusarg_passthrough'] = (original + ' +fesvr-step-size=128').strip()
    path.write_text(yaml.safe_dump(runtime, sort_keys=False))
    receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Actual current user authorization receipt required')
    for name, source in [('launch-authorization.json', authorization), ('corpus.json', corpus_path),
                         ('acceptance.json', acceptance)]:
        (output / name).write_bytes(source.read_bytes())
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    checklist = {'schema': 'iris.scalar_bf16_capture_checklist.v1', 'frozen_before_launch': True,
        'purpose': 'Resolve actual three-hart scalar BF16 conversion decoder behavior against source absence.',
        'expected_regions': 720, 'trials': 5, 'harts_online': [0, 1, 2],
        'idle_policy': corpus['idle_policy'], 'heldout': False,
        'required': ['Raw stdout/stderr/UART and failures, all720 precise trap/FPR/FCSR/checksum/cycle/instret observations',
                     'All setup/lifecycle timings, heartbeat and available FASED CSV, exact runtime/HWDB/plusargs',
                     'Exact source/toolchain/ELF/driver/image identities and dirty patches',
                     'Owned cleanup, shared-lock release and verified archive outside job'],
        'unavailable_instrumentation': ['TracerV', 'AutoCounter', 'SynthPrint'],
        'remote_wall_watchdog_seconds': 180, 'foreground': True,
        'host_phase_timeout_seconds': 360, 'calibration_usable': False,
        'source_image_association_verified': False,
        'trap_value_policy': 'Retain raw mtval without assuming payload or image equivalence.'}
    (output / 'capture-checklist.json').write_text(json.dumps(checklist, indent=2) + '\n')
    paths = [Path(__file__).resolve(), ROOT / 'firesim/prepare_managed_campaign.py',
             ROOT / 'firesim/run_prepared.py', ROOT / 'firesim/analyze_campaign.py',
             ROOT / 'firesim/workload_watchdog.py', ROOT / 'firesim/managed_programming_tools.py',
             ROOT / 'firesim/setup_phase_observer.py', ROOT / 'benchmarks/scalar_bf16_probe/validate.py',
             ROOT / 'benchmarks/scalar_bf16_probe/acceptance.py', build / 'build.json', corpus_path,
             acceptance, authorization, ROOT / 'build/xilinx-tool-paths-v1.json',
             Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    manifest['input_sha256'].update(identities)
    manifest['input_sha256'].update({str(p): digest(p) for p in paths})
    snapshot_inputs(output, manifest['input_sha256'])
    manifest.update(require_regions=True, require_goldens=True, campaign_role='scalar_bf16_decoder_diagnostic',
        launch_authorization_receipt=receipt, corpus_sha256=digest(output / 'corpus.json'),
        timing_perturbed=True, baseline_timing_equivalent=False, calibration_usable=False,
        hardware_source_association_verified=False, prepared_manager_sha256=digest(manager / 'firesim'),
        prepared_runtime_sha256=digest(path), frozen_capture_checklist_sha256=digest(output / 'capture-checklist.json'),
        loader_override={'fesvr_step_size_target_cycles': 128, 'target_cycle_bound': None,
                         'remote_wall_watchdog_seconds': 180, 'foreground': True, 'driver_binary_unchanged': True})
    manifest['prepared_file_sha256'] = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name != 'run.json' and not p.is_symlink()
        and not any(parent.is_symlink() for parent in p.parents if parent != output)}
    save_manifest(output, manifest)
    verify(output)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--gate', type=Path, action='append', required=True)
    p.add_argument('--acceptance-report', type=Path, required=True)
    p.add_argument('--authorization-receipt', type=Path, required=True)
    p.add_argument('--memory-probe-build', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = freeze(a.build.resolve(), [g.resolve() for g in a.gate], a.acceptance_report.resolve(),
                    a.authorization_receipt.resolve(), a.output.resolve(),
                    a.memory_probe_build.resolve() if a.memory_probe_build else None)
    print(json.dumps({'status': result['status'], 'expected_regions': 720, 'hardware_contacted': False}))
