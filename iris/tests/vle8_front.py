#!/usr/bin/env python3
"""Run 18 byte-knownness, fallback, fault and pending-IPI VLE8 tests. No FPGA."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess

from native_test_support import descriptor, run_checked, sha
from vle8_front_cases import CASES, assembly

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--riscv-gcc', type=Path, required=True)
    parser.add_argument('--dtc', type=Path, default=shutil.which('dtc'))
    parser.add_argument('--profile', choices=('source_compute', 'source_os'), default='source_compute')
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.dtc is None:
        parser.error('Pass --dtc or add the matching SDK dtc to PATH')
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 3600:
        parser.error('A finite timeout between zero and 3600 seconds is required')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    model = descriptor(args.build.resolve() / args.profile / 'manifest.json')
    original = next(Path(a.split('=', 1)[1]) for a in model['launch_args']
                    if a.startswith('--iris-timing-fixture='))
    fixture = out / 'vle8.fixture'
    fixture.write_bytes(original.read_bytes() +
                        b'\nempirical_vle8_front single-row-e8m1-scalar-only-v1\n')
    linker = out / 'test.ld'
    linker.write_text((HERE / 'speculative_fetch.ld').read_text().replace(
        '  /DISCARD/', '  . = 0x80003000;\n  .data : { *(.data) } :writable\n  /DISCARD/'))
    compiler = args.riscv_gcc.resolve()
    sources = [Path(__file__).resolve(), HERE / 'vle8_front_cases.py',
               HERE / 'speculative_fetch.ld', compiler, linker]
    inputs = {str(path): sha(path) for path in sources}
    records = []
    for case in CASES:
        directory = out / case['name']
        directory.mkdir()
        source = directory / 'test.S'
        source.write_text(assembly(case))
        elf = directory / 'test.elf'
        argv = [str(compiler), '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mno-relax',
                '-nostdlib', '-nostartfiles', '-static', '-Wl,--no-relax',
                '-I' + str(HERE.parents[1] / 'riscv'), '-Wl,-T,' + str(linker),
                str(source), '-o', str(elf)]
        built = subprocess.run(argv, capture_output=True, timeout=args.timeout)
        (directory / 'compile.stdout').write_bytes(built.stdout)
        (directory / 'compile.stderr').write_bytes(built.stderr)
        row = dict(case=case, passed=False, compiler_argv=argv, compile_exit=built.returncode)
        if built.returncode == 0:
            run = directory / 'run'
            receipt = run_checked(model, elf, run, fixture=fixture, timeout=args.timeout,
                                  inputs={**inputs, str(source): sha(source)}, dtc=args.dtc.resolve())
            summary = json.loads((run / 'summary.json').read_text()) if (run / 'summary.json').exists() else {}
            metrics = summary.get('single_vle8_front', {}).get('per_hart', [{}])[0]
            stderr = (run / 'stderr').read_text(errors='replace') if (run / 'stderr').exists() else ''
            expected = 1 if case.get('refuses') else 0
            passed = (receipt.get('exit_status') == expected and not receipt['timed_out']
                      and receipt['inputs_unchanged'] and receipt['error'] is None)
            if expected:
                passed = passed and any(marker in stderr for marker in (
                    'IRIS_UNDEFINED_STATE', 'IRIS_FRONTEND_UNDEFINED_BRANCH_OPERANDS_UNMODELED'))
            else:
                passed = passed and metrics.get('accepted') == case['admitted'] and metrics.get('pending') == 0
            if case.get('irq'):
                passed = passed and metrics.get('IRQ_deferred_checks', 0) > 0
            row.update(passed=bool(passed), ELF_sha256=sha(elf), metrics=metrics,
                       exit_status=receipt.get('exit_status'), raw_receipt=str(run / 'run.json'))
        records.append(row)
        print(case['name'], row['passed'], flush=True)
    report = dict(schema='iris.single_vle8_front.directed.v2', passed=all(r['passed'] for r in records),
                  records=records, cases=len(records), input_sha256=inputs,
                  hardware_contacted=False, timing_accuracy_certified=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
