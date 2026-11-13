#!/usr/bin/env python3
"""Execute eight preserved compiler ELFs on one exact private native capsule."""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ('capsule', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-capsule-sha256', required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--timeout', type=int, default=360)
    parser.add_argument('--input', type=Path, action='append', default=[])
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or args.timeout <= 0:
        parser.error('Require 1..4 independent workers and a positive per-ELF bound')
    out, capsule, fixture = [path.resolve() for path in (args.output, args.capsule, args.fixture)]
    out.mkdir(parents=True, exist_ok=False)
    manifest = capsule / 'manifest.json'
    if sha(manifest) != args.expected_capsule_sha256:
        raise ValueError('Exact approved composite capsule required')
    native = capsule / 'spike'
    uart = capsule / 'libsifive_uart.so'
    meta = json.loads(manifest.read_text())
    if sha(native) != meta['binary_sha256'] or sha(uart) != meta['uart_sha256']:
        raise ValueError('Exact paired composite native/UART required')
    for name, digest in meta['artifact_sha256'].items():
        if sha(capsule / name) != digest:
            raise ValueError('Frozen capsule changed: ' + name)
    validator_file = ROOT / 'integration/iris-mlir/examples/iris/run.py'
    validator = load('composite_preserved_compiler_validator', validator_file)
    fatal_file = ROOT / 'spike/empirical_launch_v2.py'
    fatal = load('composite_fatal_elf_helper', fatal_file)
    inputs = {str(path): sha(path) for path in [Path(__file__).resolve(), manifest, native, uart,
                                               fixture, validator_file, fatal_file,
                                               *[path.resolve() for path in args.input]]}
    tasks = []
    for op in ('gemm', 'conv2d'):
        for workers in (1, 2):
            old_dir = ROOT / f'build/hybrid7bd5-selected-merlin-{op}-h{workers}-v1'
            receipt = old_dir / 'results.json'
            old = json.loads(receipt.read_text())
            if old['pass'] is not True or len(old['runs']) != 2:
                raise ValueError('Both preserved compiler images must have prior functional qualification')
            inputs[str(receipt)] = sha(receipt)
            m, n, k = old['shape_mnk']
            expected_i32, expected_w8 = validator.inputs_and_golden(op, m, n, k)
            for previous in old['runs']:
                elf = Path(previous['argv'][-1]).resolve()
                if sha(elf) != previous['elf_sha256']:
                    raise ValueError('Preserved compiler ELF changed')
                inputs[str(elf)] = sha(elf)
                tasks.append((op, workers, m, n, k, previous, elf, expected_i32, expected_w8))
    if len(tasks) != 8:
        raise ValueError('Exactly eight numerical gates required')
    report = {'schema': 'iris.composite_preserved_compiler_eight_gates.v1', 'pass': False,
              'status': 'running', 'cases': [], 'input_sha256': inputs, 'workers': args.workers,
              'per_ELF_timeout_seconds': args.timeout, 'hardware_contacted': False,
              'fresh_compiler_invocation': False, 'timing_parameters_fitted': False,
              'protected_timing_labels_consumed': False, 'full_model_or_timing_certified': False}
    lock = threading.Lock()

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    save()
    started = time.monotonic()

    def execute(task):
        op, workers, m, n, k, previous, elf, expected_i32, expected_w8 = task
        name = f'{op}-h{workers}-{previous["kind"]}'
        directory = out / name
        directory.mkdir()
        argv = [str(native), *previous['argv'][1:]]
        argv = ['--extlib=' + str(uart) if value.startswith('--extlib=') else
                '--iris-timing-fixture=' + str(fixture) if value.startswith('--iris-timing-fixture=') else value
                for value in argv if not value.startswith('--iris-timing-trace=')]
        argv.insert(-1, '--iris-timing-trace=' + str(directory / 'summary.json'))
        for value in argv:
            if value.startswith(('--iris-bootrom=', '--dtb=')):
                path = Path(value.split('=', 1)[1])
                with lock:
                    inputs[str(path)] = sha(path)
        env = {name: value for name, value in os.environ.items()
               if not name.startswith('IRIS_EMPIRICAL_') and name != 'IRIS_FATAL_PCS'}
        env['IRIS_EMPIRICAL_FEATURES'] = str(directory / 'features.jsonl')
        addresses = sorted(set(fatal.fatal_addresses(elf).values()))
        env['IRIS_FATAL_PCS'] = ','.join(hex(value) for value in addresses)
        row = {'name': name, 'op': op, 'workers': workers, 'kind': previous['kind'], 'shape_mnk': [m, n, k],
               'argv': argv, 'ELF_sha256': sha(elf), 'fatal_PCs': addresses, 'pass': False}
        child = None
        begin = time.monotonic()
        try:
            with (directory / 'stdout').open('wb') as stdout, (directory / 'stderr').open('wb') as stderr:
                child = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
                row['owned_pid'] = child.pid
                (directory / 'invocation.json').write_text(json.dumps(row, indent=2) + '\n')
                try:
                    row['exit_status'] = child.wait(timeout=args.timeout)
                    row['timed_out'] = False
                except subprocess.TimeoutExpired:
                    row['timed_out'] = True
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                    row['exit_status'] = child.returncode
            if row['timed_out'] or row['exit_status'] != 0:
                raise ValueError('Actual ELF failed or reached its explicit bound')
            text = (directory / 'stdout').read_text()
            parsed = validator.parse(text, m * n)
            if parsed['ACC_I32'] != expected_i32 or parsed['OUT'] != expected_w8:
                raise ValueError('Independent all-word int32/W8A8 golden mismatch')
            regions = [list(map(int, line.split()[1:])) for line in text.splitlines() if line.startswith('REGION ')]
            if sorted(row[0] for row in regions) != list(range(workers)) or any(
                    len(row) != 4 or row[2] <= row[1] or row[3] <= 0 for row in regions):
                raise ValueError('Every active physical compute hart needs its actual CSR region')
            row.update(pass_=True, normal_guest_exit=True, accumulator_words=len(expected_i32),
                       w8a8_words=len(expected_w8), regions=regions)
        except Exception as error:
            row['error'] = str(error)
        finally:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            row['pass'] = row.pop('pass_', False)
            row['host_seconds'] = time.monotonic() - begin
            row['output_sha256'] = {str(path): sha(path) for path in directory.iterdir() if path.is_file()}
            (directory / 'report.json').write_text(json.dumps(row, indent=2) + '\n')
            with lock:
                report['cases'].append(row)
                save()
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        list(executor.map(execute, tasks))
    report['cases'].sort(key=lambda row: row['name'])
    report['host_seconds'] = time.monotonic() - started
    changed = [name for name, digest in inputs.items() if sha(Path(name)) != digest]
    report['pass'] = not changed and len(report['cases']) == 8 and all(row['pass'] for row in report['cases'])
    report['status'] = 'all_eight_preserved_images_and_full_numerics_passed' if report['pass'] else 'failed'
    report['changed_inputs'] = changed
    save()
    print(json.dumps({'pass': report['pass'], 'cases': len(report['cases']),
                      'host_seconds': report['host_seconds'], 'report_sha256': sha(out / 'report.json')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
