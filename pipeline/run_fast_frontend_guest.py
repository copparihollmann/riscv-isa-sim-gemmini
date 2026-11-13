#!/usr/bin/env python3
"""Run a disjoint fast-frontend guest with exact file/command receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--argv-json', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', required=True, type=float)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    argv = json.loads(args.argv_json.read_text())
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise ValueError('actual argv string array required')
    inputs = [Path(__file__).resolve(), args.argv_json.resolve(), Path(argv[0]), Path(argv[-1])]
    for arg in argv:
        if arg.startswith(('--extlib=', '--iris-bootrom=', '--dtb=', '--iris-timing-fixture=')):
            inputs.append(Path(arg.split('=', 1)[1]))
    identities = {str(path.resolve()): sha(path) for path in inputs}
    (output / 'argv.json').write_text(json.dumps(argv, indent=2) + '\n')
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('IRIS_EMPIRICAL_'):
            del env[key]
    env['IRIS_EMPIRICAL_DIAGNOSTICS'] = '1'

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    started = time.monotonic()
    with (output / 'stdout').open('w') as stdout, (output / 'stderr').open('w') as stderr:
        try:
            completed = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr,
                                       timeout=args.timeout, preexec_fn=limits)
            status, timed_out = completed.returncode, False
        except subprocess.TimeoutExpired:
            status, timed_out = None, True
    report = dict(schema='iris.fast_source_frontend.actual_guest_run.v1', argv=argv,
                  exit_status=status, timed_out=timed_out, timeout_seconds=args.timeout,
                  host_seconds=time.monotonic() - started, input_sha256=identities,
                  input_bytes_unchanged=all(sha(path) == digest for path, digest in identities.items()),
                  stdout_sha256=sha(output / 'stdout'), stderr_sha256=sha(output / 'stderr'),
                  environment={'IRIS_EMPIRICAL_DIAGNOSTICS': '1'},
                  functional_checks_performed=False, calibrated=False, timing_certified=False)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
