#!/usr/bin/env python3
"""Build only the new PLIC helper; leave shared Spike builds/provenance untouched."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE / 'build/plic'
    output.mkdir(parents=True, exist_ok=True)
    source = HERE.parent / 'third_party/riscv-isa-sim'
    compiler = shutil.which(os.environ.get('CXX', 'g++'))
    if not compiler:
        raise RuntimeError('C++ compiler unavailable')
    command = [compiler, '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
               '-I' + str(HERE.parent / 'spike/build'), '-I' + str(HERE),
               '-iquote', str(source / 'riscv'), '-iquote', str(source / 'fesvr'),
               '-iquote', str(source), str(HERE / 'tests/plic_test.cpp'),
               '-o', str(output / 'plic_test')]
    compile_result = subprocess.run(command, text=True, capture_output=True)
    (output / 'compile.stdout').write_text(compile_result.stdout)
    (output / 'compile.stderr').write_text(compile_result.stderr)
    if compile_result.returncode:
        print(compile_result.stderr)
        return compile_result.returncode
    test = subprocess.run([str(output / 'plic_test')], text=True, capture_output=True)
    (output / 'tests.stdout').write_text(test.stdout)
    (output / 'tests.stderr').write_text(test.stderr)
    inputs = [HERE / 'iris_plic.hpp', HERE / 'tests/plic_test.cpp', Path(__file__),
              HERE / 'evidence/plic.scala', HERE / 'evidence/firesim-dts.dts']
    result = {'schema_version': 1, 'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'passed_helper_tests' if test.returncode == 0 else 'failed',
              'exit_status': test.returncode, 'command': command,
              'compiler_sha256': sha(compiler), 'core_integration': False,
              'rtl_certified': False, 'pipeline_timing_certified': False,
              'input_sha256': {str(p.relative_to(HERE)): sha(p) for p in inputs},
              'binary_sha256': sha(output / 'plic_test'),
              'stdout_sha256': sha(output / 'tests.stdout'), 'stderr_sha256': sha(output / 'tests.stderr')}
    (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(test.stdout, end='')
    print(test.stderr, end='')
    return test.returncode


if __name__ == '__main__':
    raise SystemExit(main())
