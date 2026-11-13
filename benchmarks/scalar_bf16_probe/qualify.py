#!/usr/bin/env python3
"""Run the exact scalar BF16 batch on the frozen functional package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from validate import validate

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from spike.run_functional import command


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(build, out, seed):
    receipt = json.loads((build / 'build.json').read_text())
    elf = build / 'probe.elf'
    if receipt['status'] != 'built' or digest(elf) != receipt['elf_sha256']:
        raise ValueError('Exact successful build required')
    if digest(build / 'corpus.json') != receipt['corpus_sha256']:
        raise ValueError('Built corpus changed')
    for name, expected in receipt['input_sha256'].items():
        if digest(name) != expected:
            raise ValueError('Build input changed: ' + name)
    out.mkdir(parents=True, exist_ok=False)
    native = (ROOT / 'spike/bin/spike-iris-functional').resolve()
    uart = (ROOT / 'spike/bin/libsifive_uart.so').resolve()
    rom, dtb = ROOT / 'board/evidence/bootrom.rv64.img', ROOT / 'board/build/iris.dtb'
    argv = command(native, elf)
    argv = [('--extlib=' + str(uart)) if word.startswith('--extlib=') else word for word in argv]
    argv = argv[:-1] + ['--iris-bootrom=' + str(rom), '--dtb=' + str(dtb),
                        '--iris-schedule-seed=' + str(seed)] + argv[-1:]
    paths = [Path(__file__), Path(__file__).with_name('validate.py'), Path(__file__).with_name('cases.py'),
             build / 'build.json', build / 'corpus.json', elf, native, uart, rom, dtb,
             ROOT / 'spike/run_functional.py']
    identities = dict(receipt['input_sha256'])
    identities.update({str(p.resolve()): digest(p) for p in paths})
    saved = out / 'inputs'
    saved.mkdir()
    for name, expected in identities.items():
        if not (saved / expected).exists():
            shutil.copyfile(name, saved / expected)
    env = dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:' + os.environ['PATH'])
    started = time.monotonic()
    result = subprocess.run(argv, env=env, capture_output=True, timeout=120)
    (out / 'stdout').write_bytes(result.stdout)
    (out / 'stderr').write_bytes(result.stderr)
    shutil.copyfile(build / 'corpus.json', out / 'corpus.json')
    record = {'schema': 'iris.scalar_bf16_functional_gate.v1', 'seed': seed, 'argv': argv,
              'returncode': result.returncode, 'host_seconds': time.monotonic()-started,
              'elf_sha256': digest(elf), 'corpus_sha256': digest(out / 'corpus.json'),
              'input_sha256': identities, 'stdout_sha256': digest(out / 'stdout'),
              'stderr_sha256': digest(out / 'stderr'), 'hardware_contacted': False,
              'timing_certified': False, 'calibration_usable': False}
    try:
        if result.returncode:
            raise ValueError('Guest exited nonzero: ' + result.stderr.decode(errors='replace')[-1000:])
        record['proof'] = validate(result.stdout.decode(), json.loads((out / 'corpus.json').read_text()), elf)
        if any(digest(name) != expected for name, expected in identities.items()):
            raise ValueError('Inputs changed during qualification')
        record['pass'] = True
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        record.update({'pass': False, 'error': str(error)})
    (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: record.get(k) for k in ('pass', 'proof', 'error', 'host_seconds')}))
    return 0 if record['pass'] else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, required=True)
    a = p.parse_args()
    raise SystemExit(run(a.build.resolve(), a.output.resolve(), a.seed))
