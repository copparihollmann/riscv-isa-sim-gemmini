#!/usr/bin/env python3
"""Root-only postfreeze comparison; every measured case and phase is retained."""
import collections
import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(value, message):
    if not value:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text())


def statistics_for(rows):
    errors = [r['signed_error_percent'] for r in rows if r['signed_error_percent'] is not None]
    absolute = sorted(abs(e) for e in errors)
    return dict(count=len(rows), defined_relative_errors=len(errors),
                zero_reference_count=sum(r['reference_cycles'] == 0 for r in rows),
                median_signed_percent=statistics.median(errors) if errors else None,
                median_absolute_percent=statistics.median(absolute) if absolute else None,
                p90_absolute_percent=absolute[math.ceil(.9 * len(absolute)) - 1] if absolute else None,
                maximum_absolute_percent=max(absolute) if absolute else None,
                within2=sum(r['within2'] for r in rows), quantile='nearest-rank-ceil')


def main():
    prediction = ROOT / 'build/zephyr-hart2-pow2-35a-OS-prediction-v1'
    hardware = ROOT / 'build/zephyr-hart2-pow2-FPGA-sealed-analysis-v1'
    freeze = prediction / 'freeze.json'
    need(sha(freeze) == '6a654e4bd7721526f525466496a39173444b4d0f83830f998d2bf6bcad018f9d',
         'Exact pre-unblinding model prediction freeze required')
    f = load(freeze)
    need(f['pass'] is True and f['hardware_timing_labels_consumed'] is False and
         f['fitting_permitted'] is False, 'Frozen no-fit prediction contract')
    for paths in (f['input_sha256'], f['output_sha256']):
        for name, expected in paths.items():
            need(sha(name) == expected, 'Changed frozen input/output: ' + name)
    need(sha(prediction / 'run.json') == f['run_sha256'], 'Changed prediction receipt')
    h = load(hardware / 'report.json')
    need(h['pass'] is True and h['regions'] == 648 and h['independent_elements'] == 181440
         and h['normal_driver_exit_status'] == 0 and h['performance_labels_sealed'] is True,
         'Independent hardware functional and archive gate must pass')
    for name, expected in h['artifact_sha256'].items():
        need(sha(hardware / name) == expected, 'Changed sealed artifact: ' + name)
    # No performance value is read until all frozen prediction/functional gates pass.
    opened = datetime.datetime.now(datetime.timezone.utc).isoformat()
    predicted = [json.loads(l) for l in (prediction / 'regions.jsonl').read_text().splitlines()]
    measured = load(hardware / 'regions.sealed.json')
    need(len(predicted) == len(measured) == 648, 'All648 rows, no filtering')
    output = ROOT / 'build/zephyr-hart2-pow2-35a-OS-root-validation-v2'
    output.mkdir(parents=True, exist_ok=False)
    rows, groups = [], collections.defaultdict(list)
    instret_mismatches = 0
    for index, (p, a) in enumerate(zip(predicted, measured)):
        need(p['region_index'] == a['region_index'] == index, 'Unique ordered region indices')
        for key in ('case_id', 'group', 'hart', 'logical_cpu', 'pin', 'role', 'hart_mask',
                    'trial', 'operations', 'checksum', 'ack'):
            need(type(p[key]) is type(a[key]) and p[key] == a[key], 'Region identity/golden: ' + key)
        need(type(a['actual_vl']) is int and
             a['actual_vl'] == (p['elements'] if p['kind'] == 0 else p['shape']),
             'Actual hardware VL must match the independently qualified geometry')
        need(p['hart'] in (0, 1) and a['guard_ok'] is p['guard_ok'] is True,
             'Compute-hart-only score and actual guards')
        need(a['failed_elements'] == 0 and a['checked_elements'] == p['elements'],
             'Independent full element coverage')
        kind = 'rvv' if p['kind'] == 0 else 'matrix_int8' if p['format'] == 0 else 'matrix_fp8'
        kind_detail = kind if kind != 'matrix_fp8' else kind + ':' + str(p['format'])
        mismatch = p['instret_delta'] != a['instret_delta']
        instret_mismatches += mismatch
        for phase, first, last in [('total', 'start_cycle', 'end_cycle'),
                                   ('issue', 'start_cycle', 'issue_cycle'),
                                   ('drain', 'issue_cycle', 'end_cycle')]:
            need(all(type(r[k]) is int for r in (p, a) for k in (first, last)), 'Typed counters')
            model, reference = p[last] - p[first], a[last] - a[first]
            need(model >= 0 and reference >= 0 and (phase != 'total' or reference > 0), 'Counter order')
            error = 100 * (model - reference) / reference if reference else None
            row = dict(region_index=index, case_id=p['case_id'], hart=p['hart'],
                       hart_mask=p['hart_mask'], trial=p['trial'], kind=kind_detail,
                       sew=p['sew'], lmul=p['lmul'], shape=p['shape'], operations=p['operations'],
                       split=p['split'], phase=phase, model_cycles=model,
                       reference_cycles=reference, signed_error_percent=error,
                       absolute_error_percent=abs(error) if error is not None else None,
                       within2=abs(error) <= 2 if error is not None else model == reference,
                       model_instret=p['instret_delta'], reference_instret=a['instret_delta'],
                       instret_mismatch=mismatch)
            rows.append(row)
            labels = ['all', 'split:' + p['split'], 'kind:' + kind, 'kind:' + kind_detail,
                      'hart:' + str(p['hart']), 'mask:' + str(p['hart_mask']),
                      'split:' + p['split'] + ':kind:' + kind,
                      'mask:' + str(p['hart_mask']) + ':kind:' + kind]
            for label in set(labels):
                groups[label, phase].append(row)
    (output / 'regions.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    summaries = collections.defaultdict(dict)
    for (label, phase), values in sorted(groups.items()):
        summaries[label][phase] = statistics_for(values)
    report = dict(schema='iris.zephyr_pow2_35a_OS_postfreeze_validation.v1', **{'pass': True},
                  opened_hardware_labels_at_UTC=opened, selected_before_hardware_run=True,
                  new_model_fitting_or_selection=False, retained_regions=648,
                  retained_phase_rows=len(rows), protected_validation=192, training_eligible=456,
                  instret_mismatch_regions=instret_mismatches, profile='source_os',
                  detailed_hart2_accuracy_scored=False,
                  all_region_totals_within2=all(r['within2'] for r in rows if r['phase'] == 'total'),
                  all_phases_within2=all(r['within2'] for r in rows),
                  full_model_timing_certified=False, source_image_association_verified=False,
                  normal_model_HTIF_or_end_to_end_speed_claim=False,
                  debugger_stepping_equivalence_scope='Finite f5d control passed; universal/648 normal-interleave equivalence unqualified',
                  interrupts_and_peer_traffic='Included as measured; no overhead/outlier subtraction',
                  groups=dict(summaries),
                  input_sha256={str(p): sha(p) for p in (Path(__file__).resolve(), freeze,
                      prediction / 'run.json', prediction / 'regions.jsonl', hardware / 'report.json',
                      hardware / 'regions.sealed.json')},
                  output_regions_sha256=sha(output / 'regions.jsonl'))
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report_sha256': sha(output / 'report.json'),
                      'total': report['groups']['all']['total'],
                      'instret_mismatches': instret_mismatches,
                      'by_kind': {k: v['total'] for k, v in report['groups'].items()
                                  if k in ('kind:rvv', 'kind:matrix_int8', 'kind:matrix_fp8')},
                      'by_mask': {k: v['total'] for k, v in report['groups'].items()
                                  if k in ('mask:1', 'mask:2', 'mask:3')},
                      'protected': report['groups']['split:protected_validation']['total']}))


if __name__ == '__main__':
    main()
