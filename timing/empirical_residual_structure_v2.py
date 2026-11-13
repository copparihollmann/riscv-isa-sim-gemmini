#!/usr/bin/env python3
"""Read-only structural residual audit; no parameter selection or native edits."""
import collections
import hashlib
import json
import pathlib
import statistics

from empirical_priority_runtime_report import metrics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    out = ROOT / 'build/empirical-priority-28a0-structure-v2'
    out.mkdir(exist_ok=False)
    signed_path = ROOT / 'calibration/empirical-priority-28a0-actual-v2/signed-regions.jsonl'
    features_path = ROOT / 'build/empirical-priority-28a0-calibrated-features-v2/regions.jsonl'
    report_path = ROOT / 'calibration/empirical-priority-28a0-actual-v2/report.json'
    source_core = ROOT / 'third_party/shuttle/src/main/scala/exu/Core.scala'
    source_cache = ROOT / 'third_party/shuttle/src/main/scala/dmem/DCache.scala'
    source_kernel = ROOT / 'build/campaign-buffered-priority-v2-final/distribution.c'
    rows = [json.loads(s) for s in signed_path.read_text().splitlines()]
    features = {(r['case_id'], r['hart']): r for r in (json.loads(s) for s in features_path.read_text().splitlines())}
    if len(rows) != 3633 or len(features) != 3633:
        raise ValueError('Expected the exact qualified prefix')
    structure = collections.defaultdict(list)
    warm_store = collections.defaultdict(list)
    snapshots = []
    mismatches = collections.defaultdict(list)
    for row in rows:
        f = features[(row['case_id'], row['hart'])]
        m = f['case_metadata_for_reporting_only']
        if row['native_instret_delta'] != row['reference_instret_delta']:
            mismatches[row['family']].append({'case_id': row['case_id'], 'hart': row['hart'],
                                             'native': row['native_instret_delta'], 'reference': row['reference_instret_delta']})
        target = m.get('target_region')
        if not target:
            continue
        kind, mask = m['kind'], m['mask']
        domain = 'LOCAL_TCM' if target == 'tcm' + str(row['hart']) else 'REMOTE_TCM' if target.startswith('tcm') else target
        sequences = m.get('bank_bit6_sequence_by_hart', [])
        seq = sequences[row['hart']] if len(sequences) > row['hart'] else []
        bank_pattern = ('bank' + str(seq[0])) if seq and len(set(seq)) == 1 else 'alternating' if len(seq) > 1 and all(a != b for a, b in zip(seq, seq[1:])) else 'unclassified'
        cls = 'shuttle' if row['hart'] < 2 else 'rocket'
        key = (domain, kind, cls, bin(mask).count('1'), bank_pattern, m.get('n'))
        structure[key].append(row)
        dram = f.get('memory', {}).get('DRAM', {})
        if (domain == 'dram' and kind == 'write' and dram.get('writes', 0) >= 1024
                and dram.get('l2misses', 0) == 0 and dram.get('dirty_owner_forwards', 0) == 0
                and dram.get('coherence_invalidations', 0) == 0
                and dram.get('l1hits', 0) / max(1, dram.get('accesses', 0)) >= .99):
            warm_store[cls].append(row)
            snapshots.append({**row, 'actual_runtime_memory_delta': dram})
    if any(f not in ('pipeline', 'pipeline_vme') for f in mismatches):
        raise ValueError('Nonpolling instruction count changed')
    source = source_kernel.read_text().splitlines()
    polls = [{'line': i + 1, 'text': line.strip()} for i, line in enumerate(source) if 'while(__atomic_load_n(&pipeline_stage' in line]
    if len(polls) != 1:
        raise ValueError('Compiled source polling-loop evidence changed')
    table = [dict(domain=k[0], kind=k[1], hart_class=k[2], active_harts=k[3], bank_pattern=k[4], n=k[5],
                  reference_cycles_median=statistics.median(r['reference_cycles'] for r in v),
                  native_cycles_median=statistics.median(r['calibrated_native_cycles'] for r in v), **metrics(v))
             for k, v in sorted(structure.items())]
    (out / 'bank-mask-residuals.json').write_text(json.dumps(table, indent=2, sort_keys=True) + '\n')
    (out / 'warm-store-witnesses.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in snapshots))
    result = {
        'schema': 'iris.empirical_runtime_structural_residual_audit.v1', 'status': 'passed_read_only_audit',
        'regions': len(rows), 'all_numeric_goldens_passed_in_parent_receipt': True,
        'nonpolling_instret_matches_reference': len(rows) - sum(map(len, mismatches.values())),
        'polling_instret_mismatch_groups': dict(mismatches), 'compiled_source_polling_loop': polls,
        'warm_dram_store_floor': {cls: {**metrics(v), 'reference_cycles_median': statistics.median(r['reference_cycles'] for r in v),
                                       'native_cycles_median': statistics.median(r['calibrated_native_cycles'] for r in v)} for cls, v in warm_store.items()},
        'priority': 'Owned warm-L1 scalar-storefront before new bank queues: existing core pipeline drains on every store despite private L1 hits. Positive latency/interval parameters cannot reduce this floor.',
        'proposed_guard': 'Aligned integer SB/SH/SW/SD; M-mode, no translation/MPRV, known address/data, existing dirty private DRAM line, no overlapping pending owner. Recheck at actual source COM/write edge; publish once, with original knownness and precise faults. Lost ownership must nack/replay to conservative path.',
        'source_citations': [
            {'file': str(source_core), 'lines': [596, 604, 622, 779, 914, 917, 1106], 'claim': 'CPU request at EX, store data at MEM, S1/S2 kills and COM cache-nack replay.'},
            {'file': str(source_cache), 'lines': [250, 251, 291, 329, 479, 480, 483], 'claim': 'S2 permission-stable hit; write requires valid&&!nack&&!kill, not merely an L1 timing tag.'}],
        'banking_scope': 'Bank patterns/masks/targets are reporting only. A bankless interval1 queue is a known approximation; adding two banks cannot cure an already-overpredicted isolated warm private DRAM store stream. Residual bank/NoC ingress differences remain unresolved.',
        'no_native_edits': True, 'no_parameter_refit': True, 'global_heldout_timings_consumed': False,
        'hardware_contacted': False, 'full_2pct_certified': False,
        'input_sha256': {str(p): sha(p) for p in (pathlib.Path(__file__).resolve(), ROOT / 'timing/empirical_priority_runtime_report.py', signed_path, features_path, report_path, source_core, source_cache, source_kernel)},
        'output_sha256': {str(out / name): sha(out / name) for name in ('bank-mask-residuals.json', 'warm-store-witnesses.jsonl')},
    }
    (out / 'audit-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
    (out / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'report': str(out / 'report.json'), 'warm_store_floor': result['warm_dram_store_floor'], 'nonpolling_instret_matches': result['nonpolling_instret_matches_reference']}, indent=2))


if __name__ == '__main__':
    main()
