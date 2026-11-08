#!/usr/bin/env python3
"""Compile/run 11 real processor event and VLE8 read-permission checks."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from native_test_support import checked, sha

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = json.loads((build / 'build.json').read_text())
    checked(receipt['input_sha256'])
    configure = next(c['argv'] for c in receipt['commands'] if c['phase'] == 'configure')
    compiler = next(s.split('=', 1)[1] for s in configure if s.startswith('CXX='))
    flags = shlex.split(next(s.split('=', 1)[1] for s in configure if s.startswith('CXXFLAGS=')))
    libraries = shlex.split(next(s.split('=', 1)[1] for s in configure if s.startswith('LIBS=')))
    headers = [Path(p) for p in receipt['input_sha256'] if p.endswith('/riscv/processor.h')]
    if len(headers) != 1:
        raise ValueError('Unique source processor header required in build receipt')
    source = headers[0].parents[1]
    test = HERE / 'vle8_permission.cc'
    static = [build / name for name in ('libriscv.a', 'libdisasm.a', 'libsoftfloat.a', 'libfesvr.a', 'libfdt.a')]
    includes = [build, source / 'riscv', source / 'fesvr', source / 'softfloat', source / 'disasm']
    argv = [compiler, *flags, *[v for p in includes for v in ('-iquote', str(p))],
            str(test), '-Wl,--export-dynamic', '-Wl,--start-group', *map(str, static),
            '-Wl,--end-group', *libraries, '-ldl', '-o', str(out / 'permission-test')]
    inputs = {**receipt['input_sha256'], **{str(p): sha(p) for p in
              [Path(__file__).resolve(), HERE / 'native_test_support.py', test,
               build / 'build.json', Path(compiler), *static]}}
    checked(inputs)
    compiled = subprocess.run(argv, capture_output=True, timeout=120)
    (out / 'compile.stdout').write_bytes(compiled.stdout)
    (out / 'compile.stderr').write_bytes(compiled.stderr)
    report = dict(schema='iris.single_vle8_front.processor_permissions.v1', passed=False,
                  compiler_argv=argv, compile_exit=compiled.returncode, input_sha256=inputs,
                  hardware_contacted=False, timing_accuracy_certified=False)
    if compiled.returncode == 0:
        run = subprocess.run([str(out / 'permission-test')], capture_output=True, timeout=30)
        (out / 'stdout').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        report.update(exit_status=run.returncode, binary_sha256=sha(out / 'permission-test'),
                      passed=run.returncode == 0 and b'STEP_OUTCOME DONE 11' in run.stdout)
    checked(inputs)
    report['inputs_unchanged'] = True
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'compile_exit': compiled.returncode}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
