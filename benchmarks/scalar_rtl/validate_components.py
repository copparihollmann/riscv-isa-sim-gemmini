#!/usr/bin/env python3
"""Measure frozen scalar component cases after predictions; never uses the FPGA."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from iris_model.guest_regions import Instructions

MASK = (1 << 64) - 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode_signature(path, count):
    """Decode coherent guest output independently of model graph/timestamps."""
    if type(count) is not int or not 0 <= count <= 4096:
        raise ValueError('invalid ALU count')
    lines = path.read_text().splitlines()
    if len(lines) != 56 or any(not re.fullmatch('[0-9a-f]{16}', s) for s in lines):
        raise ValueError('signature must contain exactly 448 bytes')
    words = [int(s, 16) for s in lines]
    if words[:8] != [0x495249535343414c, 1, 0, 1, 1, 1, 0, 0]:
        raise ValueError('guest incomplete or failed')
    rows = []
    for hart in range(3):
        for kind in range(2):
            start, end, ibegin, iend, checksum, ops, p0, p1 = words[8 + hart * 16 + kind * 8:16 + hart * 16 + kind * 8]
            delta = (end - start) & MASK
            retired = (iend - ibegin) & MASK
            # Shuttle CSR.S B02 reads write back the old value; Rocket rewrites
            # a zero-mask read to CSR.R. This is a source-proved contract, not
            # an expected value inferred from these new RTL observations.
            if not 0 < delta < 1 << 63 or retired != count + int(hart == 2):
                raise ValueError('counter contract violated')
            if checksum != count + (1 if kind == 0 else 36) or ops != count or p0 or p1:
                raise ValueError('checksum/operation/padding contract violated')
            rows.append(dict(hart=hart, kind=kind, kernel='dependent' if kind == 0 else 'eight_chains',
                             operations=count, start_cycle=start, end_cycle=end, cycles=delta,
                             instret_delta=retired, checksum=checksum))
    return rows


def compiled_contract(build):
    """Check the actual ELF's read encodings, initialized chains and checksums."""
    n = build['alu_operations']
    if type(n) is not int or n < 0 or build['expected_checksums'] != [n + 1, n + 36]:
        raise ValueError('invalid frozen build arithmetic contract')
    image = Instructions(Path(build['elf']))
    bodies = build['compiled_body_validation']
    if len(bodies) != 2:
        raise ValueError('wrong body count')
    for kind, body in enumerate(bodies):
        pcs = body['counter_pcs']
        if len(pcs) != 4 or pcs != sorted(set(pcs)):
            raise ValueError('invalid counter PCs')
        for pc, csr in zip(pcs, (0xb00, 0xb02, 0xb02, 0xb00)):
            word = image.read(pc)
            if word & 0xfffff07f != (csr << 20 | 0x2073) or (word >> 7) & 31 == 0:
                raise ValueError('ELF counter is not nondiscarded CSRRS with zero mask')
        regs = []
        for pc in range(pcs[1] + 4, pcs[2], 4):
            word = image.read(pc)
            rd = (word >> 7) & 31
            if word & 0x707f != 0x13 or word >> 20 != 1 or not rd or (word >> 15) & 31 != rd:
                raise ValueError('ELF body changed from increment chains')
            regs.append(rd)
        expected = [5] * n if kind == 0 else ([5, 6, 7, 28, 12, 13, 14, 15] * ((n + 7) // 8))[:n]
        if regs != expected or body['decoded_addi_operations'] != n:
            raise ValueError('compiled operation count/order changed')
        # Setup is fixed initialized ADDI from x0 immediately before first CSR.
        init_regs = [5] if kind == 0 else [5, 6, 7, 28, 12, 13, 14, 15]
        for index, rd in enumerate(init_regs):
            pc = pcs[0] - 4 * (len(init_regs) - index)
            if image.read(pc) != ((index + 1) << 20 | rd << 7 | 0x13):
                raise ValueError('body initialization changed')
    return True


def compare(reference, prediction):
    if len(reference) != 6 or len(prediction) != 6:
        raise ValueError('expected six hart/stream rows')
    expected_keys = {(h, k) for h in range(3) for k in range(2)}
    refs = {(r['hart'], r['kind']): r for r in reference}
    models = {(r['hart'], r['kind']): r for r in prediction}
    if set(refs) != expected_keys or set(models) != expected_keys:
        raise ValueError('duplicate or missing hart/stream')
    result = []
    for key in sorted(expected_keys):
        ref, model = refs[key], models[key]
        for field in ('operations', 'instret_delta', 'checksum', 'kernel'):
            if ref[field] != model[field]:
                raise ValueError('functional mismatch: ' + field)
        if type(model['cycles']) is not int or model['cycles'] <= 0:
            raise ValueError('invalid model cycle prediction')
        error = 100 * (model['cycles'] - ref['cycles']) / ref['cycles']
        result.append(dict(hart=key[0], kind=key[1], kernel=ref['kernel'], operations=ref['operations'],
                           reference_cycles=ref['cycles'], predicted_cycles=model['cycles'],
                           signed_error_percent=error, within_2_percent=abs(error) <= 2,
                           reference_instret_delta=ref['instret_delta']))
    return result


def check_files(mapping):
    for path, digest in mapping.items():
        if sha(path) != digest:
            raise ValueError('changed frozen input: ' + str(path))


def load_frozen(plan_path, prediction_dir):
    closure_path = prediction_dir / 'manifest.json'
    closure = json.loads(closure_path.read_text())
    prediction_path = prediction_dir / 'predictions.json'
    if sha(prediction_path) != closure['prediction_sha256']:
        raise ValueError('prediction closure changed')
    for rel, digest in closure['artifact_sha256'].items():
        path = prediction_dir / rel
        if not path.resolve().is_relative_to(prediction_dir.resolve()) or sha(path) != digest:
            raise ValueError('prediction artifact changed or escaped capsule')
    check_files(closure['input_sha256'])
    predictions = json.loads(prediction_path.read_text())
    if predictions['reference_timings_observed'] or not predictions['predictions_frozen_before_reference']:
        raise ValueError('predictions were not declared blinded and frozen')
    if predictions['plan_sha256'] != sha(plan_path):
        raise ValueError('validation plan changed')
    plan = json.loads(plan_path.read_text())
    cases = {c['case_id']: c for c in plan['cases']}
    predicted = {c['case_id']: c for c in predictions['cases']}
    if len(cases) != 10 or len(predicted) != 10 or set(cases) != set(predicted):
        raise ValueError('validation scope changed')
    for case_id, case in cases.items():
        build_path = Path(case['build_receipt'])
        if sha(build_path) != case['build_receipt_sha256'] or predicted[case_id]['elf_sha256'] != case['elf_sha256']:
            raise ValueError('case prediction/build binding changed')
        build = json.loads(build_path.read_text())
        if sha(build['elf']) != case['elf_sha256'] or build['alu_operations'] != case['operations']:
            raise ValueError('case ELF/shape changed')
        check_files(build['input_sha256'])
        compiled_contract(build)
    return predictions, cases, predicted


def measure(case, prediction, directory, binary, timeout):
    directory.mkdir()
    sig = directory / 'signature'
    build = json.loads(Path(case['build_receipt']).read_text())
    argv = [str(binary), '+permissive', '+verilator+seed+1', '+verilator+rand+reset+2',
            '+loadmem=1', '+max-cycles=400000', '+init_write=0x2000004:0x1', '+init_write=0x2000008:0x1',
            '+signature=' + str(sig), '+signature-granularity=8', '+permissive-off', build['elf']]
    receipt = dict(schema='iris.scalar_component_rtl_run.v1', case_id=case['case_id'], operations=case['operations'],
                   build_receipt_sha256=case['build_receipt_sha256'], elf_sha256=case['elf_sha256'],
                   argv=argv, started_utc=datetime.now(timezone.utc).isoformat())
    env = dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:' + os.environ.get('PATH', ''))
    started = time.monotonic()
    with (directory / 'stdout').open('w') as stdout, (directory / 'stderr').open('w') as stderr:
        try:
            run = subprocess.run(argv, cwd=directory, env=env, stdout=stdout, stderr=stderr, timeout=timeout)
            receipt.update(exit_status=run.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            receipt.update(exit_status=None, timed_out=True)
    receipt.update(host_seconds=time.monotonic() - started, finished_utc=datetime.now(timezone.utc).isoformat())
    try:
        if receipt['exit_status'] != 0:
            raise ValueError('RTL process unsuccessful')
        if sha(build['elf']) != case['elf_sha256']:
            raise ValueError('ELF changed during measurement')
        reference = decode_signature(sig, case['operations'])
        receipt.update(status='measured', reference_rows=reference, comparisons=compare(reference, prediction['rows']))
    except (OSError, ValueError) as exc:
        receipt.update(status='failed', error=str(exc))
    receipt['artifact_sha256'] = {p.name: sha(p) for p in directory.iterdir() if p.is_file()}
    (directory / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ('case_id', 'status', 'host_seconds')}), flush=True)
    return receipt


def verify(out):
    report = json.loads((out / 'report.json').read_text())
    check_files(report['input_sha256'])
    for rel, digest in report['artifact_sha256'].items():
        path = out / rel
        if not path.resolve().is_relative_to(out.resolve()) or sha(path) != digest:
            raise ValueError('measurement artifact changed or escaped capsule')
    prediction = json.loads(Path(report['prediction_path']).read_text())
    predicted = {c['case_id']: c for c in prediction['cases']}
    comparisons = []
    for case in report['runs']:
        if case['status'] != 'measured':
            raise ValueError('incomplete RTL measurement')
        rows = decode_signature(out / ('alu' + str(case['operations'])) / 'signature', case['operations'])
        if rows != case['reference_rows']:
            raise ValueError('raw RTL signature disagrees with stored rows')
        comparisons.extend(compare(rows, predicted[case['case_id']]['rows']))
    if comparisons != report['comparisons'] or report['all_regions_within_2_percent'] != all(r['within_2_percent'] for r in comparisons):
        raise ValueError('comparison/error summary changed')
    if any(report[k] for k in ('timing_calibrated', 'final_workload_holdout', 'ethan_image_association_verified', 'hardware_contacted')):
        raise ValueError('component proof cannot claim full certification')
    return dict(status='verified', rows=len(comparisons), all_regions_within_2_percent=report['all_regions_within_2_percent'])


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / 'build/scalar-component-validation-plan-v2/plan.json')
    parser.add_argument('--predictions', type=Path, default=ROOT / 'build/scalar-component-predictions-e060-v1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--workers', type=int, choices=(1, 2), default=2)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.verify:
        print(json.dumps(verify(out)))
        return
    predictions, cases, predicted = load_frozen(args.plan.resolve(), args.predictions.resolve())
    out.mkdir(parents=True, exist_ok=False)
    (out / 'inputs').mkdir()
    inputs = {}

    def retain(path, expected=None):
        path = Path(path).resolve()
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError('input digest mismatch: ' + str(path))
        target = out / 'inputs' / digest
        if not target.exists():
            shutil.copyfile(path, target)
        inputs[str(path)] = digest

    loader_path = ROOT / 'build/rtl-loader-diag/loader-build.json'
    loader = json.loads(loader_path.read_text())
    binary = Path(loader['binary'])
    retain(binary, loader['binary_sha256'])
    for path in (loader_path, Path(__file__), ROOT / 'iris_model/guest_regions.py', args.plan,
                 args.predictions / 'predictions.json', args.predictions / 'manifest.json', ROOT / 'build/rtl-verilator/manifest.json'):
        retain(path)
    for path, digest in loader['input_sha256'].items():
        retain(path, digest)
    for path, digest in predictions['input_sha256'].items():
        retain(path, digest)
    ldd = subprocess.check_output(['ldd', str(binary)], text=True)
    if 'not found' in ldd:
        raise ValueError('missing RTL runtime library')
    (out / 'ldd.txt').write_text(ldd)
    for path in re.findall(r'(?:=>\s*)?(/[^\s]+)', ldd):
        if Path(path).is_file():
            retain(path)
    started = datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(started) <= datetime.fromisoformat(predictions['finished_utc']):
        raise ValueError('reference start does not follow recorded prediction freeze')
    preflight = dict(schema='iris.scalar_component_validation_preflight.v1', started_utc=started,
                     prediction_finished_utc=predictions['finished_utc'], prediction_manifest_sha256=sha(args.predictions / 'manifest.json'),
                     input_sha256=inputs, hardware_contacted=False, cases=list(cases))
    (out / 'preflight.json').write_text(json.dumps(preflight, indent=2) + '\n')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(measure, case, predicted[key], out / ('alu' + str(case['operations'])), binary, args.timeout)
                   for key, case in cases.items()]
        runs = [future.result() for future in futures]
    check_files(inputs)
    rows = [r for case in runs for r in case.get('comparisons', [])]
    report = dict(schema='iris.scalar_component_validation.v1', status='completed' if all(c['status'] == 'measured' for c in runs) else 'failed',
                  started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(), runs=runs, comparisons=rows,
                  prediction_path=str((args.predictions / 'predictions.json').resolve()), input_sha256=inputs,
                  source_fir_sha256=json.loads((ROOT / 'build/rtl-verilator/manifest.json').read_text())['source_fir_sha256'],
                  all_regions_within_2_percent=bool(rows) and all(r['within_2_percent'] for r in rows),
                  timing_calibrated=False, final_workload_holdout=False, ethan_image_association_verified=False, hardware_contacted=False,
                  scope='Blinded scalar component validation against distinct saved standalone IrisConfig RTL; no frontend/cache/vector/VME/full-SoC or FireSim accuracy claim')
    report['artifact_sha256'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file() and not p.is_relative_to(out / 'inputs')}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], rows=len(rows), all_regions_within_2_percent=report['all_regions_within_2_percent'])))
    if report['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
