"""Hardware-free tests using a build's verified three-hart native descriptor."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from iris_model.empirical_run import descriptor


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def checked(inputs):
    for name, expected in inputs.items():
        if sha(name) != expected:
            raise ValueError('Execution input changed: ' + name)


def run_checked(model, elf, output, *, fixture, timeout, inputs, dtc):
    """Preserve failed logs and clean up only this test's child process group."""
    output.mkdir(parents=True, exist_ok=False)
    per_hart = model['per_hart_isa']
    if set(per_hart) != {'0', '1', '2'}:
        raise ValueError('Explicit three-hart ISA metadata required')
    bound = {**model['execution_input_sha256'], **inputs,
             str(elf): sha(elf), str(fixture): sha(fixture), str(dtc): sha(dtc),
             str(Path(__file__).resolve()): sha(__file__)}
    launch = [('--iris-timing-fixture=' + str(fixture))
              if arg.startswith('--iris-timing-fixture=') else arg
              for arg in model['launch_args']]
    argv = [model['binary'], '--isa=' + per_hart['2'], '-p3',
            '-m' + ','.join(f'{base:#x}:{size:#x}' for base, size in model['memory_regions']),
            *launch, '--iris-timing-trace=' + str(output / 'summary.json'),
            *('--hart-isa=' + hart + ':' + per_hart[hart] for hart in ('0', '1', '2')),
            str(elf)]
    env = dict(os.environ)
    env['PATH'] = str(dtc.parent) + os.pathsep + env.get('PATH', '')
    env.pop('IRIS_CPU_DIAGNOSTIC_TRACE', None)
    env['IRIS_EMPIRICAL_ASYNC_TRACE'] = str(output / 'async.jsonl')
    env['IRIS_EMPIRICAL_FEATURES'] = str(output / 'features.jsonl')
    record = dict(schema='iris.native_test_execution.v1', argv=argv, input_sha256=bound,
                  environment={k: v for k, v in env.items()
                               if k.startswith(('IRIS_', 'LD_')) or k == 'PATH'},
                  physical_harts=3, hardware_contacted=False,
                  timing_accuracy_certified=False, timed_out=False,
                  inputs_unchanged=False, error=None)
    proc = None
    started = time.monotonic()
    try:
        checked(bound)
        with (output / 'stdout').open('wb') as stdout, (output / 'stderr').open('wb') as stderr:
            proc = subprocess.Popen(argv, env=env, stdout=stdout, stderr=stderr,
                                    start_new_session=True)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        record['exit_status'] = proc.returncode
        checked(bound)
        record['inputs_unchanged'] = True
    except (Exception, KeyboardInterrupt) as error:
        record['error'] = str(error)
    finally:
        if proc is not None and proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        record['host_seconds'] = time.monotonic() - started
        record['output_sha256'] = {str(path): sha(path) for path in output.iterdir()
                                   if path.is_file()}
        (output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    return record
