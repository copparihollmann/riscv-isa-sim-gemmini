#!/usr/bin/env python3
"""Compare one frozen fitted candidate against only the permitted180 TRAIN labels."""
import argparse
import json
import statistics
from pathlib import Path
import fit_pow2_scalar_cache_v1 as fit


def metrics(rows):
    errors = sorted(abs(r['signed_error_percent']) for r in rows)
    def percentile(q):
        p = (len(errors) - 1) * q
        lo = int(p)
        hi = min(lo + 1, len(errors) - 1)
        return errors[lo] + (p - lo) * (errors[hi] - errors[lo])
    return {'rows': len(rows), 'median_absolute_percent_error': statistics.median(errors),
            'p90_absolute_percent_error': percentile(.9), 'max_absolute_percent_error': max(errors),
            'within2percent_rows': sum(x <= 2 for x in errors),
            'relative_squared_loss_sum': sum((r['signed_error_percent'] / 100) ** 2 for r in rows),
            'instret_mismatches': sum(r['model_instret'] != r['hardware_instret'] for r in rows)}


def main(a):
    train, params_path, run, out = [p.resolve() for p in
                                  (a.train, a.parameters, a.run, a.output)]
    fit.need(not out.exists(), 'New output required')
    tr, params, receipt = [fit.load(p) for p in
                          (train / 'report.json', params_path, run / 'run.json')]
    fit.need(tr['reserved_timing_labels_excluded'] is True and
             fit.sha(train / 'regions.jsonl') == fit.TRAIN_ROWS and tr['regions'] == 180,
             'Exact permitted TRAIN reference required')
    fit.need(params['schema'] == 'iris.pow2_scalar_cache_two_predeclared_modes_TRAIN_NNLS.v2'
             and params['reserved_labels_consumed'] is False,
             'Frozen finite-mode TRAIN parameters required')
    packet = fit.load(params_path.with_name('report.json'))
    fit.need(packet['parameters_sha256'] == fit.sha(params_path) and
             packet['fixture_sha256'] == receipt['fixture_sha256'], 'Actual selected fixture binding')
    for p, digest in params['input_sha256'].items():
        fit.need(fit.sha(p) == digest, 'Changed fit input: ' + p)
    corpus = fit.load(fit.ROOT / 'build/pow2-memory-single-v1/corpus.json')
    observations = fit.observations(run, corpus)
    labels = [json.loads(x) for x in (train / 'regions.jsonl').read_text().splitlines()]
    canonical = {(r['case_id'], r['hart']): r for r in fit.module().canonical()
                 if r['footprint_bytes'] not in fit.RESERVED}
    rows, seen = [], set()
    for r in labels:
        key = r['case_id'], r['hart']
        fit.need(key in canonical and key not in seen and r['internal_split'] == 'train'
                 and r['footprint_bytes'] not in fit.RESERVED, 'No reserved or duplicate labels')
        seen.add(key)
        fit.need(all(type(r.get(k)) is type(v) and r[k] == v
                     for k, v in canonical[key].items()), 'Exact canonical geometry/golden')
        observed = observations[key]
        fit.need(r['cycles'] > 0, 'Positive raw measured delta')
        row = {k: r[k] for k in ('case_id', 'hart', 'footprint_bytes', 'pass_index', 'trial_id')}
        row.update(model_cycles=observed['cycles'], hardware_cycles=r['cycles'],
                   model_instret=observed['row']['instret_delta'], hardware_instret=r['instret_delta'],
                   signed_error_percent=100 * (observed['cycles'] / r['cycles'] - 1),
                   actual_L2_hit_basis=observed['admitted_hits'],
                   actual_outer_basis=observed['admitted_outer'],
                   charged_alpha=observed['charged_alpha'], charged_beta=observed['charged_beta'])
        rows.append(row)
    fit.need(seen == set(canonical) and len(rows) == 180, 'All180 TRAIN rows without filtering')
    groups = {}
    for axis in ('hart', 'footprint_bytes', 'pass_index'):
        groups[axis] = {str(v): metrics([r for r in rows if r[axis] == v])
                        for v in sorted({r[axis] for r in rows})}
    out.mkdir(parents=True)
    observations_path = out / 'TRAIN-observations.jsonl'
    observations_path.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    paths = [Path(__file__).resolve(), Path(fit.__file__).resolve(), train / 'report.json',
             train / 'regions.jsonl', params_path, params_path.with_name('report.json')]
    paths += [run / x for x in ('run.json', 'stdout', 'features.jsonl')]
    result = {'schema': 'iris.pow2_scalar_cache_actual_TRAIN_comparison.v1',
        'pass': True, 'mode': params['mode'], 'actual_guest_exit_and_all234_numeric_verified': True,
        'TRAIN_only_metrics': metrics(rows), 'TRAIN_only_groups': groups,
        'no_reserved_timing_labels_consumed': True, 'rows_filtered': False,
        'qualification_scope': 'Development TRAIN only; not reserved validation or full physical certification',
        'no_fit_or_parameter_changes': True, 'observations_sha256': fit.sha(observations_path),
        'input_sha256': {str(p): fit.sha(p) for p in paths}}
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'pass': True, 'mode': params['mode'], 'metrics': metrics(rows),
                      'report_sha256': fit.sha(out / 'report.json')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    for key in ('train', 'parameters', 'run', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    main(p.parse_args())
