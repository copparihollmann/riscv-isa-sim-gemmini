#!/usr/bin/env python3
"""Qualify the derived Zephyr training ELF without hardware or held-out timing."""
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
from spike.run_functional import command, symbols
from firesim_fit_validate import corpus, validate
from uart_profiles import check_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify(build, output, trials=5, seed=0):
    proof = json.loads((build / 'build.json').read_text())
    elf = build / 'zephyr/zephyr.elf'
    if proof['status'] != 'built' or sha(elf) != proof['elf_sha256']:
        raise ValueError('Exact successful Zephyr build required')
    for name, expected in proof['input_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Build input changed: ' + name)
    if proof.get('uart_profile', {}).get('name') != 'ethan-firesim':
        raise ValueError('Exact Ethan UART deployment profile required')
    output.mkdir(parents=True, exist_ok=False)
    specification = corpus(trials)
    encoded = json.dumps(specification, indent=2) + '\n'
    (output / 'corpus.json').write_text(encoded)
    native = (ROOT / 'spike/bin/spike-iris-functional').resolve()
    uart = (ROOT / 'spike/bin/libsifive_uart.so').resolve()
    rom, dtb = ROOT / 'board/evidence/bootrom.rv64.img', ROOT / 'board/build/iris.dtb'
    table = symbols(elf)
    fatal = [table[name] for name in ('z_fatal_error', 'z_riscv_fatal_error') if name in table]
    if len(fatal) != 2:
        raise ValueError('Both Zephyr fatal handler symbols required')
    argv = command(native, elf)
    argv = [('--extlib=' + str(uart)) if word.startswith('--extlib=') else word for word in argv]
    argv = argv[:-1] + ['--iris-bootrom=' + str(rom), '--dtb=' + str(dtb),
                        '--iris-schedule-seed=' + str(seed)] + argv[-1:]
    compiler = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    libgcc = Path(subprocess.check_output([str(compiler), '-print-libgcc-file-name'], text=True).strip())
    inputs = [Path(__file__).resolve(), Path(__file__).with_name('firesim_fit_validate.py'),
              build / 'build.json', native, uart, elf, rom, dtb, compiler, libgcc,
              ROOT / 'spike/run_functional.py', ROOT / 'hardware/manifest.json',
              ROOT / 'hardware/dtypes.json', ROOT / 'zephyr/uart-profiles.json']
    identities = {str(path): sha(path) for path in inputs}
    saved = output / 'inputs'
    saved.mkdir()
    for path, expected in identities.items():
        target = saved / expected
        if not target.exists():
            target.write_bytes(Path(path).read_bytes())
    env = dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:' + os.environ['PATH'],
               IRIS_FATAL_PCS=','.join(hex(pc) for pc in fatal))
    before = time.monotonic()
    run = subprocess.run(argv, env=env, capture_output=True, timeout=180)
    elapsed = time.monotonic() - before
    (output / 'stdout').write_bytes(run.stdout)
    (output / 'stderr').write_bytes(run.stderr)
    result = {'schema': 'iris.zephyr_fpga_training_functional_gate.v1', 'argv': argv,
              'returncode': run.returncode, 'host_seconds': elapsed, 'seed': seed,
              'elf_sha256': sha(elf), 'native_sha256': sha(native), 'uart_sha256': sha(uart),
              'corpus_sha256': sha(output / 'corpus.json'), 'input_sha256': identities,
              'stdout_sha256': sha(output / 'stdout'), 'stderr_sha256': sha(output / 'stderr'),
              'hardware_contacted': False, 'timing_calibrated': False, 'heldout': False}
    try:
        if run.returncode:
            raise ValueError('Native guest failed: ' + run.stderr.decode(errors='replace')[-1500:])
        text = run.stdout.decode()
        result['proof'] = validate(text, specification)
        result['uart_readback'] = check_report(text.splitlines(), 'ethan-firesim')
        if any(sha(path) != expected for path, expected in identities.items()):
            raise ValueError('Functional gate inputs changed during execution')
        result['pass'] = True
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        result.update(pass_=False, error=str(error))
        result['pass'] = False
    (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=5)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    result = qualify(args.build.resolve(), args.output.resolve(), args.trials, args.seed)
    print(json.dumps({key: result.get(key) for key in ('pass', 'proof', 'error', 'host_seconds')}))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
