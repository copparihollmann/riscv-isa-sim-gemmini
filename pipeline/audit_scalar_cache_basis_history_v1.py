#!/usr/bin/env python3
"""Read-only TRAIN-only attribution of the rejected paired cache basis."""
import argparse
import json
from pathlib import Path
import fit_pow2_scalar_cache_v1 as fit


def prefix(run):
    values = {}
    for line in (run / 'features.jsonl').read_text().splitlines():
        p = json.loads(line)
        if p['csr'] == 0xb00:
            values[p['hart'], p['sequence']] = p
    return values


def main(a):
    base, new, train, out = [p.resolve() for p in
                            (a.baseline, a.admitted, a.train, a.output)]
    fit.need(not out.exists(), 'New output directory required')
    report = fit.load(train / 'report.json')
    fit.need(report['reserved_timing_labels_excluded'] is True and
             fit.sha(train / 'regions.jsonl') == fit.TRAIN_ROWS,
             'Exact permitted TRAIN-only reference required')
    refs = [json.loads(x) for x in (train / 'regions.jsonl').read_text().splitlines()]
    fit.need(len(refs) == 180 and all(r['internal_split'] == 'train' and
             r['footprint_bytes'] not in fit.RESERVED for r in refs),
             'All and only 180 TRAIN rows')
    corpus = fit.load(fit.ROOT / 'build/pow2-memory-single-v1/corpus.json')
    old, current = fit.observations(base, corpus), fit.observations(new, corpus)
    bp, np = prefix(base), prefix(new)
    rows, mismatches, other_memory = [], [], []
    for r in refs:
        key = r['case_id'], r['hart']
        b, n = old[key], current[key]
        h = r['hart']
        blo, bhi = [bp[h, s] for s in b['CSR_sequences']]
        nlo, nhi = [np[h, s] for s in n['CSR_sequences']]
        def features(lo, hi):
            return {k: hi['features'].get(k, {}).get('instructions', 0) -
                    lo['features'].get(k, {}).get('instructions', 0)
                    for k in set(lo['features']) | set(hi['features'])}
        bf, nf = features(blo, bhi), features(nlo, nhi)
        fit.need(n['D_L2hit_algebra'] == n['admitted_hits'] and
                 n['D_outer'] == n['admitted_outer'],
                 'Current own-cache algebra must equal admitted ordinary loads')
        nonloads = {name: {k: v for k, v in f.items() if v and
                    k.startswith('memory.') and k != 'memory.DRAM.load'}
                    for name, f in (('old', bf), ('new', nf))}
        if any(nonloads.values()):
            other_memory.append({'case_id': r['case_id'], 'hart': h,
                                 'instructions': nonloads})
        changed = (b['D_L2hit_algebra'], b['D_outer']) != (
                    n['admitted_hits'], n['admitted_outer'])
        item = {k: r[k] for k in ('case_id', 'hart', 'footprint_bytes',
                                 'pass_index', 'trial_id')}
        item.update(old_L2_hits=b['D_L2hit_algebra'], old_outer=b['D_outer'],
                    new_L2_hits=n['admitted_hits'], new_outer=n['admitted_outer'],
                    new_own_cache_L2_hits=n['D_L2hit_algebra'],
                    new_own_cache_outer=n['D_outer'],
                    old_ROI_retired_features=bf, new_ROI_retired_features=nf,
                    other_memory=nonloads,
                    old_ROI_cache={k: bhi['memory']['DRAM'].get(k, 0) -
                        blo['memory']['DRAM'].get(k, 0) for k in bhi['memory']['DRAM']},
                    new_ROI_cache={k: nhi['memory']['DRAM'].get(k, 0) -
                        nlo['memory']['DRAM'].get(k, 0) for k in nhi['memory']['DRAM']},
                    changed=changed)
        if changed:
            item['pre_ROI_history'] = {
                'old_global_read_cycle': blo['read_cycle'],
                'new_global_read_cycle': nlo['read_cycle'],
                'old_retired': blo['retired'], 'new_retired': nlo['retired'],
                'old_DRAM': blo['memory']['DRAM'],
                'new_DRAM': nlo['memory']['DRAM'],
                'old_memory_instruction_prefix': {k: v['instructions'] for k, v
                    in blo['features'].items() if k.startswith('memory.')},
                'new_memory_instruction_prefix': {k: v['instructions'] for k, v
                    in nlo['features'].items() if k.startswith('memory.')},
            }
            mismatches.append(item)
        rows.append(item)
    out.mkdir(parents=True)
    (out / 'TRAIN-observations.jsonl').write_text(''.join(
        json.dumps(r, sort_keys=True) + '\n' for r in rows))
    inputs = [Path(__file__).resolve(), Path(fit.__file__).resolve(),
              train / 'report.json', train / 'regions.jsonl',
              fit.ROOT / 'benchmarks/pow2_memory_v1/guest.c']
    for run in (base, new):
        inputs += [run / p for p in ('run.json', 'stdout', 'features.jsonl')]
    result = {
        'schema': 'iris.scalar_cache_basis_history_TRAIN_audit.v1',
        'pass': True, 'TRAIN_rows': len(rows),
        'old_vs_alphaON_basis_mismatches': len(mismatches),
        'new_own_cache_vs_admitted_mismatches': 0,
        'ROIs_with_other_memory_instructions': len(other_memory),
        'other_memory_feature_values': sorted({(name, k, v) for x in other_memory
            for name, features in x['instructions'].items() for k, v in features.items()}),
        'first_mismatch': mismatches[0] if mismatches else None,
        'finding': 'The rejected cross-run basis differs because modeled cache '
            'classification/history changed; within every alpha-ON TRAIN ROI '
            'the new admitted ordinary-load basis equals that same run\'s D '
            'cache algebra. Compiler-generated DRAM stores occur inside '
            'the CSR windows, but contribute no L2-hit/outer-miss basis in '
            'the alpha-ON run. Pre-ROI polling, atomics, stores and cache prefixes '
            'already differ. Prefixes alone do not identify the particular '
            'request/eviction causing the first extra miss.',
        'fit_refusal_preserved': True, 'rows_filtered': False,
        'reserved_timing_labels_consumed': False, 'model_modified': False,
        'input_sha256': {str(p): fit.sha(p) for p in inputs},
        'observations_sha256': fit.sha(out / 'TRAIN-observations.jsonl'),
    }
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('pass', 'TRAIN_rows',
        'old_vs_alphaON_basis_mismatches', 'new_own_cache_vs_admitted_mismatches')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    for key in ('baseline', 'admitted', 'train', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    main(p.parse_args())
