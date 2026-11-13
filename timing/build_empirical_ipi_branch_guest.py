#!/usr/bin/env python3
"""Build the independent numeric/program-visible RVV time package check."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler', type=Path,
        default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    args = parser.parse_args(); output = args.output.resolve(); compiler = args.compiler.resolve()
    if output.exists(): raise ValueError('Fresh build output required')
    output.mkdir(parents=True)
    inputs = [ROOT / ('benchmarks/' + name) for name in
              ('start.S', 'runtime.c', 'runtime.h', 'uart_drain.h', 'link.ld')]
    inputs += [Path(__file__).resolve(), ROOT / 'timing/empirical_ipi_branch_guest.c', compiler]
    before = {str(p): sha(p) for p in inputs}
    argv = [str(compiler), '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
        '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-ffunction-sections', '-fdata-sections',
        '-fno-common', '-mcmodel=medany', '-mabi=lp64d', '-march=rv64gcv_zicsr_zifencei', '-nostdlib',
        '-static', '-Wl,--build-id=none,--gc-sections', '-DIRIS_HARTS=3', '-I' + str(ROOT / 'benchmarks'),
        '-T', str(ROOT / 'benchmarks/link.ld'), str(ROOT / 'benchmarks/start.S'),
        str(ROOT / 'benchmarks/runtime.c'), str(ROOT / 'timing/empirical_ipi_branch_guest.c'),
        '-lgcc', '-o', str(output / 'guest.elf')]
    got = subprocess.run(argv, capture_output=True)
    (output / 'build.stdout').write_bytes(got.stdout); (output / 'build.stderr').write_bytes(got.stderr)
    unchanged = all(sha(path) == digest for path, digest in before.items())
    report = {'schema': 'iris.empirical_ipi_branch_guest_build.v1', 'argv': argv, 'exit_status': got.returncode,
        'compiler_version': subprocess.check_output([str(compiler), '--version']).decode(),
        'input_sha256': before, 'fitting_usable': False, 'inputs_unchanged': unchanged}
    if got.returncode == 0: report['input_sha256'][str(output / 'guest.elf')] = sha(output / 'guest.elf')
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    if got.returncode != 0 or not unchanged: raise SystemExit(1)
    print(output / 'guest.elf')


if __name__ == '__main__': main()
