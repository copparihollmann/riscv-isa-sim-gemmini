#!/usr/bin/env python3
"""Root-only validation: freeze actual predictions before opening all1320 labels."""
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'firesim'))
from analyze_rvv_compute_heldout_asm import analyze
from replay_rvv_compute_heldout_asm_v1 import PLAN, READY, need, sha, verify_bindings
from compare_rvv_compute_asm_reserved_v1 import stats


def compare(cases, hardware, native):
    ids = [case['case_id'] for case in cases]
    need(len(ids) == len(set(ids)) == len(hardware) == len(native) == 1320,
         'All1320 cases and repetitions required')
    need(ids == [row['case_id'] for row in hardware] == [row['case_id'] for row in native],
         'Canonical complete compiled order')
    result = []
    for case, actual, prediction in zip(cases, hardware, native):
        need(case['internal_split'] == 'reserved_holdout'
             and case['validation_role'] == 'protected_validation_only', 'No training rows')
        for row in (actual, prediction):
            need(row['pass'] is True and row['mismatch_or'] == 0 and
                 type(row['hart']) is int and row['hart'] == case['hart'] and
                 type(row['trial_id']) is int and row['trial_id'] == case['trial_id'],
                 'Actual passing case/hart/trial identity')
            geometry = dict(kind=case['kind_id'], sew=case['sew'], lmul=case['lmul'],
                            mode=case['mode'], operations=case['n'], vector_bytes=case['bytes'], vl=case['vl'])
            need(all(type(row[key]) is int and row[key] == value for key, value in geometry.items()),
                 'Exact compiled operation/type/shape geometry')
            need(row['checksum'] == row['expected_checksum'] == case['expected_checksum']
                 and type(row['checksum']) is int and type(row['checked_words']) is int
                 and row['checked_words'] == (1024 if case['kind'].startswith('matrix_')
                                             else case['vl'] * case['streams']),
                 'Same independent complete word coverage/goldens')
            for key in ('start_cycle', 'issue_cycle', 'end_cycle', 'instret_delta',
                        'issue_instret_delta', 'drain_instret_delta'):
                need(type(row[key]) is int and 0 <= row[key] < 2**64, 'Typed actual counters')
            need(row['start_cycle'] < row['issue_cycle'] <= row['end_cycle']
                 and row['issue_instret_delta'] + row['drain_instret_delta'] == row['instret_delta'],
                 'Ordered actual phase counts')
        row = {key: case[key] for key in ('case_id', 'hart', 'kind', 'sew', 'lmul', 'mode',
                                          'n', 'bytes', 'trial_id')}
        row['instret'] = {key: dict(hardware=actual[key], native=prediction[key],
                                   mismatch=actual[key] != prediction[key])
                         for key in ('instret_delta', 'issue_instret_delta', 'drain_instret_delta')}
        for phase, begin, end in (('total', 'start_cycle', 'end_cycle'),
                                  ('issue', 'start_cycle', 'issue_cycle'),
                                  ('drain', 'issue_cycle', 'end_cycle')):
            target, modeled = actual[end] - actual[begin], prediction[end] - prediction[begin]
            row[phase] = dict(hardware_cycles=target, native_cycles=modeled,
                             signed_error_percent=100 * (modeled-target) / target if target else None,
                             zero_duration_mismatch=target == 0 and modeled != 0)
        result.append(row)
    return result


