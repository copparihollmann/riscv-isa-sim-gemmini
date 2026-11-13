#!/usr/bin/env python3
"""Execute the frozen two-mode TRAIN-only selection rule; never publish a provider."""
import argparse
import json
import math
from pathlib import Path
from scalar_l2_hit_run import sha


def need(ok, message):
    if not ok:
        raise ValueError(message)


def main(a):
    plan_path, out = a.plan.resolve(), a.output.resolve()
    need(not out.exists(), 'New output required')
    plan = json.loads(plan_path.read_text())
    need(plan['schema'] == 'iris.pow2_scalar_cache_two_fixed_modes_selection_plan.v1'
         and plan['actual_fitted_comparisons_available_at_plan_creation'] is False
         and plan['further_parameter_fits'] is False, 'Frozen predeclared selection plan')
    reports = {'LRU': a.LRU_report.resolve(), 'source-ShuttleRandom': a.random_report.resolve()}
    need({p['mode'] for p in plan['policies']} == set(reports), 'Exactly two fixed modes')
    candidates, inputs = [], [plan_path]
    for policy in plan['policies']:
        mode = policy['mode']
        params, fixture = Path(policy['parameters']).resolve(), Path(policy['fixture']).resolve()
        need(sha(params) == policy['parameters_sha256'] and sha(fixture) == policy['fixture_sha256'],
             'Changed frozen parameters/fixture')
        report = json.loads(reports[mode].read_text())
        need(report['schema'] == 'iris.pow2_scalar_cache_actual_TRAIN_comparison.v1'
             and report['pass'] is True and report['mode'] == mode
             and report['no_reserved_timing_labels_consumed'] is True
             and report['rows_filtered'] is False
             and report['actual_guest_exit_and_all234_numeric_verified'] is True,
             'Complete actual same-mode TRAIN comparison required')
        for p, digest in report['input_sha256'].items():
            need(sha(p) == digest, 'Changed actual comparison input: ' + p)
        metrics = report['TRAIN_only_metrics']
        need(metrics['rows'] == 180 and metrics['instret_mismatches'] == 0
             and math.isfinite(metrics['relative_squared_loss_sum']),
             'All180 TRAIN rows and finite objective required')
        candidates.append({'mode': mode, 'parameters': str(params), 'fixture': str(fixture),
                           'comparison': str(reports[mode]), 'metrics': metrics})
        inputs += [params, fixture, reports[mode]]
    selected = min(candidates, key=lambda x: (x['metrics']['relative_squared_loss_sum'],
                                              x['mode'] != 'LRU'))
    out.mkdir(parents=True)
    (out / 'candidate.fixture').write_bytes(Path(selected['fixture']).read_bytes())
    (out / 'candidate-parameters.json').write_bytes(Path(selected['parameters']).read_bytes())
    report = {'schema': 'iris.pow2_scalar_cache_two_fixed_modes_TRAIN_selection.v1',
        'pass': True, 'selected_experimental_candidate': selected['mode'],
        'candidates': candidates, 'selection_rule': plan['selection_score'],
        'new_native': 'build/scalar-L2hit-outer-frozen-2b8b7cbf',
        'candidate_fixture_sha256': sha(out / 'candidate.fixture'),
        'candidate_parameters_sha256': sha(out / 'candidate-parameters.json'),
        'preserved_old_vector_Icache_outer_II_store_atomic_service_formulas': True,
        'source_policy_limit': 'Random only for Shuttle0/1DCache accepted-new-allocation proxy. '
            'RocketDCache/L2/Icache replacement remain LRU approximations; source S1/MSHRfire/merges unqualified.',
        'reserved_hardware_labels_consumed': False,
        'current_provider_or_selection_modified': False,
        'remaining_gates': ['Root-only reserved54 timing validation',
                            'Selected-cost all5OS on exact new native/mode',
                            'Root packaging/provenance and promotion review'],
        'full_two_percent_or_source_image_certification': False,
        'input_sha256': {str(p): sha(p) for p in inputs}}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'selected': selected['mode'],
                      'report_sha256': sha(out / 'report.json'),
                      'fixture_sha256': report['candidate_fixture_sha256']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--LRU-report', dest='LRU_report', type=Path, required=True)
    p.add_argument('--random-report', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args())
