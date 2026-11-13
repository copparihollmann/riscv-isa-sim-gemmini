#!/usr/bin/env python3
"""Freeze the selected OWN-525 candidate with complete numerical definitions."""
import collections
import hashlib
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def objective(path):
    rows = [json.loads(s) for s in path.read_text().splitlines()]
    groups = collections.defaultdict(list)
    for row in rows:
        if row['partition'] == 'train':
            groups[(row['parent_case_id'], row['hart'])].append(row['signed_error_pct'] / 100)
    return statistics.mean(statistics.median(v) ** 2 for v in groups.values())


def main():
    out = ROOT / 'calibration/compute-fit-525-selected-v1'
    out.mkdir(exist_ok=False)
    options = {
        'outer': ROOT / 'calibration/compute-fit-525-outer-prior-evaluation-v1',
        'intent18': ROOT / 'calibration/compute-fit-525-intent18-evaluation-v1',
        'lf4': ROOT / 'calibration/compute-fit-525-control-lf4-evaluation-v1',
        'read55': ROOT / 'calibration/compute-fit-525-control-read55-evaluation-v1'}
    scored = {name: objective(path / 'signed-regions.jsonl') for name, path in options.items()}
    chosen = min(scored, key=lambda name: (scored[name], name))
    if chosen != 'intent18':
        raise ValueError('Own-epoch selection differs; do not freeze stale intent')
    base = ROOT / 'calibration/compute-fit-525-intent18-v1/runtime.fixture'
    raw_path = ROOT / 'calibration/compute-fit-525-constrained-v1/parameters.json'
    raw = json.loads(raw_path.read_text())
    prior_path = ROOT / 'calibration/empirical-priority-28a0-runtime-v2/parameters.json'
    model = ROOT / 'build/empirical-vme-work-frozen-525cc4af'
    identity = 'iris-empirical-compute-525-v1'
    parameters = {'schema': 'iris.empirical_compute_parameters.v1', 'calibration_identity': identity,
                  'actual_parameter_fit_performed': True, 'actual_calibrated_native_replay_completed': False,
                  'native_binary_sha256': sha(model / 'spike'), 'uart_library_sha256': sha(model / 'libsifive_uart.so'),
                  'base_hz': 500000000, 'rtc_divider': 1000, 'counter_policy': 'source-ungated-stall',
                  'vme_work': 'source-shape-subtiles-v1', 'raw_parameters_sha256': sha(raw_path),
                  'own_epoch_training_selection': {'objective': 'Mean squared relative error of TRAIN parent/hart trial medians; all families included for transport tuning.',
                                                  'candidate_objectives': scored, 'chosen': chosen,
                                                  'internal_validation_used_for_selection': False},
                  'cache': {}, 'instruction': {}, 'branch': {}, 'families': [],
                  'cost_semantics': {'read_base': 'Charged by native conservative scalar DRAM reads and coherence fallbacks; integer private L1-hit load front bypasses it. Scalar FP load fallback also charges it. Not a physical L1 latency.',
                                     'l1_miss': 'Additional effective DATA-L1 miss response service; private hits unchanged. Accepted same-line actors keep their existing dependency order; no source NoC/probe queue equivalence claim.',
                                     'outer': 'Separately bound prior28 effective outer-return and shared launch services, not newly identified on this small source525 compute corpus.',
                                     'async': 'Positive integer backend extras over current source/scoped-work baseline; nonlinear actual counter replay required.',
                                     'vector_memory': 'Additional generic unitstride ATL load/store services; direct-L2 vector path retains zero L1D allocation and preserves outer transport reservation.'},
                  'prior_memory_parameters': {'path': str(prior_path), 'sha256': sha(prior_path),
                                              'runtime_binding': str(ROOT / 'calibration/empirical-priority-28a0-binding-v2/runtime-binding.json'),
                                              'runtime_binding_sha256': sha(ROOT / 'calibration/empirical-priority-28a0-binding-v2/runtime-binding.json'),
                                              'qualified_for_525': False},
                  'unqualified': ['ScalarFP and warm scalar-store/atomic intrinsic pipeline floors remain.',
                                  'Memory hierarchy uses approximate LRU/intent-time coherence bookkeeping, not full physical bank/NoC queues.',
                                  'Shared outer545.732/461 and noncompute TCM/scratch paths are prior transfers; new-epoch heavy memory coverage remains incomplete.',
                                  'Conservative scalar read service includes hot scalarFP-load fallback; no isolated physical NoC/read latency certification.',
                                  'FADD/OPU baseline work and added costs are empirical; static native unfitted-work-duration describes the physical baseline, not absence of fixture-bound corrections.',
                                  'No BF16/FP8 vector-FADD timing fit: no training instruction coverage.',
                                  'Observed shape/work domains only; no arbitrary-shape, Zephyr end-to-end, source/image or full2% certification.',
                                  'Known actual FPGA vector-transport hangs and unsupported VME column behavior are not emulated.'],
                  'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
                  'full_model_certified': False, 'source_image_association_verified': False}
    lines = base.read_text().splitlines()
    for line in lines:
        f = line.split()
        if not f:
            continue
        if f[0] == 'empirical_cache_service':
            parameters['cache'][f[1]] = dict(zip(('read_base', 'write_base', 'l1_miss', 'outer_miss', 'outer_interval', 'dirty_extra'), map(float, f[2:8])))
        elif f[0] == 'empirical_instruction_service':
            parameters['instruction'][f[1]] = dict(zip(('l1_miss', 'outer_miss', 'outer_interval'), map(float, f[2:5])))
        elif f[0] == 'empirical_branch_service':
            parameters['branch'][f[1]] = float(f[2])
        elif f[0] == 'empirical_family':
            parameters['families'].append({'hart': int(f[1]), 'family': f[2], 'resource': f[3],
                                           'setup': float(f[4]), 'work': float(f[5]), 'interval': int(f[6]),
                                           'scope': 'Prior28path service, unqualified525transfer' if f[2].startswith(('memory.LOCAL_TCM.', 'memory.REMOTE_TCM.', 'memory.SCRATCHPAD.')) else 'Own525 actual compute training/live counter fit; effective model cost, not physical unit latency.'})
    (out / 'parameters.json').write_text(json.dumps(parameters, indent=2, sort_keys=True) + '\n')
    digest = sha(out / 'parameters.json')
    rendered = []
    for line in lines:
        f = line.split()
        if f and f[0] == 'empirical_profile':
            f[2] = identity
        if f and f[0] in ('empirical_cache_service', 'empirical_instruction_service', 'empirical_branch_service', 'empirical_family'):
            f[-3] = 'EFFECTIVE_OWN525_COMPUTE_TRAIN_OR_DECLARED_PRIOR'
            f[-2] = digest
        rendered.append(' '.join(f) if f else '')
    (out / 'runtime.fixture').write_text('\n'.join(rendered) + '\n')
    sensitivity = list(rendered)
    for i, line in enumerate(sensitivity):
        f = line.split()
        if f and f[0] == 'empirical_family' and f[2] == 'rvv.integer':
            f[4] = str(float(f[4]) + 20)
            sensitivity[i] = ' '.join(f)
    sensitivity += ['resource fit.sensitivity.integer2 1', f'empirical_family 2 rvv.integer fit.sensitivity.integer2 20 0 1 SELFTEST_ONLY {digest} core_cycles']
    (out / 'sensitivity.fixture').write_text('\n'.join(sensitivity) + '\n')
    inputs = [pathlib.Path(__file__).resolve(), base, raw_path, prior_path, ROOT / 'build/compute-fit-v3/split.json']
    inputs += [p / name for p in options.values() for name in ('report.json', 'signed-regions.jsonl')]
    selection = {'schema': 'iris.empirical_compute_own_epoch_selection.v1', 'status': 'selected_final_identity_replay_pending',
                 'native_binary_sha256': parameters['native_binary_sha256'], 'uart_library_sha256': parameters['uart_library_sha256'],
                 'parameters_sha256': digest, 'fixture_sha256': sha(out / 'runtime.fixture'),
                 'own_training_objectives': scored, 'chosen': chosen, 'actual_parameter_fit_performed': True,
                 'actual_final_identity_replay_completed': False, 'old_native_qualification_transferred': False,
                 'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
                 'input_sha256': {str(p): sha(p) for p in inputs}}
    (out / 'selection-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
    (out / 'selection.json').write_text(json.dumps(selection, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'fixture': str(out / 'runtime.fixture'), 'fixture_sha256': selection['fixture_sha256'], 'parameters_sha256': digest, 'own_training_objectives': scored}))


if __name__ == '__main__':
    main()
