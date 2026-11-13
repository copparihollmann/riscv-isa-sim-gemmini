#!/usr/bin/env python3
"""Run a fresh three-hart numeric and program-visible timing sensitivity check."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spike.run_functional import command
from benchmarks.validate_console import validate


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def run(native, uart, fixture, sensitivity, output, timeout=90,
        time_guest=ROOT / 'build/empirical-time-guest-v1/guest.elf'):
    paths = [Path(p).resolve() for p in (native, uart, fixture, sensitivity)]
    native, uart, fixture, sensitivity = paths
    if sha(fixture) == sha(sensitivity): raise ValueError('Distinct sensitivity fixture required')
    output = Path(output).resolve()
    if output.exists(): raise ValueError('Fresh selftest output required')
    output.mkdir(parents=True)
    elf = ROOT / 'benchmarks/build/smoke.elf'
    rom = ROOT / 'board/evidence/bootrom.rv64.img'; dtb = ROOT / 'board/build/iris.dtb'
    corpus = ROOT / 'benchmarks/calibration-corpus.json'
    time_guest = Path(time_guest).resolve(); time_build = time_guest.with_name('build.json')
    built = json.loads(time_build.read_text())
    if built.get('schema') != 'iris.empirical_time_guest_build.v1' or built.get('exit_status') != 0:
        raise ValueError('Built independent three-hart timing guest required')
    if built['input_sha256'].get(str(time_guest)) != sha(time_guest):
        raise ValueError('Timing guest identity changed')
    for path, expected in built['input_sha256'].items():
        if sha(path) != expected: raise ValueError('Timing guest source/build input changed: ' + path)
    sources = [Path(__file__).resolve(), ROOT / 'spike/run_functional.py',
               ROOT / 'benchmarks/validate_console.py', corpus, elf, rom, dtb, time_guest, time_build,
               *map(Path, built['input_sha256']), *paths]
    before = {str(p): sha(p) for p in sources}; records = []
    for name, selected, guest in [('smoke', fixture, elf), ('selected', fixture, time_guest),
                                  ('sensitivity', sensitivity, time_guest)]:
        folder = output / name; folder.mkdir()
        argv = command(native, guest)
        argv = ['--extlib=' + str(uart) if a.startswith('--extlib=') else a for a in argv]
        argv = argv[:-1] + ['--iris-bootrom=' + str(rom), '--dtb=' + str(dtb),
            '--iris-timing-fixture=' + str(selected),
            '--iris-timing-trace=' + str(folder / 'native-summary.json')] + argv[-1:]
        env = dict(os.environ, IRIS_EMPIRICAL_FEATURES=str(folder / 'features.jsonl'))
        started = time.monotonic(); timed_out = False
        try:
            got = subprocess.run(argv, capture_output=True, env=env, timeout=timeout)
            stdout, stderr, code = got.stdout, got.stderr, got.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code = error.stdout or b'', error.stderr or b'', None
            timed_out = True
        elapsed = time.monotonic() - started
        (folder / 'stdout').write_bytes(stdout); (folder / 'stderr').write_bytes(stderr)
        marker = 'IRIS_REGION ' if name == 'smoke' else 'IRIS_TIME_SENSITIVITY '
        rows = [json.loads(line.split(' ', 1)[1]) for line in stdout.decode().splitlines()
                if line.startswith(marker)]
        validation_error = None; checked = None
        try:
            if name == 'smoke':
                checked = validate(stdout.decode(), json.loads(corpus.read_text()), 3, True)
            else:
                done = [json.loads(line.split(' ', 1)[1]) for line in stdout.decode().splitlines()
                        if line.startswith('IRIS_TIME_DONE ')]
                if (len(rows) != 3 or {r['hart'] for r in rows} != {0, 1, 2}
                        or done != [{'failed': 0}]
                        or any(r['vl'] != 8 or r['checksum'] != 280 or r['failed'] != 0 for r in rows)):
                    raise ValueError('Timing guest must check all24 words against independent value35')
                checked = {'harts': [0, 1, 2], 'checked_words': 24, 'expected_element': 35,
                           'functional_checks_passed': True}
        except (ValueError, TypeError, KeyError) as error: validation_error = str(error)
        summary_path = folder / 'native-summary.json'
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
        retired = summary.get('retired_instructions')
        record = {'name': name, 'argv': argv, 'exit_status': code, 'timed_out': timed_out,
            'host_elapsed_seconds': elapsed, 'independent_validation': checked,
            'validation_error': validation_error, 'regions': rows,
            'retired_instructions': retired,
            'simulated_MIPS': sum(retired) / elapsed / 1e6 if isinstance(retired, list) else None,
            'pass': code == 0 and checked is not None and len(rows) == (12 if name == 'smoke' else 3)
                and {r['hart'] for r in rows} == {0, 1, 2},
            'output_sha256': {str(p): sha(p) for p in folder.iterdir() if p.is_file()}}
        (folder / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
        records.append(record)
    a, b = [{r['hart']: r for r in record['regions']} for record in records[1:]]
    controls = []
    for key in sorted(set(a) & set(b)):
        x, y = a[key], b[key]
        controls.append({'case_id': 'package-independent-rvv32', 'hart': key,
            'same_instret': x['instret_delta'] == y['instret_delta'],
            'selected_cycles': (x['end_cycle'] - x['start_cycle']) & ((1 << 64) - 1),
            'perturbed_cycles': (y['end_cycle'] - y['start_cycle']) & ((1 << 64) - 1)})
    changed_harts = {r['hart'] for r in controls if r['same_instret'] and
                     r['selected_cycles'] != r['perturbed_cycles']}
    unchanged_inputs = all(sha(path) == digest for path, digest in before.items())
    numeric = all(r['pass'] for r in records)
    sensitivity_pass = changed_harts == {0, 1, 2}
    report = {'schema': 'iris.empirical_package_selftest.v1',
        'pass': numeric and sensitivity_pass and unchanged_inputs,
        'native_binary_sha256': sha(native), 'uart_library_sha256': sha(uart),
        'fixture_sha256': sha(fixture), 'sensitivity_fixture_sha256': sha(sensitivity),
        'three_harts_numerically_verified': numeric,
        'modeled_time_sensitivity_verified': sensitivity_pass,
        'unchanged_inputs_after_execution': unchanged_inputs, 'controls': controls,
        'runs': records, 'input_sha256': before,
        'functional_scope': '12-region scalar smoke plus three-hart RVV timed work, all independently checked',
        'accuracy_2percent_certified': False, 'rtl_certified': False}
    report['evidence_sha256'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ('native', 'uart', 'fixture', 'sensitivity-fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--time-guest', type=Path, default=ROOT / 'build/empirical-time-guest-v1/guest.elf')
    args = parser.parse_args()
    report = run(args.native, args.uart, args.fixture, args.sensitivity_fixture, args.output,
                 args.timeout, args.time_guest)
    print(json.dumps({'pass': report['pass'], 'output': str(args.output)}))
    if not report['pass']: raise SystemExit(1)


if __name__ == '__main__': main()