def main(args):
    job, build, model, out = [p.resolve() for p in (args.job, args.build, args.model, args.output)]
    need(not out.exists(), 'Fresh immutable comparison directory required')
    need(sha(model / 'freeze.json') == args.freeze_sha256, 'Exact preselected prediction freeze')
    freeze = json.loads((model / 'freeze.json').read_text())
    need(freeze['schema'] == 'iris.protected_ASM_prediction_freeze.v1' and freeze['pass'] is True
         and freeze['protected_timing_labels_consumed'] is False and freeze['fitting_permitted'] is False
         and freeze['source_plan_sha256'] == PLAN, 'Sealed-label prediction policy required')
    need(sha(model / 'run.json') == freeze['run_sha256'], 'Frozen actual prediction unchanged')
    verify_bindings(freeze['input_sha256'])
    verify_bindings(freeze['output_sha256'])
    run = json.loads((model / 'run.json').read_text())
    need(run['schema'] == 'iris.protected_ASM_frozen_prediction.v1' and run['pass'] is True
         and run['regions'] == 1320 and run['complete_per_element_goldens'] == 184128
         and run['actual_CSR_ELF_endpoint_joins'] == 3960
         and run['reserved_timing_labels_consumed'] is False and run['fit_performed'] is False
         and run['train_regions'] == 0 and run['reserved_regions'] == 1320,
         'All actual prediction goldens and CSR/ELF joins required before label release')
    need(run['input_sha256'] == freeze['input_sha256'] and run['output_sha256'] == freeze['output_sha256']
         and run['input_sha256'].get(str(build / 'ready.json')) == READY
         and run['input_sha256'].get(str(build / 'guest.elf')) == sha(build / 'guest.elf')
         and run['input_sha256'].get(str(build / 'corpus.json')) == sha(build / 'corpus.json'),
         'Exact protected ELF/corpus and prediction closure')
    out.mkdir(parents=True)
    (out / 'label-release.json').write_text(json.dumps(dict(
        schema='iris.protected_timing_label_release.v1', prediction_freeze_sha256=args.freeze_sha256,
        frozen_at_utc=freeze['frozen_at_utc'], all_prediction_bindings_reverified=True,
        fit_or_selection_on_this_reference_permitted=False), indent=2) + '\n')
    verified = out / 'hardware-revalidation'
    need(analyze(job, verified) == 0, 'Fresh strict raw archive validation required')
    reference = json.loads((verified / 'report.json').read_text())
    need(reference['pass'] is True and reference['archive_verified'] is True
         and reference['regions'] == 1320 and reference['train_regions'] == 0
         and reference['reserved_regions'] == 1320 and reference['protected_validation_only'] is True,
         'Exact complete protected reference')
    readrows = lambda path: [json.loads(line) for line in path.read_text().splitlines()]
    cases = json.loads((build / 'corpus.json').read_text())['cases']
    rows = compare(cases, readrows(verified / 'regions.jsonl'), readrows(model / 'regions.jsonl'))
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in rows:
        groups = ('all', 'hart:' + str(row['hart']), 'kind:' + row['kind'],
                  'hart:' + str(row['hart']) + ':kind:' + row['kind'],
                  'kind:' + row['kind'] + ':sew:' + str(row['sew']) + ':lmul:' + str(row['lmul']))
        for phase in ('total', 'issue', 'drain'):
            value = row[phase]['signed_error_percent']
            if value is not None:
                for group in groups:
                    grouped[group][phase].append(value)
    (out / 'regions.jsonl').write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows))
    phase_pass = lambda phase: all(not row[phase]['zero_duration_mismatch']
        and (row[phase]['signed_error_percent'] is None or abs(row[phase]['signed_error_percent']) <= 2)
        for row in rows)
    report = dict(schema='iris.protected_ASM_all1320_validation.v1', **{'pass': True},
                  regions=1320, no_refit=True, train_regions=0, all_reserved_rows_and_repetitions_retained=True,
                  prediction_freeze_sha256=args.freeze_sha256,
                  measured_region_totals_all_within2_percent=phase_pass('total'),
                  measured_phases_all_within2_percent=all(phase_pass(p) for p in ('total', 'issue', 'drain')),
                  zero_duration_mismatches={p: sum(row[p]['zero_duration_mismatch'] for row in rows)
                                            for p in ('total', 'issue', 'drain')},
                  instret_mismatches={k: sum(row['instret'][k]['mismatch'] for row in rows)
                                     for k in ('instret_delta', 'issue_instret_delta', 'drain_instret_delta')},
                  timing_accuracy_certified=False, source_image_association_verified=False,
                  normal_guest_exit_or_end_to_end_model_timing_claim=False,
                  model_scope='Exact frozen source candidate; controlled postmeasurement debugger stop before UART',
                  groups={group: {phase: stats(values) for phase, values in phases.items()}
                          for group, phases in sorted(grouped.items())},
                  input_sha256={str(path): sha(path) for path in
                      (Path(__file__).resolve(), ROOT / 'timing/replay_rvv_compute_heldout_asm_v1.py',
                       ROOT / 'timing/compare_rvv_compute_asm_reserved_v1.py', job / 'run.json',
                       verified / 'report.json', verified / 'regions.jsonl', build / 'corpus.json',
                       model / 'run.json', model / 'freeze.json', model / 'regions.jsonl')},
                  output_regions_sha256=sha(out / 'regions.jsonl'))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(pass_=True, regions=1320, groups=report['groups']['all'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    for name in ('job', 'build', 'model', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--freeze-sha256', required=True)
    main(parser.parse_args())
