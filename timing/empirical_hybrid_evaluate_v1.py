#!/usr/bin/env python3
"""Report actual NEW compute counter errors, retaining unqualified families."""
import argparse
import collections
import hashlib
import json
import pathlib
import statistics

from empirical_priority_runtime_report import metrics
EXCLUDED = set()  # Every TRAIN family participates in this own-epoch fit/selection.


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main(args):
    report = json.loads(args.regions.with_name('report.json').read_text())
    if report.get('schema') != 'iris.empirical_compute_runtime_feature_join.v1' or report.get('pass') is not True or report.get('global_heldout_timings_consumed') is not False:
        raise ValueError('Qualified new compute runtime features required')
    for name, digest in {**report['input_sha256'], **report['output_sha256']}.items():
        if sha(name) != digest:
            raise ValueError('Actual feature/evidence input changed ' + name)
    observed = [json.loads(s) for s in args.regions.read_text().splitlines()]
    rows = []
    for r in observed:
        rows.append({'case_id': r['case_id'], 'parent_case_id': r['parent_case_id'], 'partition': r['partition'],
                     'family': r['family_for_reporting_only'], 'hart': r['hart'],
                     'reference_cycles': r['reference_cycles'], 'native_cycles': r['native_cycles'],
                     'reference_instret_delta': r['reference_instret_delta'], 'native_instret_delta': r['native_instret_delta'],
                     'signed_error_pct': 100 * (r['native_cycles'] - r['reference_cycles']) / r['reference_cycles'],
                     'coefficient_fit_eligible': r['family_for_reporting_only'] not in EXCLUDED})
    groups = collections.defaultdict(list)
    for r in rows:
        if True:  # Primary objective includes every TRAIN parent family.
            groups[(r['parent_case_id'], r['hart'])].append(r)
    train_groups = [v for v in groups.values() if v[0]['partition'] == 'train']
    objective = statistics.mean((statistics.median(r['signed_error_pct'] for r in v) / 100) ** 2 for v in train_groups)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'signed-regions.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    parts = ('train', 'internal_validation')
    result = {'schema': 'iris.empirical_compute_actual_counter_evaluation.v1', 'pass': True,
              'calibration_identity': report['calibration_identity'], 'native_binary_sha256': report['native_binary_sha256'],
              'fixture_sha256': report['fixture_sha256'], 'reference_archive_sha256': report['reference_archive_sha256'],
              'reference_elf_sha256': report['reference_elf_sha256'], 'regions': len(rows),
              'actual_calibrated_native_replay_completed': True,
              'overall_including_unqualified_families': {p: metrics([r for r in rows if r['partition'] == p]) for p in parts},
              'fit_eligible_only': {p: metrics([r for r in rows if r['partition'] == p and r['coefficient_fit_eligible']]) for p in parts},
              'per_family': {p: {f: metrics([r for r in rows if r['partition'] == p and r['family'] == f]) for f in sorted({r['family'] for r in rows if r['partition'] == p})} for p in parts},
              'per_family_hart': [{'partition': p, 'family': f, 'hart': h, **metrics([r for r in rows if r['partition'] == p and r['family'] == f and r['hart'] == h])} for p in parts for f in sorted({r['family'] for r in rows if r['partition'] == p}) for h in range(3) if any(r['partition'] == p and r['family'] == f and r['hart'] == h for r in rows)],
              'train_objective': {'name': 'mean_squared_relative_error_of_ALL_parent_hart_trial_medians', 'value': objective,
                                  'training_parent_hart_groups': len(train_groups), 'all_families_included':True, 'atomic_and_polling_included':True, 'selection_uses_internal_validation': False, 'methodology_correction_after_development_review':True},
              'normal_guest_exit_verified': False, 'whole_run_timing_validated': False,
              'internal_validation_scope': 'Development split; earlier diagnostics viewed, not blind acceptance.',
              'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
              'full_model_certified': False, 'source_image_association_verified': False,
              'input_sha256': {str(p.resolve()): sha(p) for p in (pathlib.Path(__file__), args.regions, args.regions.with_name('report.json'))},
              'output_sha256': {str((args.output / 'signed-regions.jsonl').resolve()): sha(args.output / 'signed-regions.jsonl')}}
    (args.output / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'report': str(args.output / 'report.json'), 'overall': result['overall_including_unqualified_families'], 'train_objective': result['train_objective']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--regions', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    main(parser.parse_args())
