#!/usr/bin/env python3
"""Freeze the independently checked baremetal context-size transfer control."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch_runner import prepare, digest, validate_cases, save_manifest
from prepare_managed_campaign import add_observer, snapshot_inputs
from run_prepared import verify


def freeze(build, gates, output, authorization, page=False, memory_probe_build=None, acceptance=None):
    import yaml
    proof = json.loads((build / 'build.json').read_text())
    corpus_path = build / 'corpus.json';corpus = json.loads(corpus_path.read_text())
    elf = build / 'probe.elf'
    if proof.get('status') != 'built' or digest(elf) != proof['elf_sha256']:
        raise ValueError('Exact successful baremetal build required')
    count = 2550 if page else 120
    split = 'iris-rvv-page-transport-fit-v1' if page else 'iris-rvv-context-transport-fit-v1'
    if corpus.get('split_id') != split or len(corpus['cases']) != count:
        raise ValueError('Exact declared transport control required')
    if page and digest(corpus_path) != proof.get('corpus_sha256'):
        raise ValueError('Exact built page layout/corpus required')
    records = [json.loads((gate / 'report.json').read_text()) for gate in gates]
    if {g['seed'] for g in records} != {0, 17}:
        raise ValueError('Both independent seed0/17 gates required')
    for gate in records:
        if (gate.get('pass') is not True or gate['elf_sha256'] != digest(elf)
                or gate['corpus_sha256'] != digest(corpus_path) or gate['proof']['regions'] != count):
            raise ValueError('Exact ELF/corpus functional gate required')
        for name, expected in gate['input_sha256'].items():
            if digest(name) != expected:
                raise ValueError('Functional gate source changed: ' + name)
    acceptance_record = None
    if page:
        if acceptance is None:
            raise ValueError('Exact page/CSR adversarial acceptance receipt required')
        acceptance_record = json.loads(acceptance.read_text())
        if (acceptance_record.get('schema') != 'iris.rvv_page_transport_acceptance.v1'
                or acceptance_record.get('pass') is not True
                or acceptance_record.get('elf_sha256') != digest(elf)
                or len(acceptance_record.get('negative_controls', [])) != 22
                or any(c.get('rejected') is not True for c in acceptance_record['negative_controls'])):
            raise ValueError('Unqualified page/CSR acceptance receipt')
        for name, expected in acceptance_record['input_sha256'].items():
            if digest(name) != expected:
                raise ValueError('Page/CSR acceptance input changed: ' + name)
        if {(r['seed'], r['report_sha256']) for r in acceptance_record['gates']} != {
                (r['seed'], digest(g / 'report.json')) for g, r in zip(gates, records)}:
            raise ValueError('Page/CSR acceptance gates differ')
    cases = [dict(id=c['case_id'], active_harts=[2], expected_checksums_by_hart=c['expected_checksums'],
                  parent_case_id=c['parent_case_id'], trial_id=c['trial_id'], suite=c['suite'],
                  region='kernel', corpus_split=corpus['split_id']) for c in corpus['cases']]
    validate_cases(cases, True)
    deploy = Path('/scratch/eygao/iris-cy/sims/firesim/deploy')
    audit = ROOT / 'build/firesim-observability-archived-driver-v3/report.json'
    manager, manifest = prepare(deploy, output, elf, cases, deploy / 'config_runtime.yaml',
        deploy / 'config_hwdb.yaml', ROOT / 'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=audit, profile_interval=1000000)
    if memory_probe_build is not None:
        from memory_observation import freeze as freeze_memory_observer
        freeze_memory_observer(memory_probe_build, output, manifest)
    add_observer(manager)
    watchdog = manager / 'iris_workload_watchdog.py';text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1:
        raise ValueError('Exact foreground watchdog contract changed')
    watchdog_seconds = 180 if page else 60
    watchdog.write_text(text.replace('SECONDS=1500', 'SECONDS=' + str(watchdog_seconds), 1))
    path = manager / 'config_runtime.yaml';runtime = yaml.safe_load(path.read_text())
    original = runtime['target_config'].get('plusarg_passthrough', '')
    if '+fesvr-step-size' in original or '+max-cycles' in original:
        raise ValueError('Conflicting manual loader or cycle limit')
    runtime['target_config']['plusarg_passthrough'] = (original + ' +fesvr-step-size=128').strip()
    path.write_text(yaml.safe_dump(runtime, sort_keys=False))
    receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Current user authorization receipt required')
    (output / 'launch-authorization.json').write_bytes(authorization.read_bytes())
    (output / 'corpus.json').write_bytes(corpus_path.read_bytes())
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    checklist = {'schema': 'iris.rvv_transport_capture_checklist.v1', 'frozen_before_launch': True,
        'purpose': 'Page-boundary and vector-CSR context-restore controls' if page else 'Separate baremetal LMUL8 transport from Zephyr lazy vector context restore',
        'expected_regions': count, 'trials': 5, 'groups': count // 5, 'expected_probe_begin_records': count,
        'harts_online': [0, 1, 2], 'idle_policy': corpus['idle_policy'], 'heldout': False,
        'required': ['Exact stdout/stderr/UART; every region cycle/instret/FNV64 and probe-begin identity',
                     'Last probe identity and failure/timeout evidence on partial outcome',
                     'Full lifecycle/setup timings, runtime/HWDB/plusargs, all source/tool/ELF/image/driver identities',
                     'Heartbeat, FASED CSV, complete owned cleanup and outside-job archive'],
        'observer_and_fence_modes': 'Hart0 bounded polling and per-case drain/no-drain branches alter timing; no isolated throughput or OS qualification claim.',
        'remote_wall_watchdog_seconds': watchdog_seconds, 'foreground': True, 'host_phase_timeout_seconds': 360,
        'no_clock_or_memory_parameter_override': True, 'calibration_usable': False}
    if memory_probe_build is not None:
        checklist['readonly_memory_observation'] = manifest['readonly_memory_observation']
    if page:
        checklist.update(runtime_vlenb_all_harts=[32, 32, 32],
                         exact_elf_page_layout=corpus['layout'],
                         page_and_csr_acceptance_sha256=digest(acceptance),
                         byte_guards_before_and_after_output=32)
    (output / 'capture-checklist.json').write_text(json.dumps(checklist, indent=2) + '\n')
    paths = [Path(__file__).resolve(), ROOT / 'firesim/prepare_managed_campaign.py', ROOT / 'firesim/analyze_campaign.py',
             ROOT / 'firesim/run_prepared.py', ROOT / 'firesim/workload_watchdog.py',
             ROOT / 'firesim/managed_programming_tools.py', ROOT / 'firesim/setup_phase_observer.py',
             ROOT / ('benchmarks/rvv_page_transport/validate.py' if page else 'benchmarks/rvv_context_transport/validate.py'), build / 'build.json', corpus_path,
             ROOT / 'build/xilinx-tool-paths-v1.json', authorization,
             Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    manifest['input_sha256'].update(proof['input_sha256'])
    if page:
        paths.append(acceptance)
        manifest['input_sha256'].update(acceptance_record['input_sha256'])
    for gate, record in zip(gates, records):
        manifest['input_sha256'].update(record['input_sha256'])
        paths += [gate / name for name in ('report.json', 'corpus.json', 'stdout', 'stderr')]
    manifest['input_sha256'].update({str(p): digest(p) for p in paths})
    snapshot_inputs(output, manifest['input_sha256'])
    manifest.update(require_regions=True, require_goldens=True, campaign_role='rvv_page_transport_diagnostic' if page else 'rvv_transport_diagnostic',
        launch_authorization_receipt=receipt, corpus_sha256=digest(output / 'corpus.json'),
        timing_perturbed=True, baseline_timing_equivalent=False, calibration_usable=False,
        hardware_source_association_verified=False, prepared_manager_sha256=digest(manager / 'firesim'),
        prepared_runtime_sha256=digest(path), frozen_capture_checklist_sha256=digest(output / 'capture-checklist.json'),
        loader_override={'fesvr_step_size_target_cycles': 128, 'target_cycle_bound': None,
                         'remote_wall_watchdog_seconds': watchdog_seconds, 'foreground': True, 'driver_binary_unchanged': True})
    manifest['prepared_file_sha256'] = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name != 'run.json' and not p.is_symlink()
        and not any(parent.is_symlink() for parent in p.parents if parent != output)}
    save_manifest(output, manifest);verify(output)
    return manifest


def main():
    p = argparse.ArgumentParser(__doc__);p.add_argument('--build', type=Path, required=True)
    p.add_argument('--gate', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True);p.add_argument('--authorization-receipt', type=Path, required=True)
    p.add_argument('--page-boundaries', action='store_true');p.add_argument('--memory-probe-build', type=Path)
    p.add_argument('--acceptance-report', type=Path)
    a = p.parse_args();r = freeze(a.build.resolve(), [g.resolve() for g in a.gate], a.output.resolve(), a.authorization_receipt.resolve(),
                                 a.page_boundaries, a.memory_probe_build.resolve() if a.memory_probe_build else None,
                                 a.acceptance_report.resolve() if a.acceptance_report else None)
    print(json.dumps({'status': r['status'], 'regions': 2550 if a.page_boundaries else 120, 'hardware_contacted': False}))


if __name__ == '__main__':
    main()
