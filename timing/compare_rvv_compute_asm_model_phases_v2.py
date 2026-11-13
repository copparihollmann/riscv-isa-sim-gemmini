#!/usr/bin/env python3
"""No-refit model-to-model phase comparison. Never opens hardware timings."""
import argparse
import collections
import copy
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(value, message):
    if not value:
        raise ValueError(message)


def compare(before, after, cases):
    ids = [case['case_id'] for case in cases]
    need(len(ids) == 1320 and len(set(ids)) == 1320, 'Canonical 1320 unique cases')
    need([row['case_id'] for row in before] == ids == [row['case_id'] for row in after],
         'Every canonical case/repetition retained in actual order')
    result = []
    numeric_fields = ('checksum', 'expected_checksum', 'mismatch_or', 'checked_words', 'vl')
    instret_fields = ('instret_delta', 'issue_instret_delta', 'drain_instret_delta')
    phases = ('issue', 'drain', 'total')
    for old, new, case in zip(before, after, cases):
        for row in (old, new):
            need(row['pass'] is True and row['mismatch_or'] == 0, 'Actual independent numeric checks')
            for key in numeric_fields + instret_fields + ('hart', 'start_cycle', 'issue_cycle', 'end_cycle'):
                need(type(row[key]) is int and row[key] >= 0, 'Typed nonnegative actual numeric/counter field')
            need(row['hart'] == case['hart'] and row['trial_id'] == case['trial_id'], 'Compiled role/trial')
            need(row['checksum'] == row['expected_checksum'] == case['expected_checksum'],
                 'Independent source corpus golden')
            need(row['start_cycle'] < row['issue_cycle'] <= row['end_cycle'], 'Ordered phase endpoints')
            need(row['issue_instret_delta'] + row['drain_instret_delta'] == row['instret_delta'],
                 'Actual retired phase counts sum')
        need(all(old[key] == new[key] for key in numeric_fields), 'Identical actual numerical values/coverage')
        old_cycles = (old['issue_cycle'] - old['start_cycle'], old['end_cycle'] - old['issue_cycle'],
                      old['end_cycle'] - old['start_cycle'])
        new_cycles = (new['issue_cycle'] - new['start_cycle'], new['end_cycle'] - new['issue_cycle'],
                      new['end_cycle'] - new['start_cycle'])
        entry = {key: case[key] for key in ('case_id', 'hart', 'kind', 'sew', 'lmul', 'mode', 'n',
                                          'bytes', 'trial_id', 'internal_split')}
        entry['numeric_unchanged'] = True
        entry['instret'] = {key: {'before': old[key], 'after': new[key], 'delta': new[key] - old[key]}
                           for key in instret_fields}
        for name, previous, current in zip(phases, old_cycles, new_cycles):
            entry[name] = {'before_model_cycles': previous, 'after_model_cycles': current,
                           'delta_cycles': current - previous}
        result.append(entry)
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    old_dir = ROOT / 'build/rvv-compute-asm-C12-TRAIN-replay-v1'
    new_dir = ROOT / 'build/rvv-compute-asm-FENCE-no-refit-replay-v1'
    build = ROOT / 'build/rvv-compute-asm-v5'
    fixture_proof = ROOT / 'build/rvv-compute-asm-FENCE-no-refit-inputs-v1/proof.json'
    need(sha(old_dir / 'run.json') == '50aa3757cd9db212d5776ddaa89422aaf2da49368a9c9f528966a6539edce923',
         'Exact frozen C12 fitted prediction')
    proof = json.loads(fixture_proof.read_text())
    need(proof['pass'] is True and proof['actual_parameter_fit_performed'] is False
         and proof['all_parameter_tokens_byte_identical'] is True, 'Fixed no-refit fixture lineage')
    bindings = {str(Path(__file__).resolve()): sha(Path(__file__).resolve()),
                str(fixture_proof): sha(fixture_proof),
                str(build / 'corpus.json'): sha(build / 'corpus.json')}
    runs = []
    for directory in (old_dir, new_dir):
        run = json.loads((directory / 'run.json').read_text())
        need(run['pass'] is True and run['regions'] == 1320
             and run['complete_per_element_goldens'] == 184128
             and run['actual_CSR_ELF_endpoint_joins'] == 3960, 'Complete actual replay')
        need(run['normal_guest_exit_verified'] is False
             and run['intentional_postmeasurement_debugger_stop'] is True,
             'Explicit pre-UART controlled-stop scope')
        for name, digest in {**run['input_sha256'], **run['output_sha256']}.items():
            need(sha(Path(name)) == digest, 'Changed actual replay evidence: ' + name)
            if name in bindings:
                need(bindings[name] == digest, 'Conflicting evidence identity')
            bindings[name] = digest
        bindings[str(directory / 'run.json')] = sha(directory / 'run.json')
        runs.append(run)
    need(runs[0]['input_sha256'][str(build / 'guest.elf')]
         == runs[1]['input_sha256'][str(build / 'guest.elf')]
         == '44c983d8495fb274a260b5d9b376d05458ff94d7365153b71cefb607fd624aaa', 'Exact unchanged ELF')
    need(runs[1]['native_epoch_uncalibrated'] is True and runs[1]['fit_performed'] is False,
         'New source epoch is uncalibrated, no refit')
    before = [json.loads(line) for line in (old_dir / 'regions.jsonl').read_text().splitlines()]
    after = [json.loads(line) for line in (new_dir / 'regions.jsonl').read_text().splitlines()]
    cases = json.loads((build / 'corpus.json').read_text())['cases']
    result = compare(before, after, cases)
    negatives = []

    def refused(name, mutant):
        try:
            compare(before, mutant, cases)
        except ValueError as error:
            negatives.append({'name': name, 'rejected': True, 'reason': str(error)})
            return
        raise RuntimeError('Counterfactual accepted: ' + name)

    mutant = copy.deepcopy(after)
    mutant[0]['checksum'] ^= 1
    refused('changed_actual_checksum', mutant)
    mutant = copy.deepcopy(after)
    mutant[0]['instret_delta'] = True
    refused('counter_boolean', mutant)
    mutant = copy.deepcopy(after)
    mutant[0]['issue_cycle'] = mutant[0]['start_cycle'] - 1
    refused('reversed_phase', mutant)
    mutant = copy.deepcopy(after)
    mutant[0]['issue_instret_delta'] += 1
    refused('invented_phase_instret', mutant)
    refused('missing_repetition', after[:-1])
    mutant = copy.deepcopy(after)
    mutant[0], mutant[1] = mutant[1], mutant[0]
    refused('case_order_join_error', mutant)
    grouped = collections.defaultdict(list)
    for row in result:
        for group in ('all', 'hart:' + str(row['hart']), 'kind:' + row['kind'],
                      'split:' + row['internal_split']):
            grouped[group].append(row)
    groups = {}
    for group, rows in grouped.items():
        groups[group] = {}
        for phase in ('issue', 'drain', 'total'):
            delta = [row[phase]['delta_cycles'] for row in rows]
            groups[group][phase] = {'rows': len(rows), 'changed': sum(value != 0 for value in delta),
                                    'minimum_delta_cycles': min(delta), 'maximum_delta_cycles': max(delta),
                                    'median_delta_cycles': statistics.median(delta)}
    (out / 'regions.jsonl').write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in result))
    summary_path = new_dir / 'native-summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    report = {
        'schema': 'iris.rvv_compute_asm_FENCE_fixed_cost_model_delta.v2', 'pass': True,
        'regions': 1320, 'complete_per_element_goldens': 184128, 'CSR_ELF_joins_each': 3960,
        'all_numeric_values_and_coverage_unchanged': True,
        'instret_mismatches': {field: sum(row['instret'][field]['delta'] != 0 for row in result)
                              for field in ('instret_delta', 'issue_instret_delta', 'drain_instret_delta')},
        'groups': groups, 'source_FENCE_tail_admissions': summary.get('opu_FM0_fence_admissions'),
        'FENCE_admission_count_observed': summary_path.exists(),
        'missing_final_summary_scope': 'Intentional pre-UART debugger quit does not emit the final summary; null admission count means unobserved, not zero. Exact selected fixture and executing pair are bound; finite separate activation witnesses stay separately scoped.',
        'corruption_controls': negatives, 'native_epoch_uncalibrated': True,
        'parameters_refitted': False, 'hardware_timing_labels_consumed': False,
        'normal_HTIF_or_end_to_end_claim': False,
        'source_image_association': False, 'timing_accuracy_certified': False,
        'input_sha256': bindings, 'regions_sha256': sha(out / 'regions.jsonl')
    }
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'all': groups['all'], 'instret_mismatches': report['instret_mismatches'],
                      'FENCE_tail_admissions': report['source_FENCE_tail_admissions'],
                      'report_sha256': sha(out / 'report.json')}))


if __name__ == '__main__':
    main()
