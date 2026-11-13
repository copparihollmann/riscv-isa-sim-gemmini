#!/usr/bin/env python3
"""Execute exact page/CSR transfer ELF with independent byte/geometry goldens."""
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__);p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True);p.add_argument('--seed', type=int, default=0)
    a = p.parse_args();build, out = a.build.resolve(), a.output.resolve()
    proof = json.loads((build / 'build.json').read_text());elf = build / 'probe.elf'
    if proof['status'] != 'built' or sha(elf) != proof['elf_sha256'] or sha(build/'corpus.json') != proof['corpus_sha256']:
        raise ValueError('Exact successful build required')
    for name, expected in proof['input_sha256'].items():
        if sha(name) != expected:
            raise ValueError('Build input changed: ' + name)
    out.mkdir(parents=True, exist_ok=False)
    native = (ROOT / 'spike/bin/spike-iris-functional').resolve()
    uart = (ROOT / 'spike/bin/libsifive_uart.so').resolve()
    rom, dtb = ROOT / 'board/evidence/bootrom.rv64.img', ROOT / 'board/build/iris.dtb'
    argv = command(native, elf)
    argv = [('--extlib=' + str(uart)) if word.startswith('--extlib=') else word for word in argv]
    argv = argv[:-1] + ['--iris-bootrom=' + str(rom), '--dtb=' + str(dtb),
                        '--iris-schedule-seed=' + str(a.seed)] + argv[-1:]
    paths = [Path(__file__), Path(__file__).with_name('validate.py'), build / 'build.json', build / 'corpus.json',
             elf, native, uart, rom, dtb, ROOT / 'spike/run_functional.py', ROOT / 'hardware/manifest.json']
    identities = dict(proof['input_sha256']);identities.update({str(p.resolve()): sha(p) for p in paths})
    saved = out / 'inputs';saved.mkdir()
    for name, expected in identities.items():
        if not (saved / expected).exists():
            shutil.copyfile(name, saved / expected)
    env = dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:' + os.environ['PATH'])
    start = time.monotonic();run = subprocess.run(argv, env=env, capture_output=True, timeout=120)
    (out / 'stdout').write_bytes(run.stdout);(out / 'stderr').write_bytes(run.stderr)
    shutil.copyfile(build / 'corpus.json', out / 'corpus.json')
    result = {'schema': 'iris.rvv_page_transport_functional_gate.v1', 'argv': argv, 'seed': a.seed,
              'returncode': run.returncode, 'host_seconds': time.monotonic() - start,
              'elf_sha256': sha(elf), 'native_sha256': sha(native), 'uart_sha256': sha(uart),
              'input_sha256': identities, 'corpus_sha256': sha(out / 'corpus.json'),
              'stdout_sha256': sha(out / 'stdout'), 'stderr_sha256': sha(out / 'stderr'),
              'hardware_contacted': False, 'timing_certified': False, 'heldout': False}
    try:
        if run.returncode:
            raise ValueError('Guest failed: ' + run.stderr.decode(errors='replace')[-1000:])
        result['proof'] = validate(run.stdout.decode(), json.loads((out / 'corpus.json').read_text()))
        if any(sha(name) != expected for name, expected in identities.items()):
            raise ValueError('Gate inputs changed during execution')
        result['pass'] = True
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        result.update(error=str(error));result['pass'] = False
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result.get(key) for key in ('pass', 'proof', 'error', 'host_seconds')}))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
