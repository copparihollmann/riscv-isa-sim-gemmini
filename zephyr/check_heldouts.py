#!/usr/bin/env python3
"""Check frozen held-outs functionally; never fit or certify timing."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'firesim'))
from batch_runner import parse_regions, validate_cases
from spike.run_functional import command, symbols
from freeze_heldouts import sha, output_hash

EXPECTED_SUITE = '1b3bbe5e0c585beff4905761547964073bb177ac97c1145aa9722dfcb016c78e'


def frozen_suite(path, expected):
    if sha(path) != expected:
        raise ValueError('Frozen held-out manifest changed')
    suite = json.loads(path.read_text()); root = path.parent.resolve()
    if suite.get('schema') != 'iris.frozen_independent_heldout_suite.v2' or suite.get('fitting_allowed') is not False:
        raise ValueError('Frozen independent held-out suite required')
    for original, item in suite['inputs'].items():
        saved = (root / item['object']).resolve()
        if root not in saved.parents or sha(saved) != item['sha256']:
            raise ValueError('Held-out object changed/escaped: ' + original)
    def load(original):
        return json.loads((root / suite['inputs'][str(Path(original).resolve())]['object']).read_text())
    return suite, load


def validate(text, case, variant, golden, region_cases, elf_sha256):
    lines = text.splitlines()
    if any(line.startswith(('IRIS_FATAL', 'IRIS_COMPILER_FATAL')) for line in lines):
        raise ValueError('Guest fatal diagnostic')
    validate_cases(region_cases, True)
    rows = parse_regions(text, region_cases, elf_sha256, None, True, True)
    results = [json.loads(line.split(' ', 1)[1]) for line in lines if line.startswith('IRIS_COMPILER_RESULT ')]
    if any(type(row.get('job')) is not int or any(not isinstance(row.get(key),list) or
            any(type(value) is not int or not 0<=value<1<<32 for value in row[key])
            for key in ('accumulator_u32','w8a8_f32_words')) for row in results):
        raise ValueError('Invalid output container types')
    if results != golden:
        raise ValueError('Full INT32/W8A8 output differs from independent golden')
    if len(rows) != case['expected_regions']:
        raise ValueError('Incorrect held-out region count')
    for row in rows:
        if row['end_cycle'] <= row['start_cycle'] or not row['instret_delta']:
            raise ValueError('Invalid raw guest counter boundaries')
        if row['region'] == 'pipeline_end_to_end':
            if row['hart'] != 2 or row['role'] != 'pipeline.end_to_end' or row.get('scope') != 'producer_entry_to_all_outputs_consumed':
                raise ValueError('End-to-end region must use one pinned producer hart and defined scope')
        else:
            job = int(row['region'].removeprefix('job'))
            if (any(type(row.get(key)) is not int for key in ('trial_id','dataset_id','hart_mask'))
                    or row.get('trial_id') != job // 3 or row.get('dataset_id') != job % 3
                    or row['role'] != ('vme.compute' if variant == 'shipped' else 'scalar.compute')
                    or row['hart_mask'] != (1 << case['workers']) - 1):
                raise ValueError('Held-out trial/dataset/placement/variant identity mismatch')
    producer = [json.loads(line.split(' ', 1)[1]) for line in lines if line.startswith('IRIS_COMPILER_PRODUCER ')]
    expected = next(r['expected_checksums_by_hart'][2] for r in region_cases if r['active_harts'] == [2])
    if (len(producer) != 1 or producer[0].get('hart') != 2 or producer[0].get('jobs') != case['jobs']
            or producer[0].get('vector_checksum') != expected or producer[0].get('vme_refused') is not True):
        raise ValueError('Hart2 producer checksum/identity/refusal mismatch')
    masks = producer[0]['overlap_masks']
    if (len(masks) != case['jobs'] or any(type(mask) is not int or not 0 <= mask < 1 << case['workers'] for mask in masks)
            or not any(masks[:2])):
        raise ValueError('Missing/invalid CPU producer overlap evidence')
    if lines.count('PASSED compiler Zephyr double-buffer pipeline') != 1:
        raise ValueError('Missing/duplicate successful terminal marker')
    return {'functional_checks_passed': True, 'regions': rows, 'output_elements': len(golden) * len(golden[0]['accumulator_u32']),
            'all_int32_and_w8a8_values_match': True, 'all_five_trials_checked': case['trials'] == 5,
            'calibration_usable': False, 'timing_accuracy_certified': False}


def corruptions(text):
    def change(prefix, field, value):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith(prefix):
                row = json.loads(line[len(prefix):]); row[field] = value(row[field]); lines[i] = prefix + json.dumps(row); break
        return '\n'.join(lines)
    lines = text.splitlines(); first_region = next(line for line in lines if line.startswith('IRIS_REGION '))
    yield 'checksum', change('IRIS_REGION ', 'checksum', lambda x: x ^ 1)
    yield 'end_to_end_missing', '\n'.join(line for line in lines if not line.startswith('IRIS_REGION ') or json.loads(line.split(' ', 1)[1])['region'] != 'pipeline_end_to_end')
    yield 'duplicate_region', text + '\n' + first_region
    yield 'end_to_end_scope', change('IRIS_REGION ', 'scope', lambda x: 'unproven_cross_hart_interval')
    for field in ('trial_id','dataset_id'):
        damaged=list(lines)
        for i,line in enumerate(damaged):
            if line.startswith('IRIS_REGION '):
                row=json.loads(line.split(' ',1)[1])
                if row['region']!='pipeline_end_to_end':
                    row[field]+=1;damaged[i]='IRIS_REGION '+json.dumps(row);break
        yield field, '\n'.join(damaged)
    yield 'full_w8a8_golden', change('IRIS_COMPILER_RESULT ', 'w8a8_f32_words', lambda x: [x[0] ^ 1, *x[1:]])
    first = next(line for line in lines if line.startswith('IRIS_COMPILER_RESULT '))
    yield 'missing_output', '\n'.join(line for line in lines if line != first)
    yield 'producer', change('IRIS_COMPILER_PRODUCER ', 'vector_checksum', lambda x: x ^ 1)
    yield 'counter', change('IRIS_REGION ', 'end_cycle', lambda x: 0)


def run(args):
    suite_path = args.suite.resolve(); suite, load = frozen_suite(suite_path, args.expected_suite_sha256)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    native, uart = args.binary.resolve(), args.uart.resolve()
    rom, dtb = ROOT / 'board/evidence/bootrom.rv64.img', ROOT / 'board/build/iris.dtb'
    inputs = {str(p): sha(p) for p in [native, uart, rom, dtb, suite_path, Path(__file__),
        ROOT / 'zephyr/freeze_heldouts.py', ROOT / 'spike/run_functional.py', ROOT / 'firesim/batch_runner.py']}
    for binary in (native,uart):
        listing=subprocess.check_output(['ldd',str(binary)],text=True)
        if 'not found' in listing:raise ValueError('Missing model runtime library')
        for name in re.findall(r'(?:=>\s*)?(/[^\s]+)',listing):
            path=Path(name)
            if path.is_file():inputs[str(path.resolve())]=sha(path)
    (out/'inputs').mkdir()
    for name,value in inputs.items():
        destination=out/'inputs'/value
        if not destination.exists():shutil.copyfile(name,destination)
        if sha(destination)!=value:raise ValueError('Execution input changed during snapshot')
    report = {'schema': 'iris.frozen_heldout_functional_check.v1', 'status': 'running',
        'suite_sha256': args.expected_suite_sha256, 'seed': args.seed, 'binary_sha256': sha(native),
        'uart_sha256': sha(uart), 'input_sha256': inputs, 'runs': [], 'hardware_contacted': False,
        'calibration_usable': False, 'timing_accuracy_certified': False, 'fitting_allowed': False,
        'counter_scope': 'Raw program-visible functional compatibility counters only; no detailed timing model selected',
        'real_reference_or_detailed_model_timings_observed': False}
    (out / 'suite-manifest.json').write_bytes(suite_path.read_bytes())
    for case in suite['cases']:
        golden, region_cases = load(case['golden']), load(case['cases_manifest'])
        for artifact in case['variants']:
            name = case['case_id'] + '-' + artifact['kind']; directory = out / name; directory.mkdir()
            elf = directory / 'guest.elf'; shutil.copyfile(suite_path.parent / artifact['elf_object'], elf)
            if sha(elf) != artifact['elf_sha256']:
                raise ValueError('Frozen held-out ELF changed')
            argv = command(native, elf)
            argv = ['--extlib=' + str(uart) if arg.startswith('--extlib=') else arg for arg in argv]
            argv[-1:-1] = ['--iris-bootrom=' + str(rom), '--dtb=' + str(dtb), '--iris-schedule-seed=' + str(args.seed)]
            fatal = symbols(elf)
            env = dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:' + os.environ.get('PATH', ''),
                IRIS_FATAL_PCS=','.join(hex(value) for key, value in fatal.items() if key in
                    ('z_fatal_error', 'z_riscv_fatal_error', 'k_sys_fatal_error_handler', 'arch_system_halt', 'abort')))
            row = {'case_id': case['case_id'], 'variant': artifact['kind'], 'argv': argv,
                   'elf_sha256': artifact['elf_sha256'], 'functional_checks_passed': False}
            started = time.monotonic()
            with (directory / 'stdout').open('wb') as stdout, (directory / 'stderr').open('wb') as stderr:
                try:
                    result = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr, timeout=args.timeout)
                    row['exit_status'] = result.returncode
                except subprocess.TimeoutExpired:
                    row.update(exit_status=None, timed_out=True)
            row.update(host_seconds=time.monotonic() - started, stdout_sha256=sha(directory / 'stdout'), stderr_sha256=sha(directory / 'stderr'))
            try:
                if row['exit_status'] != 0:
                    raise ValueError('Guest failed/timed out; preserve both raw streams')
                text = (directory / 'stdout').read_text()
                row.update(validate(text, case, artifact['kind'], golden, region_cases, artifact['elf_sha256']))
                refused = []
                for corruption, damaged in corruptions(text):
                    try:
                        validate(damaged, case, artifact['kind'], golden, region_cases, artifact['elf_sha256'])
                    except (ValueError, KeyError, TypeError):
                        refused.append(corruption)
                    else:
                        raise ValueError('Corrupt held-out evidence accepted: ' + corruption)
                row['adversarial_refusals'] = refused
            except (ValueError, KeyError, TypeError, UnicodeError) as error:
                row.update(functional_checks_passed=False, error=str(error))
            (directory / 'result.json').write_text(json.dumps(row, indent=2) + '\n'); report['runs'].append(row)
            report['status'] = 'running' if row['functional_checks_passed'] else 'failed'
            (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            if not row['functional_checks_passed']:
                return report
    for name, value in inputs.items():
        if sha(name) != value:
            raise ValueError('Held-out functional execution input changed: ' + name)
    report['status'] = 'passed_functional_only'
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--suite', type=Path, default=ROOT / 'build/frozen-heldouts-zephyr-v2/manifest.json')
    parser.add_argument('--expected-suite-sha256', default=EXPECTED_SUITE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--binary', type=Path, default=ROOT / 'build/combined-candidate-35901887/spike')
    parser.add_argument('--uart', type=Path, default=ROOT / 'build/combined-candidate-35901887/libsifive_uart.so')
    parser.add_argument('--seed', type=int, default=0); parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    if args.seed < 0 or args.timeout <= 0:
        parser.error('Nonnegative seed and positive timeout required')
    report = run(args); print(json.dumps({'status': report['status'], 'runs': len(report['runs']), 'hardware_contacted': False}))
    return 0 if report['status'] == 'passed_functional_only' else 1


if __name__ == '__main__':
    raise SystemExit(main())
