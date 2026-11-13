#!/usr/bin/env python3
"""Two predeclared cache modes; fit each from its own complete zero-cost run."""
import argparse
import json
import math
from pathlib import Path
import fit_pow2_scalar_cache_v1 as old

NATIVE = '2b8b7cbff543ddb9cd0916b8723baf6f65b3cf3754efcc238612ba230e754f7c'
POLICY = 'shuttle-miss-allocation-proxy-v1'


def zero_fixture(text, mode):
    lines = [x.split() for x in text.splitlines()
             if x.strip() and not x.lstrip().startswith('#')]
    profile = [x for x in lines if x[0] == 'empirical_profile']
    old.need(len(profile) == 1 and len(profile[0]) == 4,
             'One explicit empirical profile required')
    selectors = [x for x in lines if x[0] == 'empirical_dcache_random']
    old.need(selectors == ([] if mode == 'LRU' else
                          [['empirical_dcache_random', POLICY]]),
             'Declared mode must equal exact runtime policy selector')
    for key in ('empirical_scalar_l2_hit', 'empirical_scalar_outer_response'):
        rules = [x for x in lines if x[0] == key]
        old.need(len(rules) == 3 and {x[1] for x in rules} == {'0', '1', '2'}
                 and all(len(x) == 6 and float(x[2]) == 0 and
                         x[-1] == 'core_cycles' for x in rules),
                 'Exactly three explicit zero-coefficient basis rules required')
    return lines


