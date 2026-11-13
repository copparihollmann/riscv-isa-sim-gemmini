#!/usr/bin/env python3
"""Build a matrix readout observation and its one-byte silent software input."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess

from cases import corpus

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    (out / 'corpus.json').write_text(json.dumps(corpus(), indent=2) + '\n')
    tools = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin')
    cc = tools / 'riscv64-unknown-elf-gcc'
    nm = tools / 'riscv64-unknown-elf-nm'
    flags = ['-O2', '-g', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
             '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-fno-common', '-mcmodel=medany',
             '-mabi=lp64d', '-march=rv64gcv_zicsr_zifencei', '-save-temps=obj',
             '-I' + str(ROOT / 'benchmarks'), '-I' + str(ROOT / 'third_party/saturn/benchmarks/common')]
    inputs = [Path(__file__).resolve(), Path(__file__).with_name('cases.py'),
              ROOT / 'hardware/manifest.json', ROOT / 'benchmarks/link.ld', cc, nm]
    commands = []
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
            raise RuntimeError('Build failed; inspect retained diagnostics: ' + name)
        deps = (out / (name + '.d')).read_text().replace('\\\n', ' ').split(':', 1)[1]
        inputs += [Path(p) for p in shlex.split(deps)]
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
        raise RuntimeError('Link failed; raw diagnostics retained')
    symbols = subprocess.check_output([str(nm), '-S', '--defined-only', str(elf)], text=True)
    (out / 'symbols.txt').write_text(symbols)
    matches = re.findall(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+[dD]\s+emit_console$', symbols, re.M)
    if len(matches) != 1 or int(matches[0][1], 16) != 8:
        raise ValueError('Unique initialized software output flag required')
    address = int(matches[0][0], 16)
    original = elf.read_bytes()
    if original[:6] != b'\x7fELF\x02\x01':
        raise ValueError('RV64 little-endian ELF required')
    phoff = struct.unpack_from('<Q', original, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', original, 54)
    offsets = []
    for i in range(phnum):
        kind, permissions, offset, vaddr, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', original, phoff+i*phsize)
        if kind == 1 and permissions & 2 and vaddr <= address and address+8 <= vaddr+size:
            offsets.append(offset+address-vaddr)
    if len(offsets) != 1 or original[offsets[0]:offsets[0]+8] != struct.pack('<Q', 1):
        raise ValueError('Software output flag is not one initialized writable word')
    silent = bytearray(original)
    silent[offsets[0]:offsets[0]+8] = struct.pack('<Q', 0)
    if [i for i, (a,b) in enumerate(zip(original, silent)) if a != b] != offsets:
        raise ValueError('Silent derivative changed more than its one-byte software input')
    (out / 'probe-silent.elf').write_bytes(silent)
    for tool in ('cc1', 'as', 'collect2', 'ld'):
        path = subprocess.check_output([str(cc), '-print-prog-name=' + tool], text=True).strip()
        inputs.append(Path(path if '/' in path else shutil.which(path)).resolve())
    inputs.append(Path(subprocess.check_output([str(cc), '-print-libgcc-file-name'], text=True).strip()))
    identities = {str(p.resolve()): digest(p) for p in inputs if out not in p.resolve().parents}
    snapshots = out / 'input-snapshot'
    snapshots.mkdir()
    for name, expected in identities.items():
        if not (snapshots / expected).exists():
            shutil.copyfile(name, snapshots / expected)
        if digest(name) != expected or digest(snapshots / expected) != expected:
            raise ValueError('Build inputs changed')
    record = {'schema': 'iris.vme_column_probe_build.v1', 'status': 'built',
        'commands': commands, 'elf_sha256': digest(elf), 'silent_elf_sha256': digest(out / 'probe-silent.elf'),
        'corpus_sha256': digest(out / 'corpus.json'), 'input_sha256': identities,
        'silent_derivative': {'changed_file_byte_offsets': offsets, 'software_flag_address': address,
            'original_value': 1, 'silent_value': 0, 'code_segments_symbols_unchanged': True,
            'scope': 'Software output flag read only after all probe data collection; no hardware/RTL state edit.'},
        'hardware_contacted': False, 'calibration_usable': False, 'source_image_association_verified': False}
    (out / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'elf_sha256': record['elf_sha256'], 'silent_elf_sha256': record['silent_elf_sha256'],
                      'known_row_regions': 768, 'unknown_column_observations': 384}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build(a.output.resolve())
