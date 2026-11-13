#!/usr/bin/env python3
"""Report as-executed one/two-worker scaling from verified heldout comparisons.

Only global CLINT windows measure concurrent elapsed time. Per-hart mcycle
durations are never summed into an application elapsed-time estimate.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scaling(phases, windows):
    if not isinstance(phases, list) or len(phases) != 8 or not isinstance(windows, list) or len(windows) != 8:
        raise ValueError('Complete eight-phase elapsed-time evidence required')
    indexed = {}
    for window in windows:
        phase = window.get('phase')
        if type(phase) is not int or not 0 <= phase < 8 or phase in indexed:
            raise ValueError('Unique typed phase identifiers required')
        for field in ('model_quantized_core_cycles', 'reference_quantized_core_cycles'):
            if type(window.get(field)) is not int or window[field] <= 1000:
                raise ValueError('Positive intervals exceeding the CLINT uncertainty required')
        if type(window.get('per_interval_quantization_bound_cycles')) is not int or window['per_interval_quantization_bound_cycles'] != 1000:
            raise ValueError('Explicit1000-core-cycle CLINT quantization bound required')
        indexed[phase] = window
    groups, phase_ids = {}, set()
    for phase in phases:
        ident, workers = phase.get('phase'), phase.get('workers')
        if (type(ident) is not int or ident not in indexed or ident in phase_ids
                or type(workers) is not int or workers not in (1, 2)
                or phase.get('op') not in ('gemm', 'conv2d') or phase.get('kind') not in ('shipped', 'twin')):
            raise ValueError('Recognized unique actual workload phases required')
        phase_ids.add(ident)
        group = groups.setdefault((phase['op'], phase['kind']), {})
        if workers in group: raise ValueError('Duplicate worker configuration')
        group[workers] = indexed[ident]
    if len(groups) != 4 or any(set(v) != {1, 2} for v in groups.values()):
        raise ValueError('Both worker counts required for every operation/variant')
    result = []
    for (op, kind), group in sorted(groups.items()):
        one, two = group[1], group[2]
        model_one, model_two = [r['model_quantized_core_cycles'] for r in (one, two)]
        ref_one, ref_two = [r['reference_quantized_core_cycles'] for r in (one, two)]
        model_ratio, ref_ratio = model_one / model_two, ref_one / ref_two
        model_low, model_high = (model_one - 1000) / (model_two + 1000), (model_one + 1000) / (model_two - 1000)
        ref_low, ref_high = (ref_one - 1000) / (ref_two + 1000), (ref_one + 1000) / (ref_two - 1000)
        result.append({'op': op, 'kind': kind, 'one_worker_phase': one['phase'], 'two_worker_phase': two['phase'],
            'model_one_worker_cycles': model_one, 'model_two_worker_cycles': model_two,
            'reference_one_worker_cycles': ref_one, 'reference_two_worker_cycles': ref_two,
            'model_elapsed_ratio_one_over_two': model_ratio, 'reference_elapsed_ratio_one_over_two': ref_ratio,
            'model_ratio_interval': [model_low, model_high], 'reference_ratio_interval': [ref_low, ref_high],
            'signed_ratio_error_percent': 100 * (model_ratio / ref_ratio - 1),
            'signed_ratio_error_interval_percent': [100 * (model_low / ref_high - 1), 100 * (model_high / ref_low - 1)],
            'scope': 'As-executed phase elapsed ratios; fixed phase order/cache histories are not isolated counterfactuals.'})
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--workload', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workload, comparison = json.loads(args.workload.read_text()), json.loads(args.comparison.read_text())
    if (comparison.get('schema') != 'iris.independent_compatible_heldout_timing_comparison.v1'
            or comparison.get('workload_manifest_sha256') != sha(args.workload)
            or comparison.get('ELF_sha256') != workload.get('ELF_sha256')
            or comparison.get('global_heldout_timings_used_for_fitting') is not False):
        raise ValueError('Exact independent comparison and workload identities required')
    for name, expected in comparison.get('input_sha256', {}).items():
        if sha(name) != expected: raise ValueError('Comparison evidence changed: ' + name)
    rows = scaling(workload['phases'], comparison['global_elapsed_windows'])
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    path = output / 'worker-scaling.csv'
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    report = {'schema': 'iris.independent_elapsed_worker_scaling.v1', 'status': 'measured_ratios_not_certification',
        'rows': rows, 'method': 'globalCLINTelapsed_one_worker/globalCLINTelapsed_two_workers',
        'model_prediction_sha256': comparison['model_prediction_sha256'],
        'reference_validation_sha256': comparison['reference_validation_sha256'],
        'hardware_contacted': False, 'timing_certified': False, 'whole_batch_end_to_end_certified': False,
        'fitting_or_model_selection_performed': False,
        'input_sha256': {str(p.resolve()): sha(p) for p in (Path(__file__), args.workload, args.comparison)},
        'output_sha256': {str(path): sha(path)}}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'ratios': len(rows), 'hardware_contacted': False}))


if __name__ == '__main__': main()