def main(a):
    train, run, out = [p.resolve() for p in (a.train, a.zero, a.output)]
    old.need(not out.exists(), 'New output directory required')
    receipt = old.load(run / 'run.json')
    old.need(receipt['capsule_native'] == NATIVE, 'Exact frozen2b8 native required')
    fixtures = [Path(x.split('=', 1)[1]) for x in receipt['argv']
                if x.startswith('--iris-timing-fixture=')]
    old.need(len(fixtures) == 1, 'One actual runtime fixture required')
    fixture = fixtures[0]
    old.need(old.sha(fixture) == receipt['fixture_sha256'], 'Runtime fixture changed')
    source_text = fixture.read_text()
    lines = zero_fixture(source_text, a.mode)
    report = old.load(train / 'report.json')
    old.need(report['schema'] == 'iris.pow2_single_memory_TRAIN_only_export.v1'
             and report['status'] == 'passed' and
             report['reserved_timing_labels_excluded'] is True and
             report['regions'] == 180 and report['ELF_sha256'] == old.ELF and
             old.sha(train / 'regions.jsonl') == old.TRAIN_ROWS == report['regions_sha256'],
             'Exact permitted TRAIN-only reference required')
    reference = [json.loads(x) for x in (train / 'regions.jsonl').read_text().splitlines()]
    corpus_path = old.ROOT / 'build/pow2-memory-single-v1/corpus.json'
    corpus = old.load(corpus_path)
    old.module().validate_corpus(corpus)
    canonical = {(r['case_id'], r['hart']): r for r in old.module().canonical()
                 if r['footprint_bytes'] not in old.RESERVED}
    old.need(len(reference) == len(canonical) == 180, 'All180 TRAIN rows required')
    observations = old.observations(run, corpus)
    seen, joined = set(), []
    for r in reference:
        key = r['case_id'], r['hart']
        old.need(key in canonical and key not in seen and
                 r['internal_split'] == 'train' and r['footprint_bytes'] not in old.RESERVED,
                 'No reserved, duplicate or noncanonical reference')
        seen.add(key)
        old.need(all(type(r.get(k)) is type(v) and r[k] == v
                     for k, v in canonical[key].items()), 'Reference geometry/golden mismatch')
        b = observations[key]
        old.need(b['D_L2hit_algebra'] == b['admitted_hits'] and
                 b['D_outer'] == b['admitted_outer'],
                 'Same-mode baseline/admitted class mismatch; preserve all rows and refuse')
        old.need(b['charged_alpha'] == b['charged_beta'] == 0,
                 'Real zero-cost baseline required')
        old.need(type(r['cycles']) is int and r['cycles'] > 0, 'Positive measured delta')
        joined.append({k: r[k] for k in ('case_id', 'hart', 'semantic_parent_case_id',
            'footprint_bytes', 'pass_index', 'trial_id')})
        joined[-1].update(baseline_native_cycles=b['cycles'], hardware_cycles=r['cycles'],
            actual_admitted_L2_hit_lines=b['admitted_hits'],
            actual_admitted_outer_lines=b['admitted_outer'],
            baseline_instret=b['row']['instret_delta'], hardware_instret=r['instret_delta'])
    old.need(seen == set(canonical), 'All TRAIN groups/repeats retained')
    coefficients = []
    for h in range(3):
        samples = [(r['actual_admitted_L2_hit_lines'], r['actual_admitted_outer_lines'],
                    r['hardware_cycles'] - r['baseline_native_cycles'], r['hardware_cycles'])
                   for r in joined if r['hart'] == h]
        (alpha, beta), design = old.nnls(samples)
        old.need(all(math.isfinite(x) and 0 <= x < 1e11 for x in (alpha, beta)),
                 'Coefficient horizon')
        coefficients.append({'hart': h, 'alpha_core_cycles_per_modeled_L2_hit_line': alpha,
            'beta_core_cycles_per_modeled_outer_miss_line': beta,
            'TRAIN_rows': len(samples), 'design': design})
    paths = [Path(__file__).resolve(), Path(old.__file__).resolve(), fixture,
             train / 'report.json', train / 'regions.jsonl', corpus_path,
             old.ROOT / 'benchmarks/pow2_memory_v1/validate.py']
    paths += [run / p for p in ('run.json', 'stdout', 'features.jsonl')]
    params = {'schema': 'iris.pow2_scalar_cache_two_predeclared_modes_TRAIN_NNLS.v2',
        'pass': True, 'mode': a.mode, 'zero_baseline': str(run), 'coefficients': coefficients,
        'estimator': 'Fixed per-hart2-column nonnegative relative LS; all60TRAIN rows/hart; '
            'no intercept, no filtering. Target=HWminus actual same-mode zero native cycles. '
            'X=actual ordinary scalar load L2-hit/outer-miss probes with strict same-run class equality.',
        'finite_comparison_plan': 'Only LRU versus fixed-source ShuttleRandom; no seed/PRNG/policy tuning; '
            'mode selection uses sum of TRAIN relative-square loss only; actual replay required.',
        'TRAIN_relative_squared_loss_sum': sum(p['design']['relative_squared_loss_sum']
                                              for p in coefficients),
        'reserved_labels_consumed': False, 'physical_latencies_identified': False,
        'actual_nonlinear_replay_qualified': False,
        'input_sha256': {str(p): old.sha(p) for p in paths}}
    out.mkdir(parents=True)
    (out / 'parameters.json').write_text(json.dumps(params, indent=2) + '\n')
    pid = old.sha(out / 'parameters.json')
    identity = 'iris-pow2-' + a.mode + '-TRAIN-scalar-cache-v2'
    output_lines = []
    for x in lines:
        if x[0] in ('empirical_scalar_l2_hit', 'empirical_scalar_outer_response'):
            continue
        if x[0] == 'empirical_profile':
            x = x[:]
            x[2] = identity
        output_lines.append(' '.join(x))
    for p in coefficients:
        for name, key in (('empirical_scalar_l2_hit', 'alpha_core_cycles_per_modeled_L2_hit_line'),
                          ('empirical_scalar_outer_response', 'beta_core_cycles_per_modeled_outer_miss_line')):
            output_lines.append(f'{name} {p["hart"]} {p[key]:.17g} EFFECTIVE_POW2_TRAIN {pid} core_cycles')
    (out / 'runtime.fixture').write_text('\n'.join(output_lines) + '\n')
    (out / 'TRAIN-observations.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n'
                                                       for r in joined))
    result = {'pass': True, 'mode': a.mode, 'rows': 180,
        'parameters_sha256': pid, 'fixture_sha256': old.sha(out / 'runtime.fixture'),
        'reserved_labels_consumed': False, 'actual_runtime_accuracy_qualified': False,
        'TRAIN_relative_squared_loss_sum': params['TRAIN_relative_squared_loss_sum']}
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({**result, 'coefficients': coefficients}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--mode', choices=('LRU', 'source-ShuttleRandom'), required=True)
    for key in ('train', 'zero', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    main(p.parse_args())
