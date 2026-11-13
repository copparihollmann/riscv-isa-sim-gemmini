#!/usr/bin/env python3
"""Build and freeze a three-hart scalar BF16 decode batch; no hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

from cases import corpus

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    data = corpus()
    (out / 'corpus.json').write_text(json.dumps(data, indent=2) + '\n')
    rows = []
    for c in data['cases']:
        rows.append('{' + json.dumps(c['case_id']) + ',' + json.dumps(c['parent_case_id']) + ','
                    + ','.join(str(c[k]) for k in ('kind', 'rm', 'pattern', 'trial_id', 'instruction'))
                    + ',' + str(c['operand_bits']) + 'ULL,' + str(c['expected_checksums']['0']) + 'ULL}')
    (out / 'cases.inc').write_text('static const case_t cases[]={\n' + ',\n'.join(rows) + '\n};\n')
    cc = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    flags = ['-O2', '-g', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
             '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-fno-common', '-mcmodel=medany',
             '-mabi=lp64d', '-march=rv64gcv_zicsr_zifencei', '-save-temps=obj',
             '-I' + str(ROOT / 'benchmarks'), '-I' + str(out)]
    commands = []
    inputs = [Path(__file__).resolve(), Path(__file__).with_name('cases.py'),
              ROOT / 'spike/scalar-bf16-decoder-proof.json', ROOT / 'hardware/manifest.json', cc,
              ROOT / 'benchmarks/link.ld']
    for name, source, defines in [
            ('start', ROOT / 'benchmarks/start.S', []),
            ('runtime', ROOT / 'benchmarks/runtime.c', ['-Dtrap_dispatch=base_trap_dispatch']),
            ('guest', Path(__file__).with_name('guest.c'), [])]:
        argv = [str(cc), *flags, *defines, '-MD', '-MF', str(out / (name + '.d')),
                '-c', str(source), '-o', str(out / (name + '.o'))]
        result = subprocess.run(argv, capture_output=True)
        (out / (name + '.stdout')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        commands.append({'argv': argv, 'exit_status': result.returncode})
        if result.returncode:
            raise RuntimeError('Compilation failed; raw evidence retained: ' + name)
        dependencies = (out / (name + '.d')).read_text().replace('\\\n', ' ').split(':', 1)[1]
        inputs += [Path(s) for s in shlex.split(dependencies)]
    elf = out / 'probe.elf'
    argv = [str(cc), *flags, '-nostdlib', '-static', '-Wl,--build-id=none',
            '-Wl,-Map,' + str(out / 'link.map'), '-T', str(ROOT / 'benchmarks/link.ld'),
            *[str(out / (name + '.o')) for name in ('start', 'runtime', 'guest')],
            '-lgcc', '-o', str(elf)]
    result = subprocess.run(argv, capture_output=True)
    (out / 'link.stdout').write_bytes(result.stdout)
    (out / 'link.stderr').write_bytes(result.stderr)
    commands.append({'argv': argv, 'exit_status': result.returncode})
    if result.returncode:
        raise RuntimeError('Link failed; raw evidence retained')
    for tool in ('cc1', 'as', 'collect2', 'ld'):
        name = subprocess.check_output([str(cc), '-print-prog-name=' + tool], text=True).strip()
        inputs.append(Path(name if '/' in name else shutil.which(name)).resolve())
    inputs.append(Path(subprocess.check_output([str(cc), '-print-libgcc-file-name'], text=True).strip()))
    inputs = sorted({p.resolve() for p in inputs if out not in p.resolve().parents})
    hashes = {str(p): digest(p) for p in inputs}
    snapshots = out / 'input-snapshot'
    snapshots.mkdir()
    for name, expected in hashes.items():
        destination = snapshots / expected
        if not destination.exists():
            shutil.copyfile(name, destination)
        if digest(destination) != expected or digest(name) != expected:
            raise ValueError('Build source changed: ' + name)
    report = {'schema': 'iris.scalar_bf16_probe_build.v1', 'status': 'built',
              'commands': commands, 'elf_sha256': digest(elf),
              'corpus_sha256': digest(out / 'corpus.json'), 'input_sha256': hashes,
              'hardware_contacted': False, 'calibration_usable': False}
    (out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'elf_sha256': report['elf_sha256'], 'regions': data['regions']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output.resolve())
