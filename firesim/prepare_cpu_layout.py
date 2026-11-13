#!/usr/bin/env python3
"""Prepare the original-operand-order CPU layout training batch; never launch."""
import argparse
import importlib.util
import itertools
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
from batch_runner import digest, prepare, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from run_prepared import verify

ROLE = 'cpu_layout_original_order_training_v2'
WATCHDOG = 600
PHASE_TIMEOUT = 780
TARGET_BOUND_REASON = ('No target +max-cycles: known successful FPGA startup global driver cycles exceeded '
                       '5,000,000,000; the proposed 1,900,000,000 bound could terminate the loader. '
                       'The original archived driver also parses this option with a 32-bit atoi. '
                       'Use the owned foreground wall watchdog instead.')


def load_validator():
    path = ROOT / 'benchmarks/cpu_layout_v2/verify.py'
    spec = importlib.util.spec_from_file_location('iris_cpu_layout_v2_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_cases(document):
    if (document.get('schema') != 'iris.cpu_layout_cases.v1'
            or document.get('required_regions') != 2313
            or document.get('fitting_only') is not True or document.get('global_heldout') is not False):
        raise ValueError('Exact training-only CPU layout case contract required')
    cases = document['cases']
    expected = {}
    for mode, offset, n, repeat in itertools.product(('compact', 'wide'), range(0, 64, 2),
                                                   (16, 64, 256, 1024), range(3)):
        expected[f'cpu.layout.v2.{mode}.off{offset}.n{n}.repeat{repeat}'] = (mode, offset, n, repeat)
    for repeat in range(3):
        expected[f'cpu.layout.v2.noop.off8.n0.repeat{repeat}'] = ('noop', 8, 0, repeat)
    if len(cases) != 771 or {c['id'] for c in cases} != set(expected):
        raise ValueError('Complete unique original-order v2 case identities required')
    for c in cases:
        mode, offset, n, repeat = expected[c['id']]
        parent = f'cpu.layout.v2.{mode}.off{offset}.n{n}'
        if (c.get('active_harts') != [0, 1, 2] or c.get('expected_checksums_by_hart') != [h + 1 + 3*n for h in range(3)]
                or c.get('parent_case_id') != parent or c.get('repeat_id') != repeat
                or c.get('mode') != mode or c.get('loop_offset') != offset or c.get('n') != n
                or c.get('region') != 'loop' or c.get('corpus_split') != 'cpu-layout-original-fit-v2'):
            raise ValueError('Independent layout identity/golden mismatch: ' + c['id'])
    validate_cases(cases, True)
    return cases


def check_rows(lines, proof):
    rows = load_validator().validate(lines, proof)
    for row in rows:
        name = f"cpu.layout.v2.{row['mode']}.off{row['loop_offset']}.n{row['n']}.repeat{row['repeat']}"
        if row.get('case_id') != name or row.get('region') != 'loop':
            raise ValueError('Console layout case identity mismatch')
    return rows


def admit(build, expected_ready_sha256):
    build = Path(build).resolve()
    paths = {name: build/name for name in ('ready.json', 'build.json', 'binary-proof.json',
                                         'qualification.json', 'cases.json', 'batch.elf', 'layout-meta.json')}
    if digest(paths['ready.json']) != expected_ready_sha256:
        raise ValueError('Ready packet must be frozen explicitly before preparation')
    ready, built, proof, qualification, case_doc = [json.loads(paths[name].read_text()) for name in
                                                  ('ready.json', 'build.json', 'binary-proof.json',
                                                   'qualification.json', 'cases.json')]
    if (ready.get('schema') != 'iris.cpu_layout_ready.v1' or ready.get('status') != 'ready_for_root_managed_preparation'
            or ready.get('fitting_only') is not True or ready.get('global_heldout') is not False
            or ready.get('source_frozen_for_preparation') is not True
            or (ready.get('required_regions'), ready.get('main_regions'), ready.get('noop_regions'),
                ready.get('harts'), ready.get('parent_layouts')) != (2313, 2304, 9, 3, 256)
            or Path(ready['elf']).resolve() != paths['batch.elf']
            or Path(ready['cases_path']).resolve() != paths['cases.json']):
        raise ValueError('Exact source-frozen three-hart training packet required')
    expected_hashes = {'batch.elf': 'elf_sha256', 'build.json': 'build_sha256',
                       'binary-proof.json': 'binary_proof_sha256', 'qualification.json': 'qualification_sha256',
                       'cases.json': 'cases_sha256'}
    for name, key in expected_hashes.items():
        if digest(paths[name]) != ready[key]:
            raise ValueError('Ready packet artifact changed: ' + name)
    elf_sha = ready['elf_sha256']
    if (built.get('schema') != 'iris.cpu_layout_build.v1' or built.get('fitting_only') is not True
            or built.get('elf_sha256') != elf_sha or built['argv'][-1] != str(paths['batch.elf'])
            or proof.get('schema') != 'iris.cpu_layout_binary_proof.v1' or proof.get('status') != 'passed'
            or proof.get('elf_sha256') != elf_sha or proof.get('fitting_only') is not True
            or proof.get('all64_actual_loop_offsets_and_opcode_widths_verified') is not True
            or qualification.get('schema') != 'iris.cpu_layout_qualification.v1'
            or qualification.get('status') != 'passed' or qualification.get('elf_sha256') != elf_sha
            or qualification.get('binary_proof_sha256') != digest(paths['binary-proof.json'])):
        raise ValueError('Exact original-order binary proof/build/qualification required')
    if (ready['source_inputs_sha256'] != built['input_sha256']
            or ready['support_source_sha256'] != qualification['support_source_sha256']
            or str(ROOT/'benchmarks/cpu_layout_v2/generate.py') not in built['input_sha256']):
        raise ValueError('Source packet does not describe the v2 original-order implementation')
    identities = {str(path): digest(path) for path in paths.values()}
    identities.update(built['input_sha256'])
    identities.update(qualification['support_source_sha256'])
    for name, expected in identities.items():
        if digest(name) != expected:
            raise ValueError('CPU layout build/support input changed: ' + name)
    cases = check_cases(case_doc)
    toolroot = Path(built['argv'][0]).parent
    nm = toolroot/'riscv64-unknown-elf-nm'
    identities[str(nm)] = digest(nm)
    if load_validator().inspect(build, toolroot) != proof:
        raise ValueError('Independent current ELF opcode/loop/CSR proof differs')
    expected_negatives = {(seed, field) for seed in (0, 17) for field in ('checksum', 'loop_pc', 'instret_delta')}
    negatives = qualification['negative_controls']
    if (len(negatives) != 6 or {(x['seed'], x['field']) for x in negatives} != expected_negatives
            or any(x.get('rejected') is not True for x in negatives)):
        raise ValueError('All six seeded numerical/PC/counter corruptions must be rejected')
    functional = qualification['functional']
    if len(functional) != 2 or {x['seed'] for x in functional} != {0, 17}:
        raise ValueError('Both actual seeded executions required')
    for entry in functional:
        gate = build/f"seed{entry['seed']}"
        result_path = gate/'results.json'
        result = json.loads(result_path.read_text())
        stdout, stderr = gate/'stdout', gate/'stderr'
        if (digest(result_path) != entry['results_sha256'] or digest(stdout) != entry['stdout_sha256']
                or entry.get('regions') != 2313 or entry.get('no_op_controls') != 9 or entry.get('exit_status') != 0
                or result.get('schema') != 'iris.empirical_training_native_replay.v1'
                or result.get('status') != 'completed' or result.get('exit_status') != 0
                or result.get('hardware_contacted') is not False
                or result.get('global_heldout_timings_consumed') is not False
                or result['argv'][-1] != str(paths['batch.elf']) or '-p3' not in result['argv']
                or result['argv'].count('--iris-schedule-seed='+str(entry['seed'])) != 1
                or any(x.startswith('--iris-timing-') for x in result['argv'])
                or result['input_sha256'].get(str(paths['batch.elf'])) != elf_sha):
            raise ValueError('Seeded functional receipt/ELF/argv mismatch')
        for name in ('stdout', 'stderr'):
            if digest(gate/name) != result['outputs_sha256'][name]:
                raise ValueError('Seeded raw output changed: ' + name)
        lines = stdout.read_text().splitlines()
        check_rows(lines, proof)
        for field in ('checksum', 'loop_pc', 'instret_delta'):
            changed = list(lines)
            index = next(i for i, line in enumerate(changed) if line.startswith('IRIS_REGION '))
            row = json.loads(changed[index].split(' ', 1)[1]); row[field] += 1
            changed[index] = 'IRIS_REGION '+json.dumps(row)
            try:
                check_rows(changed, proof)
            except ValueError:
                pass
            else:
                raise ValueError('Independent corruption accepted: ' + field)
        identities.update(result['input_sha256'])
        identities.update({str(p): digest(p) for p in (result_path, stdout, stderr, gate/'argv.json')})
    for name, expected in identities.items():
        if digest(name) != expected:
            raise ValueError('CPU layout admission input changed: ' + name)
    return ready, cases, paths['batch.elf'], identities


def freeze(args):
    import yaml
    build, output, authorization = args.build.resolve(), args.output.resolve(), args.authorization_receipt.resolve()
    ready, cases, elf, identities = admit(build, args.expected_ready_sha256)
    receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Actual standing-user authorization receipt required')
    controls_path = ROOT/'build/cpu-layout-tools-local-v1/report.json'
    controls = json.loads(controls_path.read_text())
    if (controls.get('schema') != 'iris.cpu_layout_managed_tools_local_controls.v1'
            or controls.get('pass') is not True or controls.get('unit_admission_tests') != 8
            or controls.get('real_wrong_role_archive', {}).get('rejected') is not True):
        raise ValueError('Successful actual local admission/corruption controls required')
    for name, expected in controls['input_sha256'].items():
        if digest(name) != expected:
            raise ValueError('Managed tool controls bind different source bytes: ' + name)
    identities.update(controls['input_sha256'])
    if args.validate_only:
        return {'status': 'local_admission_validated_no_job_or_hardware', 'expected_regions': 2313, 'hardware_contacted': False}
    fs = Path('/scratch/eygao/iris-cy/sims/firesim'); deploy = fs/'deploy'
    manager, manifest = prepare(deploy, output, elf, cases, deploy/'config_runtime.yaml', deploy/'config_hwdb.yaml',
        ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json', profile_interval=1000000)
    from memory_observation import freeze as freeze_memory
    freeze_memory(args.memory_probe_build.resolve(), output, manifest)
    add_observer(manager)
    watchdog = manager/'iris_workload_watchdog.py'; text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1:
        raise ValueError('Reviewed foreground watchdog changed')
    watchdog.write_text(text.replace('SECONDS=1500', 'SECONDS='+str(WATCHDOG), 1))
    runtime_path = manager/'config_runtime.yaml'; runtime = yaml.safe_load(runtime_path.read_text())
    original = runtime['target_config'].get('plusarg_passthrough', '')
    if '+fesvr-step-size' in original or '+max-cycles' in original:
        raise ValueError('Conflicting loader or unsafe target-cycle bound')
    runtime['target_config']['plusarg_passthrough'] = (original+' +fesvr-step-size=128').strip()
    runtime_path.write_text(yaml.safe_dump(runtime, sort_keys=False))
    for name in ('ready.json', 'build.json', 'binary-proof.json', 'qualification.json', 'cases.json', 'layout-meta.json'):
        (output/name).write_bytes((build/name).read_bytes())
    (output/'corpus.json').write_bytes((build/'ready.json').read_bytes())
    (output/'launch-authorization.json').write_bytes(authorization.read_bytes())
    checklist = {'schema': 'iris.cpu_layout_capture_checklist.v1', 'frozen_before_launch': True,
        'fitting_only': True, 'global_heldout': False, 'expected_regions': 2313, 'cases': 771,
        'harts_online': [0, 1, 2], 'regions_by_hart': 771, 'main_regions': 2304, 'noop_regions': 9,
        'loop_shapes': {'modes': ['compact', 'wide'], 'actual_loop_offsets': list(range(0, 64, 2)),
                        'N': [16, 64, 256, 1024], 'immediate_repeats': 3},
        'goldens': {'checksum': 'hart+1+3*N', 'counter_end': 'N',
                    'minstret_delta': {'Shuttle0/1': '3*N+2', 'Rocket2': '3*N+3'}},
        'operand_order': 'Original literal compact c.addi a0,3; c.addiw a5,1; bne a1,a5,loop. v1 is superseded.',
        'cache_condition': ready['conditions']['cache_condition'], 'UART_inside_ROI': False,
        'required': ['Raw UART/manager stdout/stderr and complete failures; all2313 raw counter/checksum/loop+CSR PC records',
            'Exact source/compiler/ELF/binary proof/seed0+17/six negative controls and original driver/image/runtime/HWDB/plusargs',
            'Four managed phases with fresh all-user/device checks/shared lock/owned cleanup/external quiescent archive',
            'Available heartbeat/aggregate FASED CSV plus reviewed read-only FASED settings; no invented per-hart attribution'],
        'unavailable_instrumentation': ['TracerV', 'AutoCounter', 'SynthPrint'],
        'remote_wall_watchdog_seconds': WATCHDOG, 'host_phase_timeout_seconds': PHASE_TIMEOUT,
        'target_cycle_bound': None, 'target_cycle_bound_omission_reason': TARGET_BOUND_REASON,
        'proposed_runtime_not_applied': ready.get('proposed_runtime'),
        'calibration_usable': False, 'timing_certified': False, 'source_image_association_verified': False}
    (output/'capture-checklist.json').write_text(json.dumps(checklist, indent=2)+'\n')
    launch = ['#!/usr/bin/env bash', 'export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH',
        'cd '+shlex.quote(str(fs))+' || exit 1',
        'source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(output/'launch-environment.stdout'))+
            ' 2> '+shlex.quote(str(output/'launch-environment.stderr')),
        'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3', str(ROOT/'firesim/run_prepared.py'),
            str(output), '--execute', '--authorization-id', receipt['authorization']['authorization_id'],
            '--timeout', str(PHASE_TIMEOUT)])]
    (output/'launch.sh').write_text('\n'.join(launch)+'\n'); (output/'launch.sh').chmod(0o700)
    env_paths = [fs/'sourceme-manager.sh', fs/'env.sh', fs.parent.parent/'env.sh']
    sources = [Path(__file__).resolve(), ROOT/'firesim/analyze_cpu_layout.py', ROOT/'firesim/test_cpu_layout.py',
        ROOT/'build/cpu-layout-tools-local-v1/report.json', ROOT/'firesim/analyze_campaign.py',
        ROOT/'firesim/run_prepared.py', ROOT/'firesim/prepare_managed_campaign.py', ROOT/'firesim/workload_watchdog.py',
        ROOT/'firesim/managed_programming_tools.py', ROOT/'firesim/setup_phase_observer.py', authorization,
        ROOT/'build/xilinx-tool-paths-v1.json', *env_paths,
        Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    identities.update({str(path): digest(path) for path in sources})
    manifest['input_sha256'].update(identities); snapshot_inputs(output, manifest['input_sha256'])
    manifest.update(require_regions=True, require_goldens=True, campaign_role=ROLE,
        launch_authorization_receipt=receipt, corpus_sha256=digest(output/'corpus.json'),
        ready_sha256=args.expected_ready_sha256, expected_regions=2313, fitting_only=True, global_heldout=False,
        calibration_usable=False, timing_accuracy_certified=False, hardware_source_association_verified=False,
        prepared_manager_sha256=digest(manager/'firesim'), prepared_runtime_sha256=digest(runtime_path),
        frozen_capture_checklist_sha256=digest(output/'capture-checklist.json'),
        environment_source_sha256={str(p): digest(p) for p in env_paths},
        loader_override={'fesvr_step_size_target_cycles': 128, 'target_cycle_bound': None,
            'target_cycle_bound_omission_reason': TARGET_BOUND_REASON, 'remote_wall_watchdog_seconds': WATCHDOG,
            'foreground': True, 'driver_binary_unchanged': True})
    manifest['prepared_file_sha256'] = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name != 'run.json' and not p.is_symlink()
        and not any(parent.is_symlink() for parent in p.parents if parent != output)}
    save_manifest(output, manifest); verify(output)
    return {'status': manifest['status'], 'expected_regions': 2313, 'hardware_contacted': False, 'job': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--build', type=Path, default=ROOT/'build/cpu-layout-v2')
    parser.add_argument('--expected-ready-sha256', required=True)
    parser.add_argument('--authorization-receipt', type=Path, required=True)
    parser.add_argument('--memory-probe-build', type=Path, default=ROOT/'build/fased-readonly-managed-v2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    print(json.dumps(freeze(parser.parse_args())))
