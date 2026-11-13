#!/usr/bin/env python3
"""Independently audit raw scalar measurements and frozen prediction signatures."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re

if __package__:
    from .validate_components import compiled_contract, compare, decode_signature, sha
else:
    from validate_components import compiled_contract, compare, decode_signature, sha


def artifacts(base, mapping):
    for name, digest in mapping.items():
        path = (base / name).resolve()
        if not path.is_relative_to(base.resolve()) or sha(path) != digest:
            raise ValueError('changed or escaped artifact: ' + name)


def audit(out, predictions, expected_prediction_manifest):
    report = json.loads((out / 'report.json').read_text())
    if report['schema'] != 'iris.scalar_component_validation.v1' or report['status'] != 'completed':
        raise ValueError('complete scalar component report required')
    for key in ('timing_calibrated', 'final_workload_holdout', 'ethan_image_association_verified', 'hardware_contacted'):
        if report[key] is not False:
            raise ValueError('component result cannot assert certification')
    artifacts(out, report['artifact_sha256'])
    inputs = report['input_sha256']
    for original, digest in inputs.items():
        if not re.fullmatch('[0-9a-f]{64}', digest) or sha(out / 'inputs' / digest) != digest:
            raise ValueError('archived input changed: ' + original)

    def archived(original):
        return out / 'inputs' / inputs[str(original)]

    prediction_manifest = predictions / 'manifest.json'
    if sha(prediction_manifest) != expected_prediction_manifest:
        raise ValueError('frozen prediction manifest differs from expected anchor')
    closure = json.loads(prediction_manifest.read_text())
    artifacts(predictions, closure['artifact_sha256'])
    pred_path = Path(report['prediction_path'])
    if sha(predictions / 'predictions.json') != closure['prediction_sha256'] or sha(archived(pred_path)) != closure['prediction_sha256']:
        raise ValueError('run does not bind these predictions')
    pred = json.loads((predictions / 'predictions.json').read_text())
    preflight = json.loads((out / 'preflight.json').read_text())
    if preflight['prediction_manifest_sha256'] != expected_prediction_manifest:
        raise ValueError('preflight does not bind frozen prediction closure')
    if pred['reference_timings_observed'] or not pred['predictions_frozen_before_reference']:
        raise ValueError('blinded prediction role violated')
    if datetime.fromisoformat(pred['finished_utc']) >= datetime.fromisoformat(report['started_utc']):
        raise ValueError('recorded prediction freeze must precede reference measurement')
    plan_paths = [p for p, digest in inputs.items() if digest == pred['plan_sha256']]
    if len(plan_paths) != 1:
        raise ValueError('ambiguous frozen plan binding')
    plan = json.loads(archived(plan_paths[0]).read_text())
    plans = {c['case_id']: c for c in plan['cases']}
    preds = {c['case_id']: c for c in pred['cases']}
    runs = {c['case_id']: c for c in report['runs']}
    # The caller's immutable prediction-manifest anchor binds this exact plan;
    # future source-derived candidates can have a fresh, genuinely unseen plan.
    names = {'scalar.alu' + str(c['operations']) for c in plan['cases']}
    if (len(plan['cases']) != 10 or len(pred['cases']) != 10 or len(report['runs']) != 10 or
            len(names) != 10 or set(plans) != names or set(preds) != names or set(runs) != names):
        raise ValueError('ten-case validation scope changed')
    all_rows = []
    for case_id, run in runs.items():
        plan_case, prediction = plans[case_id], preds[case_id]
        n = plan_case['operations']
        case_dir = out / ('alu' + str(n))
        if json.loads((case_dir / 'results.json').read_text()) != run:
            raise ValueError('inline run differs from frozen per-case receipt')
        if run['status'] != 'measured' or run['exit_status'] != 0 or run['timed_out'] is not False:
            raise ValueError('unsuccessful RTL measurement')
        if datetime.fromisoformat(run['started_utc']) < datetime.fromisoformat(report['started_utc']):
            raise ValueError('case predates preflight')
        artifacts(case_dir, run['artifact_sha256'])
        build_path = Path(plan_case['build_receipt'])
        if (sha(archived(build_path)) != plan_case['build_receipt_sha256'] or
                run['build_receipt_sha256'] != prediction['build_receipt_sha256'] or
                run['build_receipt_sha256'] != plan_case['build_receipt_sha256']):
            raise ValueError('case build binding changed')
        build = json.loads(archived(build_path).read_text())
        if (run['elf_sha256'] != plan_case['elf_sha256'] or
                prediction['elf_sha256'] != plan_case['elf_sha256'] or
                sha(archived(build['elf'])) != plan_case['elf_sha256'] or run['argv'][-1] != build['elf']):
            raise ValueError('different ELF was measured/predicted')
        build['elf'] = str(archived(build['elf']))
        compiled_contract(build)
        reference = decode_signature(case_dir / 'signature', n)
        raw_prediction = decode_signature(predictions / ('alu' + str(n)) / 'signature', n)
        for raw, stored in zip(raw_prediction, prediction['rows']):
            if any(stored[key] != value for key, value in raw.items()):
                raise ValueError('prediction rows disagree with frozen raw signature')
        rows = compare(reference, raw_prediction)
        if reference != run['reference_rows'] or rows != run['comparisons']:
            raise ValueError('timing table disagrees with raw reference/prediction signatures')
        all_rows.extend(rows)
    if len(all_rows) != 60 or all_rows != report['comparisons']:
        raise ValueError('complete comparison table changed')
    all_pass = all(r['within_2_percent'] for r in all_rows)
    if report['all_regions_within_2_percent'] is not all_pass:
        raise ValueError('aggregate error claim disagrees with raw data')
    summary = {}
    for hart in range(3):
        rows = [r for r in all_rows if r['hart'] == hart]
        summary[str(hart)] = dict(rows=len(rows), exact=sum(r['signed_error_percent'] == 0 for r in rows),
                                 min_signed_error_percent=min(r['signed_error_percent'] for r in rows),
                                 max_signed_error_percent=max(r['signed_error_percent'] for r in rows))
    return dict(status='verified_raw_component_validation', rows=60, per_hart=summary,
                prediction_manifest_sha256=expected_prediction_manifest, report_sha256=sha(out / 'report.json'),
                all_regions_within_2_percent=all_pass, timing_calibrated=False, held_out_full_workload=False)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--prediction-manifest-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.run.resolve(), args.predictions.resolve(), args.prediction_manifest_sha256), indent=2))


if __name__ == '__main__':
    main()
