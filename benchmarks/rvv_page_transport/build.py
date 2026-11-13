#!/usr/bin/env python3
"""Build one source-frozen page/CSR context-transfer diagnostic; no hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from cases import cases

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=False)
    corpus = cases()
    lines = []
    for c in corpus['cases']:
        values = [json.dumps(c[k]) for k in ('case_id', 'parent_case_id', 'family')]
        values += [str(c[k]) for k in ('crossing_group', 'bytes_before_page', 'input_offset', 'output_offset', 'mode', 'pattern', 'trial_id')]
        values += [str(c['expected_checksums'][2]) + 'ULL']
        lines.append('{' + ','.join(values) + '}')
    (out / 'cases.inc').write_text('static const case_t cases[]={\n' + ',\n'.join(lines) + '\n};\n')
    compiler = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    elf = out / 'probe.elf'
    argv = [str(compiler), '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
        '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-fno-common', '-mcmodel=medany', '-mabi=lp64d',
        '-march=rv64gcv_zicsr_zifencei', '-nostdlib', '-static', '-save-temps=obj', '-Wl,--build-id=none',
        '-Wl,-Map,' + str(out / 'link.map'), '-I' + str(ROOT / 'benchmarks'), '-I' + str(out),
        '-T', str(ROOT / 'benchmarks/link.ld'), str(ROOT / 'benchmarks/start.S'),
        str(ROOT / 'benchmarks/runtime.c'), str(Path(__file__).with_name('guest.c')), '-lgcc', '-o', str(elf)]
    run = subprocess.run(argv, capture_output=True)
    (out / 'build.stdout').write_bytes(run.stdout); (out / 'build.stderr').write_bytes(run.stderr)
    if run.returncode:
        raise RuntimeError('Build failed; raw compiler evidence retained at ' + str(out))
    symbols = subprocess.check_output(['/usr/bin/readelf', '-sW', str(elf)], text=True)
    (out / 'symbols.txt').write_text(symbols)
    layout = {'arena_bytes': 8192, 'alignment': 4096}
    for line in symbols.splitlines():
        fields = line.split()
        if fields and fields[-1] in ('input_arena', 'output_arena'):
            assert int(fields[2]) == 8192
            layout[fields[-1]] = int(fields[1], 16)
    if len(layout) != 4 or any(layout[k] % 4096 for k in ('input_arena', 'output_arena')):
        raise ValueError('Exact page-aligned ELF arena layout missing')
    corpus['layout'] = layout
    (out / 'corpus.json').write_text(json.dumps(corpus, indent=2) + '\n')
    objdump = compiler.with_name('riscv64-unknown-elf-objdump')
    (out / 'disassembly.txt').write_bytes(subprocess.check_output([str(objdump), '-dr', str(elf)]))
    paths = [Path(__file__).resolve(), Path(__file__).with_name('cases.py'), Path(__file__).with_name('guest.c'),
        compiler, objdump, Path('/usr/bin/readelf'), *[ROOT / 'benchmarks' / n for n in
        ('start.S', 'runtime.c', 'runtime.h', 'uart_drain.h', 'link.ld')]]
    for name in ('cc1', 'as', 'collect2', 'ld'):
        path = subprocess.check_output([str(compiler), '-print-prog-name=' + name], text=True).strip()
        paths.append(Path(path).resolve() if '/' in path else Path(shutil.which(path)).resolve())
    for token in re.findall(r'^LOAD\s+(\S+)', (out / 'link.map').read_text(), re.M):
        path = Path(token).resolve()
        if path.is_file() and not path.is_relative_to(out): paths.append(path)
    identities = {str(path.resolve()): sha(path) for path in paths}
    saved = out / 'input-snapshot'; saved.mkdir()
    for name, expected in identities.items():
        if sha(name) != expected: raise ValueError('Build input changed: ' + name)
        if not (saved / expected).exists(): shutil.copyfile(name, saved / expected)
    receipt = {'schema': 'iris.rvv_page_transport_build.v1', 'status': 'built', 'argv': argv,
        'elf_sha256': sha(elf), 'corpus_sha256': sha(out / 'corpus.json'), 'layout': layout,
        'input_sha256': identities, 'hardware_contacted': False,
        'artifact_sha256': {str(p.relative_to(out)): sha(p) for p in sorted(out.iterdir()) if p.is_file()}}
    (out / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'elf': str(elf), 'regions': len(corpus['cases']), 'sha256': sha(elf), 'layout': layout}))


if __name__ == '__main__':
    main()
