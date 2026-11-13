#!/usr/bin/env python3
"""Execute an isolated saved-RTL readout diagnostic and preserve exact evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks/vme_column_probe'))
from validate import signature


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def run(build, reference, output, seed, max_cycles=2000000, timeout=600):
    if type(max_cycles) is not int or type(timeout) is not int or max_cycles <= 0 or timeout <= 0:
        raise ValueError('Explicit positive reference bounds required')
    output.mkdir(parents=True, exist_ok=False)
    built = json.loads((build / 'build.json').read_text())
    elf = build / 'probe-silent.elf'
    if built['status'] != 'built' or digest(elf) != built['silent_elf_sha256']:
        raise ValueError('Exact successful silent software-input ELF required')
    reference_receipt = json.loads((reference / 'build.json').read_text())
    binary = reference / 'simulator-preload'
    if (reference_receipt.get('schema') != 'iris.vme_column_preload_whole_reference.v1'
            or reference_receipt['status'] != 'built' or digest(binary) != reference_receipt['binary_sha256']):
        raise ValueError('Exact saved-RTL reference required')
    sources = [Path(__file__).resolve(), ROOT / 'benchmarks/vme_column_probe/validate.py',
               ROOT / 'benchmarks/vme_column_probe/cases.py', build / 'build.json', build / 'corpus.json', elf,
               reference / 'build.json', binary]
    inputs = dict(built['input_sha256'])
    inputs.update({str(p): digest(p) for p in sources})
    snapshots = output / 'inputs'
    snapshots.mkdir()
    for name, expected in inputs.items():
        if digest(name) != expected:
            raise ValueError('Source changed before reference execution')
        if not (snapshots / expected).exists():
            shutil.copyfile(name, snapshots / expected)
    argv = [str(binary), '+permissive', '+verilator+seed+'+str(seed), '+verilator+rand+reset+2',
            '+loadmem=1', '+noc_util_sample_rate=0', '+max-cycles='+str(max_cycles),
            '+init_write=0x2000004:0x1', '+init_write=0x2000008:0x1', '+permissive-off',
            '+signature='+str(output / 'guest.signature'), '+signature-granularity=8', str(elf)]
    record = {'schema': 'iris.vme_column_actual_saved_RTL_run.v1', 'status': 'running',
        'argv': argv, 'seed': seed, 'elf_sha256': digest(elf), 'input_sha256': inputs,
        'host_timeout_seconds': timeout, 'target_max_cycles': max_cycles,
        'hardware_contacted': False, 'source_FIR_sha256': reference_receipt['source_fir_sha256'],
        'source_image_association_verified': False, 'full_functional_certified': False,
        'timing_certified': False, 'calibration_usable': False,
        'software_output_flag_only_difference_from_hardware_ELF': built['silent_derivative']}
    (output / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
    started = time.monotonic()
    with (output / 'stdout').open('wb') as stdout, (output / 'stderr').open('wb') as stderr:
        try:
            result = subprocess.run(argv, cwd=output, stdout=stdout, stderr=stderr, timeout=timeout,
                                    env=dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']))
            record.update(exit_status=result.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            record.update(exit_status=None, timed_out=True)
    record['host_seconds'] = time.monotonic()-started
    try:
        if record['exit_status'] != 0 or record['timed_out']:
            raise ValueError('Reference did not complete successfully')
        analysis = signature(output / 'guest.signature', elf)
        (output / 'analysis.json').write_text(json.dumps(analysis, indent=2) + '\n')
        if any(digest(name) != expected for name, expected in inputs.items()):
            raise ValueError('Inputs changed during execution')
        record.update(status='passed_source_row_controls_and_raw_column_observations',
                      row_controls=analysis['row_controls_passed'],
                      column_classifications=analysis['column_classifications'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        record.update(status='failed', error=str(error))
    record['artifact_sha256'] = {p.name: digest(p) for p in output.iterdir() if p.is_file() and p.name != 'report.json'}
    (output / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k:record.get(k) for k in ('status', 'column_classifications', 'error', 'host_seconds')}))
    return 0 if record['status'].startswith('passed_') else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reference', type=Path, default=ROOT / 'build/vme-column-preload-reference-v1')
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--max-cycles', type=int, default=2000000)
    p.add_argument('--timeout', type=int, default=600)
    a = p.parse_args()
    raise SystemExit(run(a.build.resolve(), a.reference.resolve(), a.output.resolve(), a.seed, a.max_cycles, a.timeout))
