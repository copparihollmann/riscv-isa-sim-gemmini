#!/usr/bin/env python3
"""Select a positive runtime candidate from the fresh compute training split."""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    out = ROOT / 'calibration/compute-fit-523-candidate-v1'
    out.mkdir(exist_ok=False)
    raw_path = ROOT / 'calibration/compute-fit-523-constrained-v1/parameters.json'
    raw = json.loads(raw_path.read_text())
    base_path = ROOT / 'calibration/compute-fit-523-outer-prior-v1/base.fixture'
    rows_path = ROOT / 'build/compute-fit-features-523-outer-prior-v1/regions.jsonl'
    rows = [json.loads(s) for s in rows_path.read_text().splitlines()]
    native = ROOT / 'build/empirical-rocket-RAS-frozen-52314001/spike'
    uart = native.with_name('libsifive_uart.so')
    identity = 'iris-empirical-compute-523-v1'
    parameters = {'schema': 'iris.empirical_compute_selected_parameters.v1',
                  'actual_parameter_fit_performed': True, 'actual_calibrated_native_replay_completed': False,
                  'calibration_identity': identity, 'native_binary_sha256': sha(native), 'uart_library_sha256': sha(uart),
                  'base_hz': 500000000, 'rtc_divider': 1000, 'counter_policy': 'source-ungated-stall',
                  'raw_parameters_sha256': sha(raw_path), 'base_fixture_sha256': sha(base_path),
                  'base_scope': 'Shared outer545.732/461 and noncompute paths are separately bound prior28 values, not qualified as source523 physical memory parameters.',
                  'generic_scalar_DRAM_extra_costs_fitted': False, 'families': [], 'branch': {}, 'instruction_l1_extra': {},
                  'unqualified': ['ScalarFP structural floor and source memory store pipeline remain unresolved.',
                                  'Shared outer service and noncompute paths are prior transfers, not identified by this compute-only reference.',
                                  'No BF16/FP8 vector-FADD coefficient: absent training instruction coverage.',
                                  'Atomic/polling-pipeline timing excluded from coefficient selection; all errors still reported.',
                                  'Setup/work equivalence and async overlap require actual counter replays; this selection is not live accuracy evidence.'],
                  'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
                  'source_image_association_verified': False}
    for h in range(3):
        cls = 'shuttle' if h < 2 else 'rocket'
        model = raw['models'][cls]
        coeff = model['coefficients']
        parameters['branch'][str(h)] = int(round(coeff.get('branch.mispredicts', 0.)))
        parameters['instruction_l1_extra'][str(h)] = int(round(coeff.get('icache.DRAM.l1misses', 0.)))
        training = [r for r in rows if r['partition'] == 'train' and r['parent_case_id'] in model['training_parent_ids'] and ('shuttle' if r['hart'] < 2 else 'rocket') == cls]
        families = sorted({f for r in training for f, v in r['features'].items() if v['instructions'] and f.startswith(('rvv.', 'vme.', 'memory.vector.'))})
        for family in families:
            a, b = coeff.get(family + '.instructions', 0.), coeff.get(family + '.work', 0.)
            if not (a or b):
                continue
            domain = sorted({r['features'][family]['work'] / r['features'][family]['instructions'] for r in training if r['features'].get(family, {}).get('instructions', 0)})
            if family.startswith('memory.'):
                setup, work = a, b
                resource = 'fit.compute.vector-memory' + str(h)
                scope = 'Additional vector-store service; native fractional accumulation, preserves actual outer transport reservation.'
            else:
                points = [r for r in training if r['features'].get(family, {}).get('instructions', 0)]
                scored = []
                for ai in range(9):
                    for bi in range(3):
                        loss = sum(((ai * r['features'][family]['instructions'] + bi * r['features'][family]['work'] -
                                     a * r['features'][family]['instructions'] - b * r['features'][family]['work']) / max(1, r['reference_cycles'])) ** 2 for r in points)
                        scored.append((loss, ai + bi, ai, bi))
                _, _, setup, work = min(scored)
                if not (setup or work):
                    continue
                resource = ('fit.compute.sharedFPU2' if h == 2 else 'fit.compute.vectorFP' + str(h)) if family.startswith('rvv.fadd.') else ('fit.compute.vme' + str(h) if family.startswith('vme.') else 'fit.compute.vector' + str(h))
                scope = 'Positive integer async extra duration over this source523 baseline; observed-work domain only.'
            parameters['families'].append({'hart': h, 'family': family, 'setup': setup, 'work': work, 'interval': 1,
                                           'resource': resource, 'raw_setup_work': [a, b],
                                           'training_work_per_instruction': domain, 'scope': scope})
    (out / 'parameters.json').write_text(json.dumps(parameters, indent=2, sort_keys=True) + '\n')
    digest = sha(out / 'parameters.json')
    lines = [line.replace('compute-v1-523-outer-prior-v1', identity) for line in base_path.read_text().splitlines() if not line.startswith('empirical_instruction_service ')]
    lines += ['resource ' + name + ' 1' for name in sorted({f['resource'] for f in parameters['families']})]
    for h in range(3):
        # Outer prior retained exactly; no duplicated cache service layers.
        lines.append(f'empirical_instruction_service {h} {parameters["instruction_l1_extra"][str(h)]} 545.732041126 461 NEW_COMPUTE_TRAIN_FIT {digest} core_cycles')
        lines.append(f'empirical_branch_service {h} {parameters["branch"][str(h)]} NEW_COMPUTE_TRAIN_FIT {digest} core_cycles')
    for f in parameters['families']:
        lines.append('empirical_family ' + str(f['hart']) + ' ' + f['family'] + ' ' + f['resource'] + ' ' +
                     ' '.join(format(f[k], '.12g') for k in ('setup', 'work', 'interval')) + ' NEW_COMPUTE_TRAIN_FIT ' + digest + ' core_cycles')
    (out / 'runtime.fixture').write_text('\n'.join(lines) + '\n')
    (out / 'selection-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
    (out / 'selection.json').write_text(json.dumps({'schema': 'iris.empirical_compute_selection.v1', 'status': 'selected_actual_replay_pending',
        'parameters_sha256': digest, 'fixture_sha256': sha(out / 'runtime.fixture'), 'actual_native_quality_claimed': False,
        'input_sha256': {str(p): sha(p) for p in (pathlib.Path(__file__).resolve(), raw_path, base_path, rows_path,
                         ROOT / 'build/compute-fit-v3/split.json')}, 'global_heldout_timings_consumed': False, 'full_2pct_certified': False}, indent=2) + '\n')
    print(json.dumps({'fixture': str(out / 'runtime.fixture'), 'sha256': sha(out / 'runtime.fixture'), 'family_rules': len(parameters['families'])}))


if __name__ == '__main__':
    main()
