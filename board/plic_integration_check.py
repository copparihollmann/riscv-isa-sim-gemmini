#!/usr/bin/env python3
"""Run ordinary PLIC guest ELFs; do not mutate the shared native Spike build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spike.run_functional import command


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'build/timing-live/spike')
    parser.add_argument('--uart', type=Path, default=ROOT / 'build/timing-live/libsifive_uart.so')
    parser.add_argument('--compiler', type=Path, default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    parser.add_argument('--output', type=Path, default=ROOT / 'build/plic-integration')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--seed', type=int, help='recorded functional hart scheduling seed')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    # Rebuilding or rerunning can invalidate an old success before a later
    # compile failure/timeout. Never leave that receipt presenting stale green.
    (output / 'results.json').unlink(missing_ok=True)
    rom, dtb = ROOT / 'board/evidence/bootrom.rv64.img', ROOT / 'board/build/iris.dtb'
    builds, results = [], []
    runtime = output / 'plic-runtime.o'
    common = [str(args.compiler.resolve()), '-O2', '-g', '-Wall', '-Wextra',
              '-Wno-unused-variable', '-Wno-unused-function', '-Werror',
              '-ffreestanding', '-fno-builtin', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
              '-mcmodel=medany', '-mabi=lp64d', '-march=rv64gcv_zicsr_zifencei',
              '-I' + str(ROOT / 'benchmarks')]
    runtime_build = common + ['-Dtrap_dispatch=base_trap_dispatch', '-c',
                              str(ROOT / 'benchmarks/runtime.c'), '-o', str(runtime)]
    compiled = subprocess.run(runtime_build, text=True, capture_output=True)
    (output / 'build-runtime.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode: raise RuntimeError('PLIC runtime build failed: ' + compiled.stderr)
    builds.append(runtime_build)
    for mode in range(10):
        elf = output / ('plic-' + str(mode) + '.elf')
        build = common + ['-DPLIC_MODE=' + str(mode),
                 '-nostdlib', '-static', '-Wl,--build-id=none,--gc-sections',
                 '-T', str(ROOT / 'benchmarks/link.ld'), str(ROOT / 'benchmarks/start.S'),
                 str(runtime), str(ROOT / 'board/plic_guest.c'),
                 '-lgcc', '-o', str(elf)]
        compiled = subprocess.run(build, text=True, capture_output=True)
        (output / ('build-' + str(mode) + '.log')).write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError('PLIC guest build failed: ' + compiled.stderr)
        builds.append(build)
    if args.build_only:
        print(json.dumps({'status': 'built_only', 'guests': len(builds) - 1})); return 0
    binary_before, uart_before = sha(args.binary), sha(args.uart)
    env = dict(os.environ)
    env['PATH'] = '/scratch/eygao/iris-cy/.conda-env/bin:' + env['PATH']
    for mode in range(10):
        elf = output / ('plic-' + str(mode) + '.elf')
        cmd = command(args.binary.resolve(), elf)
        cmd = ['--extlib=' + str(args.uart.resolve()) if word.startswith('--extlib=') else word for word in cmd]
        if mode != 6:
            cmd = cmd[:-1] + ['--iris-bootrom=' + str(rom), '--dtb=' + str(dtb)] + cmd[-1:]
        if args.seed is not None:
            cmd = cmd[:-1] + ['--iris-schedule-seed=' + str(args.seed)] + cmd[-1:]
        timed_out = False
        try:
            ran = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            def decoded(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            ran = subprocess.CompletedProcess(cmd, 124, decoded(error.stdout), decoded(error.stderr))
        stdout, stderr = output / ('plic-' + str(mode) + '.stdout'), output / ('plic-' + str(mode) + '.stderr')
        stdout.write_text(ran.stdout); stderr.write_text(ran.stderr)
        expected = 'IRIS_PLIC_UNKNOWN_MIP' if mode in (3, 4, 9) else 'Iris PLIC read/effect depends on uninitialized'
        if mode < 5 or mode == 9:
            passed = ran.returncode != 0 and expected in ran.stderr
        elif mode == 5:
            rows = [json.loads(line[len('IRIS_PLIC '):]) for line in ran.stdout.splitlines() if line.startswith('IRIS_PLIC ')]
            passed = (ran.returncode == 0 and len(rows) == 3 and {row['hart'] for row in rows} == {0, 1, 2}
                      and all(row['irq_checks'] == 3 for row in rows)
                      and 'PASSED physical PLIC register and interrupt integration' in ran.stdout)
        elif mode == 6:
            passed = ran.returncode == 0 and 'PASSED generic PLIC compatibility' in ran.stdout
        else:
            expected_cause = 9 if mode == 8 else 11
            passed = ran.returncode == 0 and ('PASSED physical PLIC external trap cause ' + str(expected_cause)) in ran.stdout
        results.append({'mode': mode, 'pass': passed and not timed_out, 'exit_status': ran.returncode,
                        'timed_out': timed_out,
                        'argv': cmd, 'elf_sha256': sha(elf), 'stdout_sha256': sha(stdout),
                        'stderr_sha256': sha(stderr), 'physical_boot': mode != 6})
    stable_inputs = sha(args.binary) == binary_before and sha(args.uart) == uart_before
    passed_all = all(r['pass'] for r in results) and stable_inputs
    record = {'schema_version': 1, 'status': 'passed_process_regressions' if passed_all else 'failed',
              'results': results, 'build_commands': builds, 'binary_sha256': sha(args.binary),
              'seed': args.seed, 'binary_and_uart_unchanged_during_run': stable_inputs,
              'uart_sha256': sha(args.uart), 'compiler_sha256': sha(args.compiler),
              'rom_sha256': sha(rom), 'dtb_sha256': sha(dtb),
              'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in
                  [ROOT / 'board/plic_guest.c', Path(__file__), ROOT / 'board/iris_plic.hpp',
                   ROOT / 'benchmarks/start.S', ROOT / 'benchmarks/runtime.c', ROOT / 'benchmarks/runtime.h',
                   ROOT / 'benchmarks/link.ld', ROOT / 'third_party/riscv-isa-sim/riscv/plic.cc',
                   ROOT / 'third_party/riscv-isa-sim/riscv/devices.h']},
              'rtl_certified': False, 'pipeline_timing_certified': False, 'zephyr_smp_certified': False,
              'limitations': ['UART is used only to assert a source-high condition, not to certify its FIFO timing.',
                              'PLIC registered fan-in/IRQ and TileLink pipeline timing are not calibrated.']}
    (output / 'results.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'tests': len(results), 'artifact': str(output / 'results.json')}))
    return 0 if passed_all else 1


if __name__ == '__main__':
    raise SystemExit(main())
