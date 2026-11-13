#!/usr/bin/env python3
"""Build/freeze independent Zephyr held-outs without executing their ELFs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def output_hash(values):
    h = 14695981039346656037
    for value in values:
        for byte in struct.pack('<I', value):
            h = ((h ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return h


def produce_counter_pcs(listing):
    inside = False; rows = []
    for line in listing.splitlines():
        match = re.match(r'^([0-9a-f]+) <([^>]+)>:', line)
        if match:
            inside = match[2] == 'produce'
        if not inside:
            continue
        fields = line.split()
        if len(fields) < 2 or not re.fullmatch('[0-9a-f]{8}', fields[1]):
            continue
        word = int(fields[1], 16)
        csr = word >> 20
        if csr in (0xb00, 0xb02) and word & 0xfffff07f == csr << 20 | 0x2073 and (word >> 7) & 31:
            rows.append({'pc': int(fields[0].rstrip(':'), 16), 'word': word, 'csr': csr})
    if [row['csr'] for row in rows] != [0xb02, 0xb00, 0xb00, 0xb02]:
        raise ValueError('Expected exact producer retired/cycle/cycle/retired read contract')
    return rows


def freeze(output, trials):
    output.mkdir(parents=True, exist_ok=False)
    objects = output / 'objects'; objects.mkdir()
    inputs = {}
    def retain(path, expected=None):
        path = Path(path).resolve(); value = sha(path)
        if expected is not None and value != expected:
            raise ValueError('Held-out source/build changed: ' + str(path))
        target = objects / value
        if not target.exists():
            shutil.copyfile(path, target)
        if sha(target) != value:
            raise ValueError('Held-out snapshot changed')
        inputs[str(path)] = {'sha256': value, 'object': str(target.relative_to(output))}
        return value
    cases = []
    binary = ROOT / 'build/combined-candidate-35901887/spike'
    uart = binary.parent / 'libsifive_uart.so'
    objdump = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-objdump')
    environment = dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:' + os.environ.get('PATH', ''))
    for op in ('gemm', 'conv2d'):
        for workers in (1, 2):
            name = op + '-h' + str(workers); directory = output / name
            command = [sys.executable, str(ROOT / 'zephyr/compiler_pipeline.py'), '--op', op,
                       '--harts', str(workers), '--output', str(directory), '--binary', str(binary), '--uart', str(uart),
                       '--app-source', str(ROOT / 'zephyr/heldout-pipeline'), '--trials', str(trials),
                       '--require-end-to-end', '--build-only', '--mlir-receipt', str(ROOT / 'build/merlin-mlir' / op / 'artifacts.json')]
            with (output / (name + '.stdout')).open('xb') as stdout, (output / (name + '.stderr')).open('xb') as stderr:
                result = subprocess.run(command, env=environment, stdout=stdout, stderr=stderr)
            if result.returncode:
                raise RuntimeError(name + ' build failed; preserve raw logs')
            build = json.loads((directory / 'build-only.json').read_text())
            if build['executed'] or build['timing_observed'] or build['jobs'] != 3 * trials:
                raise ValueError('Held-out build unexpectedly executed or changed scope')
            retain(directory / 'build-only.json'); retain(directory / 'emission.json')
            for path, value in build['source_sha256'].items():
                retain(path, value)
            golden_path = directory / 'generated/golden.json'; retain(golden_path)
            goldens = json.loads(golden_path.read_text())
            m, n, k = build['shape_mnk']
            region_cases = []
            for job, golden in enumerate(goldens):
                checksums = [0, 0, 0]
                for hart in range(workers):
                    first, last = m * hart // workers, m * (hart + 1) // workers
                    checksums[hart] = output_hash(golden['accumulator_u32'][first*n:last*n])
                region_cases.append({'id': 'zephyr.compiler.' + op + '.job' + str(job), 'region': 'job' + str(job),
                    'trial_id': job // 3, 'dataset_id': job % 3, 'active_harts': list(range(workers)),
                    'expected_checksums_by_hart': checksums, 'corpus_split': 'iris-v2-heldout-zephyr'})
            producer_values = [7 + (job % 3) * 8 + element for job in range(3 * trials) for element in range(8)]
            region_cases.append({'id': 'zephyr.compiler.' + op + '.end_to_end', 'region': 'pipeline_end_to_end',
                'active_harts': [2], 'expected_checksums_by_hart': [0, 0, output_hash(producer_values)],
                'corpus_split': 'iris-v2-heldout-zephyr'})
            (directory / 'cases.json').write_text(json.dumps(region_cases, indent=2) + '\n'); retain(directory / 'cases.json')
            variants = []
            for artifact in build['artifacts']:
                elf = Path(artifact['elf']); retain(elf, artifact['elf_sha256'])
                receipt_path = elf.parents[1] / 'build.json'; retain(receipt_path, artifact['build_receipt_sha256'])
                receipt = json.loads(receipt_path.read_text())
                for path, value in receipt['input_sha256'].items():
                    retain(ROOT / path, value)
                listing = subprocess.check_output([objdump, '-d', elf], text=True)
                destination = directory / (artifact['kind'] + '.disassembly'); destination.write_text(listing); retain(destination)
                variants.append({**artifact, 'elf_object': inputs[str(elf.resolve())]['object'],
                                 'producer_counter_pcs': produce_counter_pcs(listing)})
            cases.append({'case_id': 'merlin.zephyr.' + op + '.' + str(workers) + 'compute',
                'entrypoint': 'examples/iris/run.sh op ' + op,
                'shape_mnk': [m, n, k], 'convolution_source_shape': None if op == 'gemm' else {
                    'input_nhwc': [1, 10, 10, 8], 'filter_hwio': [3, 3, 8, 64], 'stride': [1, 1], 'padding': 'valid'},
                'workers': workers, 'compute_harts': list(range(workers)), 'producer_hart': 2, 'physical_harts': 3,
                'trials': trials, 'datasets': 3, 'jobs': 3 * trials, 'variants': variants,
                'cases_manifest': str(directory / 'cases.json'), 'cases_manifest_sha256': sha(directory / 'cases.json'),
                'golden': str(golden_path), 'golden_sha256': sha(golden_path),
                'expected_regions': workers * 3 * trials + 1,
                'end_to_end_scope': 'Pinned hart2 producer entry through all outputs consumed; excludes boot, main thread construction and final result printing',
                'inactive_hart_policy': 'All3 Zephyr CPUs online; workers pinned0/1, producer pinned2; unused compute hart uses normal OS scheduler/idle/WFI, not powered off',
                'fitting_allowed': False, 'timing_observed': False, 'build_argv': command})
    for path in [Path(__file__), ROOT / 'zephyr/compiler_pipeline.py', ROOT / 'zephyr/heldout-pipeline/derivation.json',
                 ROOT / 'benchmarks/heldout-corpus.json', ROOT / 'hardware/merlin-source.json', ROOT / 'hardware/iris-mlir-source.json',
                 ROOT / 'hardware/manifest.json', objdump]:
        retain(path)
    miles_path = ROOT / 'benchmarks/build/heldout-build.json'; miles = json.loads(miles_path.read_text()); retain(miles_path)
    for item in miles['artifacts']:
        retain(item['path'], item['sha256'])
        for path, value in item['input_sha256'].items():
            retain(path, value)
    report = {'schema': 'iris.frozen_independent_heldout_suite.v2', 'split_id': 'iris-v2-heldout-zephyr',
        'fitting_allowed': False, 'status': 'built_frozen_not_executed', 'cases': cases, 'miles_original_defaults': miles,
        'real_reference_or_detailed_model_timings_observed': False, 'source_functional_checks_permitted': True,
        'holdout_retirement_policy': 'If real timing errors from these cases inform changes/fitting, retire them and freeze replacement cases before independent validation',
        'calibration_usable': False, 'timing_accuracy_certified': False, 'hardware_contacted': False,
        'inputs': inputs}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--trials', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.trials <= 32:
        parser.error('trials must be in1..32')
    report = freeze(args.output.resolve(), args.trials)
    print(json.dumps({'status': report['status'], 'zephyr_cases': len(report['cases']), 'hardware_contacted': False}))


if __name__ == '__main__':
    main()
