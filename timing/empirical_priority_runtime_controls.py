#!/usr/bin/env python3
"""Independent arithmetic/identity corruptions for the actual-counter reader."""
import copy
import hashlib
import json
import pathlib
import tempfile

from empirical_priority_runtime_report import compare, load_rows, metrics, quantile, verify_join, verify_runtime_identity

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    output = ROOT / 'build/empirical-priority-runtime-reader-controls-v1'
    output.mkdir(exist_ok=False)
    source = ROOT / 'timing/empirical_priority_runtime_report.py'
    baseline_path = ROOT / 'build/empirical-priority-28a0-features-v1/regions.jsonl'
    split_path = ROOT / 'calibration/empirical-priority-v2/split.json'
    row = json.loads(baseline_path.read_text().splitlines()[0])
    split = json.loads(split_path.read_text())
    key = (row['case_id'], row['hart'])
    baseline = {key: row}
    candidate = copy.deepcopy(baseline)
    candidate[key]['native_cycles'] = row['reference_cycles'] * 2
    actual = compare(baseline, candidate, split)
    assert actual[0]['signed_error_pct'] == 100
    assert actual[0]['reference_cycles'] == row['reference_cycles']
    assert actual[0]['baseline_native_cycles'] == row['native_cycles']
    assert metrics(actual)['within_2pct_count'] == 0
    assert metrics(actual)['absolute_p90_pct'] == 100
    assert quantile([1, 2, 3, 4], .9) == 3.7
    assert metrics([])['regions'] == 0 and metrics([])['absolute_median_pct'] is None
    controls = []

    def rejects(name, action):
        try:
            action()
        except (ValueError, KeyError):
            controls.append({'control': name, 'rejected': True})
        else:
            raise AssertionError('Did not reject ' + name)

    for field, value in [('parent_case_id', 'wrong'), ('partition', 'wrong'),
                         ('reference_cycles', row['reference_cycles'] + 1),
                         ('reference_instret_delta', row['reference_instret_delta'] + 1),
                         ('family_for_reporting_only', 'wrong')]:
        corrupted = copy.deepcopy(candidate)
        corrupted[key][field] = value
        rejects('changed_' + field, lambda: compare(baseline, corrupted, split))
    rejects('missing_region', lambda: compare(baseline, {}, split))
    with tempfile.TemporaryDirectory(prefix='iris-actual-counter-controls-') as directory:
        path = pathlib.Path(directory) / 'rows.jsonl'

        def bad_rows(rows):
            path.write_text(''.join(json.dumps(value) + '\n' for value in rows))
            return load_rows(path)

        for field, value in [('hart', True), ('hart', 3), ('native_cycles', True),
                             ('native_cycles', -1), ('reference_cycles', 0),
                             ('reference_cycles', 1.5), ('checksum_validated', False)]:
            bad = copy.deepcopy(row)
            bad[field] = value
            rejects('invalid_' + field + '_' + str(value), lambda: bad_rows([bad]))
        rejects('duplicate_region', lambda: bad_rows([row, row]))
        assert len(bad_rows([row])) == 1

        # Verify a byte-bound real baseline join, then independently corrupt
        # only its declared rows digest. No fake predictions or fit claimed.
        original_report = ROOT / 'build/empirical-priority-28a0-features-v1/report.json'
        assert verify_join(original_report, baseline_path)['joined_regions'] == 3633
        report = json.loads(original_report.read_text())
        report['regions_sha256'] = '0' * 64
        corrupt_path = pathlib.Path(directory) / 'report.json'
        corrupt_path.write_text(json.dumps(report))
        rejects('changed_joined_rows_digest', lambda: verify_join(corrupt_path, baseline_path))
        parameters = {'native_binary_sha256': '0' * 64,
                      'uart_library_sha256': '0' * 64,
                      'calibration_identity': 'wrong'}
        rejects('parameter_native_pair_mismatch', lambda: verify_runtime_identity(original_report, parameters, ROOT / 'calibration/empirical-priority-28a0-runtime-v2/runtime.fixture'))
    receipt = {'schema': 'iris.empirical_actual_counter_reader_controls.v1', 'pass': True,
               'arithmetic_and_real_join_checks': 9, 'corruption_refusals': controls,
               'actual_calibrated_replay_performed': False,
               'global_heldout_timings_consumed': False, 'hardware_contacted': False,
               'input_sha256': {str(p): sha(p) for p in (pathlib.Path(__file__).resolve(), source, baseline_path, split_path)},
               'accuracy_or_model_certification_claimed': False}
    (output / 'reader-source.py').write_bytes(source.read_bytes())
    (output / 'controls-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
    (output / 'report.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'pass': True, 'corruption_refusals': len(controls), 'output': str(output)}))


if __name__ == '__main__':
    main()
