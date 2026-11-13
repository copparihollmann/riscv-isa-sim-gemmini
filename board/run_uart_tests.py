#!/usr/bin/env python3
"""Build/test independent UART helper; do not rebuild or mutate Spike core."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    evidence_path = HERE / 'uart-source-evidence.json'
    evidence = json.loads(evidence_path.read_text())
    for name, source in evidence['sources'].items():
        if sha(HERE / source['snapshot']) != source['sha256']:
            raise RuntimeError('UART source snapshot mismatch: ' + name)
    artifacts = {source['source_artifact']: source['source_artifact_sha256']
                 for source in evidence['sources'].values() if source.get('source_artifact')}
    artifact_verified = {}
    for path, expected in artifacts.items():
        artifact_verified[path] = Path(path).is_file()
        if artifact_verified[path] and sha(path) != expected:
            raise RuntimeError('UART external elaboration artifact mismatch: ' + path)
    output = HERE / 'build/uart'; output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').unlink(missing_ok=True)
    source = HERE.parent / 'third_party/riscv-isa-sim'
    compiler = shutil.which(os.environ.get('CXX', 'g++'))
    if not compiler: raise RuntimeError('C++ compiler unavailable')
    cmd = [compiler, '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
           '-I' + str(HERE.parent / 'spike/build'), '-I' + str(HERE),
           '-iquote', str(source / 'riscv'), '-iquote', str(source / 'fesvr'),
           '-iquote', str(source), str(HERE / 'tests/uart_test.cpp'), '-o', str(output / 'uart_test')]
    compiled = subprocess.run(cmd, text=True, capture_output=True)
    (output / 'compile.stdout').write_text(compiled.stdout)
    (output / 'compile.stderr').write_text(compiled.stderr)
    if compiled.returncode:
        print(compiled.stderr); return compiled.returncode
    ran = subprocess.run([str(output / 'uart_test')], text=True, capture_output=True)
    (output / 'tests.stdout').write_text(ran.stdout); (output / 'tests.stderr').write_text(ran.stderr)
    inputs = [HERE / 'iris_uart.hpp', HERE / 'tests/uart_test.cpp', Path(__file__), evidence_path]
    inputs += [HERE / source['snapshot'] for source in evidence['sources'].values()]
    receipt = {'schema_version': 1, 'status': 'passed_helper_tests' if ran.returncode == 0 else 'failed',
               'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'exit_status': ran.returncode, 'compiler_sha256': sha(compiler), 'build_command': cmd,
               'input_sha256': {str(path.relative_to(HERE) if path.is_relative_to(HERE) else path): sha(path) for path in inputs},
               'binary_sha256': sha(output / 'uart_test'), 'stdout_sha256': sha(output / 'tests.stdout'),
               'stderr_sha256': sha(output / 'tests.stderr'), 'core_integrated': False,
               'rtl_certified': False, 'zephyr_smp_certified': False, 'rx_sampling_certified': False,
               'clock_domain_calibrated': False}
    receipt['external_artifact_verified'] = artifact_verified
    (output / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(ran.stdout, end=''); print(ran.stderr, end='')
    return ran.returncode


if __name__ == '__main__': raise SystemExit(main())
