#!/usr/bin/env python3
"""Build one finite baremetal LMUL1/2/4/8 context-transport diagnostic batch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
from cases import cases

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__);p.add_argument('--output', type=Path, required=True)
    a = p.parse_args();out = a.output.resolve();out.mkdir(parents=True, exist_ok=False)
    corpus = cases();(out / 'corpus.json').write_text(json.dumps(corpus, indent=2) + '\n')
    (out / 'cases.inc').write_text('static const case_t cases[]={\n' + ',\n'.join(
        '{' + json.dumps(c['case_id']) + ',' + json.dumps(c['parent_case_id']) + ',' + ','.join(str(c[k]) for k in ('lmul', 'avl', 'drain', 'trial_id'))
        + ',' + str(c['expected_checksums'][2]) + 'ULL}' for c in corpus['cases']) + '\n};\n')
    compiler = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    elf = out / 'probe.elf'
    argv = [str(compiler), '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
            '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-fno-common', '-mcmodel=medany', '-mabi=lp64d',
            '-march=rv64gcv_zicsr_zifencei', '-nostdlib', '-static', '-Wl,--build-id=none',
            '-I' + str(ROOT / 'benchmarks'), '-I' + str(out), '-T', str(ROOT / 'benchmarks/link.ld'),
            str(ROOT / 'benchmarks/start.S'), str(ROOT / 'benchmarks/runtime.c'),
            str(Path(__file__).with_name('guest.c')), '-lgcc', '-o', str(elf)]
    run = subprocess.run(argv, capture_output=True)
    (out / 'build.stdout').write_bytes(run.stdout);(out / 'build.stderr').write_bytes(run.stderr)
    paths = [Path(__file__), Path(__file__).with_name('cases.py'), Path(__file__).with_name('guest.c'), compiler,
             *[ROOT / 'benchmarks' / n for n in ('start.S', 'runtime.c', 'runtime.h', 'uart_drain.h', 'link.ld')],
             Path(subprocess.check_output([str(compiler), '-print-libgcc-file-name'], text=True).strip())]
    record = {'schema': 'iris.rvv_context_transport_build.v1', 'status': 'built' if run.returncode == 0 else 'failed',
              'argv': argv, 'elf_sha256': sha(elf) if elf.exists() else None,
              'input_sha256': {str(path.resolve()): sha(path) for path in paths}, 'hardware_contacted': False}
    saved=out/'input-snapshot';saved.mkdir()
    for name,digest in record['input_sha256'].items():
        destination=saved/digest
        if not destination.exists():shutil.copyfile(name,destination)
    (out / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
    if run.returncode:
        raise SystemExit(run.stderr.decode())
    print(json.dumps({'elf': str(elf), 'regions': len(corpus['cases']), 'sha256': sha(elf)}))


if __name__ == '__main__':
    main()
