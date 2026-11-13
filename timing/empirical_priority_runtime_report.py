#!/usr/bin/env python3
"""Compare actual calibrated counter regions with their byte-matched FPGA ELF.

This reader does not produce predictions or select parameters. All region labels
and address/bank annotations below are reporting keys, never runtime inputs.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def load_rows(path):
    rows = [json.loads(line) for line in pathlib.Path(path).read_text().splitlines()]
    by_key = {}
    for row in rows:
        if type(row.get('hart')) is not int or row['hart'] not in (0, 1, 2):
            raise ValueError('Invalid hart')
        key = (row['case_id'], row['hart'])
        if key in by_key:
            raise ValueError('Duplicate actual region ' + str(key))
        for field in ('native_cycles', 'reference_cycles'):
            if type(row.get(field)) is not int or row[field] <= 0:
                raise ValueError('Invalid integer cycle span ' + field)
        if row.get('checksum_validated') is not True:
            raise ValueError('Unqualified region checksum')
        by_key[key] = row
    return by_key


def quantile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * fraction
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    return values[lower] * (upper - pos) + values[upper] * (pos - lower) if upper != lower else values[lower]


def metrics(rows, field='signed_error_pct'):
    errors = [row[field] for row in rows]
    absolute = [abs(value) for value in errors]
    return {
        'regions': len(rows),
        'signed_mean_pct': statistics.mean(errors) if errors else None,
        'signed_median_pct': statistics.median(errors) if errors else None,
        'absolute_median_pct': statistics.median(absolute) if errors else None,
        'absolute_p90_pct': quantile(absolute, .9),
        'absolute_max_pct': max(absolute) if errors else None,
        'within_2pct_count': sum(value <= 2 for value in absolute),
        'within_2pct_fraction': sum(value <= 2 for value in absolute) / len(rows) if rows else None,
    }


def compare(baseline, calibrated, split):
    if set(baseline) != set(calibrated):
        raise ValueError('Baseline/calibrated region domains differ')
    result = []
    for key, row in calibrated.items():
        before = baseline[key]
        for field in ('parent_case_id', 'partition', 'reference_cycles', 'reference_instret_delta', 'family_for_reporting_only'):
            if row[field] != before[field]:
                raise ValueError('Reference identity mismatch ' + field)
        parent = split['split'][row['parent_case_id']]
        if parent['partition'] != row['partition']:
            raise ValueError('Frozen split changed')
        ref = row['reference_cycles']
        metadata = row.get('case_metadata_for_reporting_only', {})
        result.append({
            'case_id': row['case_id'], 'parent_case_id': row['parent_case_id'],
            'semantic_parent_case_id': parent['semantic_parent_case_id'],
            'partition': row['partition'], 'family': row['family_for_reporting_only'],
            'hart': row['hart'], 'reference_cycles': ref,
            'baseline_native_cycles': before['native_cycles'],
            'calibrated_native_cycles': row['native_cycles'],
            'signed_error_pct': 100 * (row['native_cycles'] - ref) / ref,
            'baseline_signed_error_pct': 100 * (before['native_cycles'] - ref) / ref,
            'reference_instret_delta': row['reference_instret_delta'],
            'native_instret_delta': row['native_instret_delta'],
            'baseline_instret_delta': before['native_instret_delta'],
            'report_target': metadata.get('target_region', ''),
            'report_kind': metadata.get('kind', ''), 'report_n': metadata.get('n', ''),
            'report_mask': metadata.get('mask', ''), 'report_stride': metadata.get('stride', ''),
            'report_spread': metadata.get('spread', ''),
            'report_addresses': metadata.get('addresses_by_hart', []),
            'report_bit6_sequences': metadata.get('bank_bit6_sequence_by_hart', []),
        })
    return sorted(result, key=lambda r: (r['case_id'], r['hart']))


def verify_join(report_path, rows_path):
    report = json.loads(report_path.read_text())
    if report.get('schema') != 'iris.empirical_priority_runtime_feature_join.v2':
        raise ValueError('Wrong actual runtime join contract')
    if report.get('status') not in ('qualified_partial', 'passed_all_measured_regions'):
        raise ValueError('Actual runtime join not qualified')
    if report.get('global_heldout_timings_consumed') is not False:
        raise ValueError('Global heldout contamination')
    if report.get('regions_sha256') != sha(rows_path):
        raise ValueError('Joined rows changed')
    for path, digest in report['input_sha256'].items():
        path = pathlib.Path(path)
        path = path if path.is_absolute() else ROOT / path
        if sha(path) != digest:
            raise ValueError('Join input changed ' + str(path))
    canonical_path = report_path.parent / 'native-baseline.json'
    if sha(canonical_path) != report['native_baseline_sha256']:
        raise ValueError('Canonical native receipt changed')
    return report


def verify_runtime_identity(report_path, parameters, fixture):
    canonical = json.loads((report_path.parent / 'native-baseline.json').read_text())
    argv = canonical['argv']
    native = pathlib.Path(argv[0])
    uart = pathlib.Path(next(s.split('=', 1)[1] for s in argv if s.startswith('--extlib=')))
    actual_fixture = pathlib.Path(next(s.split('=', 1)[1] for s in argv if s.startswith('--iris-timing-fixture=')))
    if sha(native) != parameters['native_binary_sha256'] or sha(uart) != parameters['uart_library_sha256']:
        raise ValueError('Selected parameter native/UART identity does not match actual replay')
    if actual_fixture.resolve() != fixture.resolve() or sha(actual_fixture) != sha(fixture):
        raise ValueError('Wrong actual fixture')
    identity = [s.split()[2] for s in fixture.read_text().splitlines() if s.startswith('empirical_profile ')]
    if identity != [parameters['calibration_identity']]:
        raise ValueError('Fixture calibration identity differs from parameters')


def main(args):
    before_report = verify_join(args.baseline_report, args.baseline)
    actual_report = verify_join(args.calibrated_report, args.calibrated)
    if before_report['reference_archive_sha256'] != actual_report['reference_archive_sha256']:
        raise ValueError('Baseline/calibrated hardware reference differs')
    baseline, actual = load_rows(args.baseline), load_rows(args.calibrated)
    split = json.loads(args.split.read_text())
    parameters = json.loads(args.parameters.read_text())
    if parameters.get('actual_parameter_fit_performed') is not True:
        raise ValueError('Parameters are not fitted')
    if parameters.get('global_heldout_timings_consumed') is not False:
        raise ValueError('Contaminated parameter fitting')
    verify_runtime_identity(args.calibrated_report, parameters, args.fixture)
    rows = compare(baseline, actual, split)
    groups = collections.defaultdict(list)
    banks = collections.defaultdict(list)
    trials = collections.defaultdict(list)
    for row in rows:
        groups[(row['partition'], row['family'], row['hart'])].append(row)
        if row['report_target']:
            key = tuple(str(row[f]) for f in ('partition', 'hart', 'report_target', 'report_kind', 'report_n', 'report_mask', 'report_stride', 'report_spread'))
            banks[key].append(row)
        trials[(row['parent_case_id'], row['hart'])].append(row)
    for values in trials.values():
        if len(values) != 3:
            raise ValueError('Matched prefix lost a repetition group')
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    (out / 'signed-regions.jsonl').write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows))
    with (out / 'signed-regions.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, list) else value for key, value in row.items()})
    per_family_hart = [dict(partition=k[0], family=k[1], hart=k[2], **metrics(v), baseline=metrics(v, 'baseline_signed_error_pct')) for k, v in sorted(groups.items())]
    per_family = {}
    for part in ('train', 'internal_validation'):
        per_family[part] = {family: metrics([r for r in rows if r['partition'] == part and r['family'] == family]) for family in sorted({r['family'] for r in rows if r['partition'] == part})}
    variance = []
    for (parent, hart), values in sorted(trials.items()):
        native = [row['calibrated_native_cycles'] for row in values]
        ref = [row['reference_cycles'] for row in values]
        variance.append({'parent_case_id': parent, 'hart': hart, 'repetitions': 3,
                         'reference_min_cycles': min(ref), 'reference_max_cycles': max(ref),
                         'reference_relative_range_pct': 100 * (max(ref) - min(ref)) / statistics.median(ref),
                         'native_min_cycles': min(native), 'native_max_cycles': max(native),
                         'native_relative_range_pct': 100 * (max(native) - min(native)) / statistics.median(native)})
    (out / 'repetitions.json').write_text(json.dumps(variance, indent=2, sort_keys=True) + '\n')
    coverage = []
    for configured in parameters['families']:
        hart, family = configured['hart'], configured['family']
        observed = [r for r in actual.values() if r['hart'] == hart and r['features'].get(family, {}).get('instructions', 0)]
        coverage.append({'hart': hart, 'family': family,
                         'observed_regions': len(observed),
                         'observed_instructions': sum(r['features'][family]['instructions'] for r in observed),
                         'observed_work': sum(r['features'][family]['work'] for r in observed),
                         'observed_work_per_instruction': sorted({r['features'][family]['work'] / r['features'][family]['instructions'] for r in observed}),
                         'training_work_per_instruction': configured.get('training_work_per_instruction'),
                         'scope': configured['scope']})
    report = {
        'schema': 'iris.empirical_priority_actual_runtime_validation.v1',
        'status': 'actual_partial_calibrated_counter_replay_completed',
        'actual_parameter_fit_performed': True, 'actual_calibrated_native_replay_completed': True,
        'reference_archive_sha256': actual_report['reference_archive_sha256'],
        'calibration_identity': parameters['calibration_identity'],
        'native_binary_sha256': parameters['native_binary_sha256'],
        'uart_library_sha256': parameters['uart_library_sha256'],
        'fixture_sha256': sha(args.fixture), 'parameters_sha256': sha(args.parameters),
        'regions': len(rows), 'reference_regions': actual_report['reference_regions'],
        'partial': actual_report['partial'], 'unmatched_reference_regions': actual_report['reference_regions'] - len(rows),
        'overall_including_unqualified_families': {part: metrics([r for r in rows if r['partition'] == part]) for part in ('train', 'internal_validation')},
        'baseline_overall_same_regions': {part: metrics([r for r in rows if r['partition'] == part], 'baseline_signed_error_pct') for part in ('train', 'internal_validation')},
        'per_family': per_family, 'per_family_hart': per_family_hart,
        'configured_family_actual_coverage': coverage,
        'unreached_configured_family_rules': [r for r in coverage if r['observed_instructions'] == 0],
        'per_hart': {str(h): metrics([r for r in rows if r['hart'] == h]) for h in range(3)},
        'per_hart_target_mask_stride_spread': [dict(zip(('partition', 'hart', 'target', 'kind', 'n', 'mask', 'stride', 'spread'), k), **metrics(v)) for k, v in sorted(banks.items())],
        'reference_instret_mismatch_regions': sum(r['native_instret_delta'] != r['reference_instret_delta'] for r in rows),
        'native_baseline_instret_changed_regions': sum(r['native_instret_delta'] != r['baseline_instret_delta'] for r in rows),
        'repetition_groups': len(variance), 'all_numeric_goldens_passed': True,
        'runtime_classification_only': True, 'case_labels_and_bank_annotations_used_only_for_reporting': True,
        'internal_validation_scope': 'Development set with earlier residual diagnostics viewed; not blind acceptance.',
        'normal_guest_exit_verified': False, 'whole_run_or_end_to_end_timing_validated': False,
        'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
        'full_model_certified': False, 'rtl_certified': False, 'source_image_association_verified': False,
        'unqualified': parameters['unapplied'],
        'input_sha256': {str(p.resolve().relative_to(ROOT)): sha(p) for p in [pathlib.Path(__file__), args.baseline, args.baseline_report, args.calibrated, args.calibrated_report, args.split, args.parameters, args.fixture]},
        'output_sha256': {str((out / name).resolve().relative_to(ROOT)): sha(out / name) for name in ('signed-regions.jsonl', 'signed-regions.csv', 'repetitions.json')},
    }
    (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'report': str(out / 'report.json'), 'actual_runtime_metrics': report['overall_including_unqualified_families']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=pathlib.Path, required=True)
    parser.add_argument('--baseline-report', type=pathlib.Path, required=True)
    parser.add_argument('--calibrated', type=pathlib.Path, required=True)
    parser.add_argument('--calibrated-report', type=pathlib.Path, required=True)
    parser.add_argument('--parameters', type=pathlib.Path, required=True)
    parser.add_argument('--fixture', type=pathlib.Path, required=True)
    parser.add_argument('--split', type=pathlib.Path, default=ROOT / 'calibration/empirical-priority-v2/split.json')
    parser.add_argument('--output', type=pathlib.Path, required=True)
    main(parser.parse_args())
