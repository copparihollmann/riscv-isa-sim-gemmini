#!/usr/bin/env python3
"""Freeze the independently qualified, disjoint Zephyr FPGA training batch."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch_runner import prepare, digest, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from run_prepared import verify


def freeze(build, gates, output, authorization, diagnostic=None, memory_probe_build=None):
    import yaml
    proof = json.loads((build / 'build.json').read_text())
    corpus = json.loads((gates[0] / 'corpus.json').read_text())
    elf = build / 'zephyr/zephyr.elf'
    if proof['status'] != 'built' or digest(elf) != proof['elf_sha256']:
        raise ValueError('Exact successful build required')
    if corpus.get('split_id') != 'iris-zephyr-fpga-fit-v1':
        raise ValueError('Disjoint Zephyr fitting corpus required')
    for gate in gates:
        row = json.loads((gate / 'report.json').read_text())
        if row.get('pass') is not True or row['elf_sha256'] != digest(elf) or row['corpus_sha256'] != digest(gates[0] / 'corpus.json'):
            raise ValueError('Both independent functional seeds must pass on exact ELF/corpus')
        for path, expected in row['input_sha256'].items():
            if digest(path) != expected:
                raise ValueError('Functional proof input changed: ' + path)
    if {json.loads((g / 'report.json').read_text())['seed'] for g in gates} != {0, 17}:
        raise ValueError('Both deterministic schedule seed0/17 proofs required')
    diagnostic_record = None
    if diagnostic is not None:
        diagnostic_record = json.loads(diagnostic.read_text())
        if (diagnostic_record.get('schema') != 'iris.zephyr_hart2_diagnostic_ready.v1'
                or diagnostic_record.get('elf_sha256') != digest(elf)
                or diagnostic_record.get('build_receipt_sha256') != digest(build / 'build.json')
                or diagnostic_record.get('timing_perturbed') is not True
                or diagnostic_record.get('baseline_timing_equivalent') is not False):
            raise ValueError('Exact explicitly perturbed diagnostic receipt required')
        for gate in diagnostic_record['gates']:
            if digest(gate['path']) != gate['sha256']:
                raise ValueError('Diagnostic functional gate changed')
    cases = [dict(id=c['case_id'], active_harts=[h for h in range(3) if c['mask'] & (1 << h)],
                  expected_checksums_by_hart=c['expected_checksums'], region=c['region'],
                  parent_case_id=c['parent_case_id'], trial_id=c['trial_id'], suite=c['suite'],
                  workload_mask=c['workload_mask'], corpus_split=corpus['split_id']) for c in corpus['cases']]
    validate_cases(cases, True)
    deploy = Path('/scratch/eygao/iris-cy/sims/firesim/deploy')
    audit = ROOT / 'build/firesim-observability-archived-driver-v3/report.json'
    driver = ROOT / 'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz'
    manager, manifest = prepare(deploy, output, elf, cases, deploy / 'config_runtime.yaml',
                                deploy / 'config_hwdb.yaml', driver, observability_report=audit,
                                profile_interval=1000000)
    if memory_probe_build is not None:
        from memory_observation import freeze as freeze_memory_observer
        freeze_memory_observer(memory_probe_build, output, manifest)
    add_observer(manager)
    watchdog = manager / 'iris_workload_watchdog.py'
    text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1:
        raise ValueError('Wall watchdog parameter contract changed')
    watchdog.write_text(text.replace('SECONDS=1500', 'SECONDS=180', 1))
    runtime_path = manager / 'config_runtime.yaml'
    runtime = yaml.safe_load(runtime_path.read_text())
    original = runtime['target_config'].get('plusarg_passthrough', '')
    if '+fesvr-step-size' in original or '+max-cycles' in original:
        raise ValueError('Conflicting manual loader/cycle bound')
    runtime['target_config']['plusarg_passthrough'] = (original + ' +fesvr-step-size=128').strip()
    runtime_path.write_text(yaml.safe_dump(runtime, sort_keys=False))
    receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Current user launch receipt required')
    (output / 'launch-authorization.json').write_bytes(authorization.read_bytes())
    (output / 'corpus.json').write_bytes((gates[0] / 'corpus.json').read_bytes())
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    checklist = {'schema': 'iris.zephyr_fit_capture_checklist.v1', 'frozen_before_launch': True,
                 'split': corpus['split_id'], 'heldout': False, 'expected_regions': 285,
                 'cases': 210, 'trials': 5, 'phase_markers': 10, 'harts_online': [0, 1, 2],
                 'idle_policy': corpus['idle_policy'], 'dispatch_scope': corpus['dispatch_region'],
                 'required': ['All raw manager/stdout/stderr/UART including failures',
                              'Every region mcycle/minstret/checksum and CLINT mtime bracket',
                              'UART DIV profile readback and final completion',
                              'All five repetitions and seven workload masks; hart roles',
                              'Actual runtime/HWDB/plusargs, source/toolchain/ELF/image/driver identities',
                              'Per-phase host timing, heartbeat and available FASED counters'],
                 'observability_audit_sha256': digest(audit), 'wall_watchdog_seconds': 180,
                 'wall_watchdog_foreground': True, 'host_phase_timeout_seconds': 360,
                 'no_clock_or_memory_parameter_override': True, 'calibration_usable': False}
    if diagnostic_record is not None:
        checklist.update(purpose='Hart2 Zephyr vector-context hypothesis test', timing_perturbed=True,
                         baseline_timing_equivalent=False, diagnostic_variant=diagnostic_record['variant'],
                         breadcrumbs=diagnostic_record['breadcrumbs'],
                         required_diagnostic_capture='All kernel/app stage breadcrumbs and pinned observer output; include partial last stage on timeout')
    if memory_probe_build is not None:
        checklist['readonly_memory_observation'] = manifest['readonly_memory_observation']
    (output / 'capture-checklist.json').write_text(json.dumps(checklist, indent=2) + '\n')
    paths = [Path(__file__).resolve(), ROOT / 'firesim/prepare_managed_campaign.py',
             ROOT / 'firesim/analyze_campaign.py', ROOT / 'firesim/run_prepared.py',
             ROOT / 'firesim/managed_programming_tools.py', ROOT / 'firesim/setup_phase_observer.py',
             ROOT / 'firesim/workload_watchdog.py', ROOT / 'zephyr/firesim_fit.py',
             ROOT / 'zephyr/firesim_fit_validate.py', build / 'build.json', authorization,
             ROOT / 'build/xilinx-tool-paths-v1.json',
             Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    if diagnostic is not None:
        paths.append(diagnostic)
    manifest['input_sha256'].update({str(ROOT / name): value for name, value in proof['input_sha256'].items()})
    for gate in gates:
        row = json.loads((gate / 'report.json').read_text())
        manifest['input_sha256'].update(row['input_sha256'])
        paths += [gate / name for name in ('report.json', 'corpus.json', 'stdout', 'stderr')]
    manifest['input_sha256'].update({str(path): digest(path) for path in paths})
    snapshot_inputs(output, manifest['input_sha256'])
    manifest.update(require_regions=True, require_goldens=True, campaign_role='zephyr_fitting',
                    launch_authorization_receipt=receipt, corpus_sha256=digest(output / 'corpus.json'),
                    hardware_source_association_verified=False, calibration_usable=False,
                    frozen_capture_checklist_sha256=digest(output / 'capture-checklist.json'),
                    prepared_manager_sha256=digest(manager / 'firesim'),
                    prepared_runtime_sha256=digest(runtime_path),
                    loader_override={'fesvr_step_size_target_cycles': 128, 'target_cycle_bound': None,
                                     'remote_wall_watchdog_seconds': 180, 'foreground': True,
                                     'driver_binary_unchanged': True})
    if diagnostic_record is not None:
        manifest.update(campaign_role='zephyr_diagnostic', timing_perturbed=True,
                        baseline_timing_equivalent=False, diagnostic_variant=diagnostic_record['variant'],
                        diagnostic_receipt_sha256=digest(diagnostic))
    manifest['prepared_file_sha256'] = {str(path.relative_to(output)): digest(path)
        for path in sorted(output.rglob('*')) if path.is_file() and path.name != 'run.json'
        and not path.is_symlink() and not any(p.is_symlink() for p in path.parents if p != output)}
    save_manifest(output, manifest)
    verify(output)
    return manifest


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--gate', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--authorization-receipt', type=Path, required=True)
    p.add_argument('--diagnostic-ready', type=Path)
    p.add_argument('--memory-probe-build', type=Path)
    a = p.parse_args()
    result = freeze(a.build.resolve(), [g.resolve() for g in a.gate], a.output.resolve(), a.authorization_receipt.resolve(),
                    a.diagnostic_ready.resolve() if a.diagnostic_ready else None,
                    a.memory_probe_build.resolve() if a.memory_probe_build else None)
    print(json.dumps({'status': result['status'], 'cases': len(result['cases']),
                      'regions': sum(len(c['active_harts']) for c in result['cases']), 'hardware_contacted': False}))


if __name__ == '__main__':
    main()
