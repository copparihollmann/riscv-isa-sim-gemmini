#!/usr/bin/env python3
"""Compare only the declared CPU-layout-v2 development corpus; never fit parameters."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(rows):
    errors = [row['signed_error_percent'] for row in rows]
    absolute = sorted(abs(error) for error in errors)
    return dict(rows=len(rows), median_signed_error_percent=statistics.median(errors),
                median_absolute_error_percent=statistics.median(absolute),
                p90_absolute_error_percent=absolute[int(.9 * (len(absolute) - 1))],
                within2pct_fraction=sum(error <= 2 for error in absolute) / len(absolute))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--readback', type=Path, required=True)
    parser.add_argument('--capsule', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reference = ROOT / 'build/fpga-cpu-layout-v2-001-analysis/regions.csv'
    source = args.readback / 'main-regions.jsonl'
    validation = args.readback / 'validation.json'
    proof = json.loads(validation.read_text())
    if proof['pass'] is not True or proof['main_regions'] != 2304:
        raise ValueError('Qualified complete unchanged-ELF CPU-layout readback required')
    ref = {(row['case_id'], int(row['hart'])): row for row in csv.DictReader(reference.open())}
    rows = []
    for line in source.read_text().splitlines():
        row = json.loads(line)
        if not row['case_id'].startswith('cpu.layout.v2.') or row['mode'] not in ('compact', 'wide'):
            raise ValueError('Only CPU-layout-v2 main development rows are admitted')
        expected = ref[(row['case_id'], row['hart'])]
        observed_cycles = row['end_cycle'] - row['start_cycle']
        expected_cycles = int(expected['cycles'])
        if row['pass'] is not True or observed_cycles <= 0 or expected_cycles <= 0:
            raise ValueError('Actual qualified positive region required')
        row.update(native_cycles=observed_cycles, reference_cycles=expected_cycles,
                   signed_error_percent=100 * (observed_cycles - expected_cycles) / expected_cycles,
                   reference_parent_case_id=expected['parent_case_id'])
        rows.append(row)
    if len(rows) != 2304 or len({(r['case_id'], r['hart']) for r in rows}) != 2304:
        raise ValueError('Missing or duplicate exact main records')
    table = out / 'regions.jsonl'
    table.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows))
    groups = {}
    for hart in range(3):
        for mode in ('compact', 'wide'):
            chosen = [r for r in rows if r['hart'] == hart and r['mode'] == mode]
            groups[f'{hart}:{mode}'] = dict(
                all=metrics(chosen),
                warm_N_ge64=metrics([r for r in chosen if r['repeat'] > 0 and r['n'] >= 64]))
    inputs = [Path(__file__).resolve(), source, validation, reference,
              args.capsule / 'manifest.json', args.capsule / 'verification.json', table]
    report = dict(schema='iris.fast_source_frontend.CPU_development_comparison.v2',
                  main_regions=2304, actual_CSR_ELF_joins=4608,
                  functional_checks_passed=True, normal_guest_exit_verified=False,
                  intentional_post_ROI_debugger_stop=True, noop_controls_qualified=False,
                  metrics=metrics(rows), groups=groups,
                  parameters_fitted=False, global_heldout_timings_consumed=False,
                  scope='Declared CPU-layout-v2 development data only; warm subsets explicit; not independent whole-workload qualification.',
                  timing_2pct_certified=False,
                  input_sha256={str(path.resolve()): sha(path) for path in inputs})
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(report_sha256=sha(out / 'report.json'), metrics=report['metrics'], groups=groups)))


if __name__ == '__main__':
    main()
