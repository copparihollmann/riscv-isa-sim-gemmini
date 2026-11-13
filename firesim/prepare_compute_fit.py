#!/usr/bin/env python3
"""Prepare the independently reviewed compute fitting ELF; never launch hardware."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch_runner import digest, prepare, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from prepare_buffered_priority import merge_inputs, NO_TARGET_BOUND
from run_prepared import verify

ROLE = 'compute_fitting_campaign_v1'
WATCHDOG, PHASE_TIMEOUT = 600, 780


def validator():
    path = ROOT / 'benchmarks/compute_fit/validate.py'
    spec = importlib.util.spec_from_file_location('iris_compute_fit_validator', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def corpus_cases(corpus, original):
    validator().admitted(corpus)
    if len(corpus['cases']) != 456 or corpus['expected_region_count'] != 1008:
        raise ValueError('Complete456case/1008region compute packet required')
    prior = {c['case_id']: c for c in original['cases']}
    expected_order = [c['case_id'] for c in original['cases'] if c['suite'] == 'distribution'
                      and c['kind'] not in ('memory', 'vme_memory')]
    if [c['case_id'].replace('compute.v1.', 'buffered.v2.', 1) for c in corpus['cases']] != expected_order:
        raise ValueError('Static parent source order must be preserved')
    parents = set(); trials = {}
    for case in corpus['cases']:
        copied = dict(case)
        copied['case_id'] = copied['case_id'].replace('compute.v1.', 'buffered.v2.', 1)
        copied['parent_case_id'] = copied.pop('reference_parent_case_id')
        if copied != prior.get(copied['case_id']):
            raise ValueError('Compute kernel parameters/goldens differ from declared semantic parent')
        parents.add(case['semantic_parent_case_id'])
        trials.setdefault(case['parent_case_id'], []).append(case['trial_id'])
    if len(parents) != 152 or any(sorted(v) != [0, 1, 2] for v in trials.values()):
        raise ValueError('Every semantic parent must retain three unique trials')
    cases = [{'id': c['case_id'], 'active_harts': [h for h in range(3) if c['mask'] & (1 << h)],
              'parent_case_id': c['parent_case_id'], 'semantic_parent_case_id': c['semantic_parent_case_id'],
              'trial_id': c['trial_id'], 'suite': c['suite'], 'region': 'kernel',
              'expected_checksums_by_hart': c['expected_checksums']} for c in corpus['cases']]
    validate_cases(cases, True)
    if sum(len(c['active_harts']) for c in cases) != 1008:
        raise ValueError('Exact all-hart region coverage required')
    return cases


def check_readback(elf, layout, corpus):
    if (layout.get('schema') != 'iris.buffered_campaign_readback_layout.v1'
            or layout.get('elf_sha256') != digest(elf) or layout.get('record_bytes') != 64
            or layout.get('records') != 1008 or layout.get('fields') !=
                ['case_index', 'hart', 'start', 'end', 'instret', 'checksum', 'expected', 'pass']
            or layout.get('stop_sentinel_initial_value') != (1 << 64)-1
            or layout.get('stop_sentinel_complete_value') != 0
            or layout.get('file_backed_initial_sentinel_verified') is not True
            or layout.get('intentional_debugger_stop_is_normal_guest_exit') is not False):
        raise ValueError('Exact known-sentinel64-byte-record readback contract required')
    objects = layout['objects']
    if set(objects) != {'buffered_records', 'buffered_measurements_done', 'buffered_record_count', 'buffered_case_count'}:
        raise ValueError('Complete physical readback object identities required')
    if objects['buffered_records']['size'] != 64*1008:
        raise ValueError('Readback array must contain every measured region')
    raw = Path(elf).read_bytes()
    if raw[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Little-endian ELF64 required')
    phoff = struct.unpack_from('<Q', raw, 32)[0]; phsize, phnum = struct.unpack_from('<HH', raw, 54)
    sentinel = objects['buffered_measurements_done']['address']; found = False
    for k in range(phnum):
        typ, flags, off, va, pa, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', raw, phoff+k*phsize)
        if typ != 1: continue
        if any(max(base, pa) < min(base+size, pa+memsz) for base, size in corpus['memory_regions'].values()):
            raise ValueError('ELF overlaps a tested memory window')
        if pa <= sentinel and sentinel+8 <= pa+filesz:
            if int.from_bytes(raw[off+sentinel-pa:off+sentinel-pa+8], 'little') != (1 << 64)-1:
                raise ValueError('Actual loaded sentinel bytes are not known UINT64_MAX')
            found = True
    if not found: raise ValueError('Completion sentinel must be file-backed before CRT/BSS')


def admit(build, expected_ready):
    build = Path(build).resolve()
    if digest(build / 'ready.json') != expected_ready: raise ValueError('Ready packet changed')
    ready = json.loads((build / 'ready.json').read_text())
    corpus = json.loads((build / 'corpus.json').read_text())
    original = json.loads((build / 'original-corpus.json').read_text())
    cases = corpus_cases(corpus, original); elf = build / 'campaign.elf'
    if (ready.get('schema') != 'iris.compute_fitting_ready.v1'
            or ready.get('fitting_only') is not True or ready.get('global_heldout') is not False
            or ready.get('elf_sha256') != digest(elf) or ready.get('corpus_sha256') != digest(build / 'corpus.json')
            or ready.get('required_cases') != 456 or ready.get('required_regions') != 1008):
        raise ValueError('Exact new fitting-only compute readiness required')
    check_readback(elf, json.loads((build / 'readback-layout.json').read_text()), corpus)
    identities = {str(build / name): digest(build / name) for name in
        ('ready.json', 'build.json', 'corpus.json', 'qualification.json', 'readback-layout.json', 'split.json', 'original-corpus.json')}
    for name, field in [('build.json', 'build_sha256'), ('qualification.json', 'qualification_sha256'),
                        ('readback-layout.json', 'readback_layout_sha256')]:
        if digest(build / name) != ready.get(field): raise ValueError('Readiness evidence changed: ' + name)
    built = json.loads((build / 'build.json').read_text())
    if (built.get('elf_sha256') != digest(elf) or built.get('bss_bytes', 1 << 30) > 131072
            or built.get('kernel_preparation_and_measured_window_source_unchanged') is not True):
        raise ValueError('Reviewed small-BSS exact-kernel build required')
    merge_inputs(identities, built['input_sha256'])
    qualification = json.loads((build / 'qualification.json').read_text())
    if qualification.get('pass') is not True or qualification.get('elf_sha256') != digest(elf):
        raise ValueError('Successful exact compute functional qualification required')
    negatives = qualification.get('negative_controls', [])
    if len(negatives) != 14 or any(n.get('rejected') is not True for n in negatives):
        raise ValueError('All14 numerical/identity/completion corruption controls required')
    merge_inputs(identities, qualification['input_sha256'])
    review_path = Path(ready['independent_prelaunch_review']).resolve()
    if digest(review_path) != ready['independent_prelaunch_review_sha256']:
        raise ValueError('Independent prelaunch review changed')
    reviewed = json.loads(review_path.read_text())
    if (reviewed.get('schema') != 'iris.compute_fitting_independent_review.v1' or reviewed.get('pass') is not True
            or reviewed.get('ELF_sha256') != digest(elf) or reviewed.get('corpus_sha256') != digest(build / 'corpus.json')
            or reviewed.get('split_sha256') != digest(build / 'split.json')
            or [reviewed.get(k) for k in ('cases', 'semantic_parents', 'regions')] != [456, 152, 1008]
            or any(reviewed.get(k) is not True for k in ('kernel_preparation_window_source_equal',
                'compiled_table_identity_order_verified', 'independent_goldens_verified', 'no_bulk_memory_cases'))):
        raise ValueError('Independent source/table/golden/split/storage review required')
    merge_inputs(identities, reviewed['input_sha256']); identities[str(review_path)] = digest(review_path)
    for seed in (0, 17):
        folder = build / ('seed' + str(seed)); result = json.loads((folder / 'run.json').read_text())
        if (result.get('schema') != 'iris.compute_fitting_functional_run.v1' or result.get('status') != 'passed'
                or result.get('seed') != seed or result.get('exit_status') != 0
                or result.get('regions') != 1008 or result['argv'][-1] != str(elf)
                or '-p3' not in result['argv'] or '--iris-schedule-seed=' + str(seed) not in result['argv']):
            raise ValueError('Both exact successful three-hart functional schedules required')
        for suffix in ('stdout', 'stderr'):
            if digest(folder / ('run.' + suffix)) != result[suffix + '_sha256']:
                raise ValueError('Functional output changed')
        validator().validate((folder / 'run.stdout').read_text(), corpus)
        merge_inputs(identities, result['input_sha256'])
        merge_inputs(identities, {str(folder / name): digest(folder / name) for name in ('run.json', 'run.stdout', 'run.stderr')})
    identities[str(elf)] = digest(elf)
    for name, wanted in identities.items():
        if digest(name) != wanted: raise ValueError('Declared compute input changed: ' + name)
    return ready, corpus, cases, elf, identities


def freeze(args):
    import yaml
    build, output = args.build.resolve(), args.output.resolve()
    ready, corpus, cases, elf, identities = admit(build, args.expected_ready_sha256)
    authorization = args.authorization_receipt.resolve(); receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Actual user launch authorization receipt required')
    controls_path = args.controls.resolve(); controls = json.loads(controls_path.read_text())
    if (controls.get('schema') != 'iris.compute_fitting_managed_tool_controls.v1'
            or controls.get('pass') is not True or controls.get('unit_admission_tests') != 8
            or controls.get('real_wrong_role_archive', {}).get('rejected') is not True):
        raise ValueError('Actual admission and wrong-reference archive controls required')
    for name, wanted in controls['input_sha256'].items():
        if digest(name) != wanted: raise ValueError('Managed tool controls bind changed input: ' + name)
    merge_inputs(identities, controls['input_sha256']); identities[str(controls_path)] = digest(controls_path)
    if args.validate_only: return {'status': 'local_admission_validated', 'regions': 1008, 'hardware_contacted': False}
    fs = Path('/scratch/eygao/iris-cy/sims/firesim'); deploy = fs / 'deploy'
    manager, manifest = prepare(deploy, output, elf, cases, deploy / 'config_runtime.yaml', deploy / 'config_hwdb.yaml',
        ROOT / 'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT / 'build/firesim-observability-archived-driver-v3/report.json', profile_interval=1000000)
    from memory_observation import freeze as freeze_memory
    freeze_memory(args.memory_probe_build.resolve(), output, manifest); add_observer(manager)
    watchdog = manager / 'iris_workload_watchdog.py'; text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1: raise ValueError('Reviewed watchdog changed')
    watchdog.write_text(text.replace('SECONDS=1500', 'SECONDS=' + str(WATCHDOG), 1))
    runtime_path = manager / 'config_runtime.yaml'; runtime = yaml.safe_load(runtime_path.read_text())
    previous = runtime['target_config'].get('plusarg_passthrough', '')
    if '+max-cycles' in previous or '+fesvr-step-size' in previous: raise ValueError('Conflicting loader/cycle bound')
    runtime['target_config']['plusarg_passthrough'] = (previous + ' +fesvr-step-size=128').strip()
    runtime_path.write_text(yaml.safe_dump(runtime, sort_keys=False))
    for name in ('corpus.json', 'ready.json', 'build.json', 'qualification.json', 'readback-layout.json', 'split.json', 'original-corpus.json'):
        (output / name).write_bytes((build / name).read_bytes())
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    (output / 'launch-authorization.json').write_bytes(authorization.read_bytes())
    checklist = {'schema': 'iris.compute_fitting_capture_checklist.v1', 'frozen_before_launch': True,
        'fitting_only': True, 'global_heldout': False, 'cases': 456, 'semantic_parents': 152, 'trials': 3,
        'expected_regions': 1008, 'remote_wall_watchdog_seconds': WATCHDOG, 'host_phase_timeout_seconds': PHASE_TIMEOUT,
        'old_campaign_timings_applicable': False, 'new_exact_ELF_reference_required': True,
        'required': ['All region mcycle/minstret/checksums, failure/terminal records and repeat identity',
            'Raw manager/stdout/stderr/UART/heartbeat/FASED, exact configs/plusargs and all source/ELF/toolchain/image/driver digests',
            'Complete four-phase managed lifecycle with full occupancy/ownership/lock checks and owned cleanup before external capture'],
        'unavailable_instrumentation': ['TracerV', 'AutoCounter', 'SynthPrint'],
        'source_image_association_verified': False, 'timing_accuracy_certified': False}
    (output / 'capture-checklist.json').write_text(json.dumps(checklist, indent=2) + '\n')
    sources = [Path(__file__).resolve(), ROOT / 'firesim/analyze_compute_fit.py', ROOT / 'firesim/analyze_campaign.py',
        ROOT / 'firesim/prepare_buffered_priority.py', ROOT / 'firesim/prepare_managed_campaign.py', ROOT / 'firesim/run_prepared.py',
        ROOT / 'firesim/workload_watchdog.py', ROOT / 'firesim/setup_phase_observer.py', ROOT / 'firesim/managed_programming_tools.py',
        ROOT / 'benchmarks/compute_fit/validate.py', ROOT / 'benchmarks/campaign_buffered/validate_priority.py',
        ROOT / 'firesim/test_compute_fit.py', controls_path, authorization,
        ROOT / 'build/xilinx-tool-paths-v1.json', fs / 'sourceme-manager.sh', fs / 'env.sh', fs.parent.parent / 'env.sh']
    merge_inputs(identities, {str(p): digest(p) for p in sources}); merge_inputs(manifest['input_sha256'], identities)
    snapshot_inputs(output, manifest['input_sha256'])
    manifest.update(campaign_role=ROLE, require_regions=True, require_goldens=True, expected_regions=1008,
        fitting_only=True, global_heldout=False, launch_authorization_receipt=receipt,
        corpus_sha256=digest(output / 'corpus.json'), ready_sha256=args.expected_ready_sha256,
        old_campaign_timings_applicable=False, new_exact_ELF_reference_required=True,
        calibration_usable=False, timing_accuracy_certified=False, hardware_source_association_verified=False,
        prepared_manager_sha256=digest(manager / 'firesim'), prepared_runtime_sha256=digest(runtime_path),
        frozen_capture_checklist_sha256=digest(output / 'capture-checklist.json'),
        loader_override={'fesvr_step_size_target_cycles': 128, 'target_cycle_bound': None,
            'target_cycle_bound_omission_reason': NO_TARGET_BOUND, 'remote_wall_watchdog_seconds': WATCHDOG,
            'foreground': True, 'driver_binary_unchanged': True})
    launch = ['#!/usr/bin/env bash', 'export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH',
        'cd ' + shlex.quote(str(fs)) + ' || exit 1',
        'source ./sourceme-manager.sh --skip-ssh-setup > ' + shlex.quote(str(output / 'launch-environment.stdout')) +
            ' 2> ' + shlex.quote(str(output / 'launch-environment.stderr')),
        'exec ' + shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3', str(ROOT / 'firesim/run_prepared.py'),
            str(output), '--execute', '--authorization-id', receipt['authorization']['authorization_id'], '--timeout', str(PHASE_TIMEOUT)])]
    (output / 'launch.sh').write_text('\n'.join(launch) + '\n'); (output / 'launch.sh').chmod(0o700)
    manifest['prepared_file_sha256'] = {str(p.relative_to(output)): digest(p) for p in output.rglob('*')
        if p.is_file() and p.name != 'run.json' and not p.is_symlink()
        and not any(parent.is_symlink() for parent in p.parents if parent != output)}
    save_manifest(output, manifest); verify(output)
    return {'status': manifest['status'], 'regions': 1008, 'hardware_contacted': False, 'job': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--build', type=Path, default=ROOT / 'build/compute-fit-v3')
    parser.add_argument('--expected-ready-sha256', required=True)
    parser.add_argument('--authorization-receipt', type=Path, required=True)
    parser.add_argument('--memory-probe-build', type=Path, default=ROOT / 'build/fased-readonly-managed-v2')
    parser.add_argument('--controls', type=Path, default=ROOT / 'build/compute-fit-tools-controls-v1/report.json')
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--validate-only', action='store_true')
    print(json.dumps(freeze(parser.parse_args())))
