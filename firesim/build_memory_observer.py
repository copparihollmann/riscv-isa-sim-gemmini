#!/usr/bin/env python3
"""Build and freeze the reviewed read-only FASED BAR observer; never opens hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'firesim/readonly_fased_latency.c'
    evidence = ROOT / 'firesim/fased-read-source-evidence.json'
    reviewed = json.loads(evidence.read_text())
    if digest(source) != reviewed['candidate_source_sha256']:
        raise ValueError('Read-only observer source no longer matches its reviewed evidence')
    local_source = output / 'readonly_fased_latency.c'
    shutil.copyfile(source, local_source)
    compiler = Path('/usr/bin/cc').resolve()
    binary = output / 'readonly-fased-latency'
    argv = [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-save-temps=obj', '-Wl,-Map,' + str(output / 'link.map'),
            '-o', str(binary), str(local_source)]
    result = subprocess.run(argv, capture_output=True)
    (output / 'build.stdout').write_bytes(result.stdout)
    (output / 'build.stderr').write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError('Observer build failed; raw compiler evidence retained')
    inputs = {str(p): digest(p) for p in [source, evidence, Path(__file__).resolve(), compiler]}
    for name in ('cc1', 'as', 'collect2', 'ld'):
        tool = subprocess.check_output([str(compiler), '-print-prog-name=' + name], text=True).strip()
        resolved = Path(tool).resolve() if '/' in tool else Path(shutil.which(tool)).resolve()
        inputs[str(resolved)] = digest(resolved)
    # These are the exact linked startup objects, libraries and linker scripts.
    # The retained .i is the exact preprocessed translation-unit input.
    for token in re.findall(r'^LOAD\s+(\S+)', (output / 'link.map').read_text(), re.M):
        path = Path(token)
        if path.is_file() and not path.is_relative_to(output):
            inputs[str(path.resolve())] = digest(path.resolve())
    metadata = subprocess.run(['/usr/bin/readelf', '-l', '-d', str(binary)], capture_output=True, check=True)
    (output / 'elf-metadata.txt').write_bytes(metadata.stdout)
    inputs['/usr/bin/readelf'] = digest('/usr/bin/readelf')
    fixture_dir = ROOT / 'build/fased-readonly-tests'
    controls = []
    for name, expected in [('valid', 0), ('invalid-all-ones', 1), ('invalid-zero-presence', 1), ('ambiguous-parameter', 1)]:
        fixture = fixture_dir / (name + '.bin')
        result = subprocess.run([str(binary), '--test-file', str(fixture)], capture_output=True)
        (output / (name + '.stdout')).write_bytes(result.stdout)
        (output / (name + '.stderr')).write_bytes(result.stderr)
        inputs[str(fixture)] = digest(fixture)
        if result.returncode != expected:
            raise ValueError('Observer admission control failed: ' + name)
        controls.append({'fixture': name, 'returncode': result.returncode, 'expected_returncode': expected})
    artifacts = {str(p.relative_to(output)): digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    report = {'schema': 'iris.readonly_memory_observer_build.v1', 'pass': True,
              'hardware_contacted': False, 'argv': argv, 'binary_sha256': digest(binary),
              'source_sha256': digest(source), 'reviewed_evidence_sha256': digest(evidence),
              'input_sha256': inputs, 'artifact_sha256': artifacts, 'fixture_controls': controls,
              'dynamic_runtime': 'Remote interpreter/libc identities must be captured before actual execution; host libraries are not assumed identical.',
              'source_image_association_verified': False, 'calibration_usable': False}
    snapshots = output / 'inputs'; snapshots.mkdir()
    for name, expected in inputs.items():
        path = Path(name)
        if digest(path) != expected:
            raise ValueError('Observer input changed during build: ' + name)
        destination = snapshots / expected
        if not destination.exists():
            shutil.copyfile(path, destination)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output.resolve())
    print(json.dumps({'pass': result['pass'], 'binary_sha256': result['binary_sha256'], 'hardware_contacted': False}))
