"""Root-only, no-refit validation of the predeclared 342 reserved regions."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'firesim'))
from analyze_rvv_compute1320 import analyze


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def readrows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def stats(values):
    absolute = sorted(abs(value) for value in values)
    return dict(count=len(values), median_signed_percent=statistics.median(values),
                median_absolute_percent=statistics.median(absolute),
                p90_absolute_percent=absolute[math.ceil(.9 * len(absolute)) - 1],
                maximum_absolute_percent=max(absolute), within2=sum(v <= 2 for v in absolute),
                quantile='nearest-rank-ceil')


def main(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    build, model, job = args.build.resolve(), args.model.resolve(), args.job.resolve()
    # Rederive all reference rows from the quiescent raw archive. A prior
    # report or a rewritten derived JSONL cannot certify the reference.
    verified = out / 'hardware-revalidation'
    need(analyze(job, verified) == 0, 'Fresh strict archived reference validation failed')
    reference = json.loads((verified / 'report.json').read_text())
    corpus = json.loads((build / 'corpus.json').read_text())
    run = json.loads((model / 'run.json').read_text())
    need(reference['pass'] is True and reference['archive_verified'] is True and
         reference['regions'] == 1320, 'All actual reference regions required')
    need(run['pass'] is True and run['regions'] == 1320 and
         run['actual_CSR_ELF_endpoint_joins'] == 3960 and
         run['complete_per_element_goldens'] == 184128 and
         run['reserved_timing_labels_consumed'] is False,
         'Complete frozen native replay and independent element/endpoint checks required')
    for name, expected in {**run['input_sha256'], **run['output_sha256']}.items():
        need(sha(name) == expected, 'Native bound input/output changed: ' + name)
    need(run['input_sha256'].get(str(build / 'guest.elf')) == sha(build / 'guest.elf') and
         run['input_sha256'].get(str(build / 'corpus.json')) == sha(build / 'corpus.json'),
         'Native must execute this exact compiled corpus')
    hardware, native = readrows(verified / 'regions.jsonl'), readrows(model / 'regions.jsonl')
    cases = corpus['cases']
    need(len(hardware) == len(native) == len(cases) == 1320, 'Exact complete row counts')
    need([r['case_id'] for r in hardware] == [r['case_id'] for r in native] ==
         [r['case_id'] for r in cases], 'Canonical complete compiled order required')
    results, grouped = [], collections.defaultdict(lambda: collections.defaultdict(list))
    for case, h, n in zip(cases, hardware, native):
        if case['internal_split'] != 'reserved_holdout':
            continue
        need(h['hart'] == n['hart'] == case['hart'] and
             h['trial_id'] == n['trial_id'] == case['trial_id'] and
             h['pass'] is True and n['pass'] is True and
             h['checksum'] == n['checksum'] == case['expected_checksum'] and
             h['checked_words'] == n['checked_words'], 'Same actual roles and independent goldens')
        row = {k: case[k] for k in ('case_id', 'hart', 'kind', 'sew', 'lmul', 'mode', 'n', 'bytes', 'trial_id')}
        row['instret_mismatch'] = n['instret_delta'] != h['instret_delta']
        for phase, start, end in (('total', 'start_cycle', 'end_cycle'),
                                  ('issue', 'start_cycle', 'issue_cycle'),
                                  ('drain', 'issue_cycle', 'end_cycle')):
            y, p = h[end] - h[start], n[end] - n[start]
            need(type(y) is int and type(p) is int and y >= 0 and p >= 0, 'Actual ordered phase counters')
            error = (p - y) / y * 100 if y else None
            row[phase] = dict(hardware_cycles=y, native_cycles=p, signed_error_percent=error)
            if error is not None:
                for group in ('all', 'hart' + str(case['hart']), 'kind:' + case['kind'],
                              'hart' + str(case['hart']) + ':' + case['kind']):
                    grouped[group][phase].append(error)
        results.append(row)
    need(len(results) == 342, 'All predeclared reserved regions and repetitions required')
    (out / 'regions.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in results))
    report = dict(schema='iris.rvv_compute1320_reserved_validation.v1', **{'pass': True},
                  regions=342, no_refit=True, all_reserved_rows_and_repetitions_retained=True,
                  timing_accuracy_certified=False, source_image_association_verified=False,
                  whole_run_timing_or_speed_claim=False, zero_duration_phase_errors_reported_as_null=True,
                  instret_mismatches=sum(r['instret_mismatch'] for r in results),
                  groups={k: {p: stats(v) for p, v in phases.items()} for k, phases in sorted(grouped.items())},
                  input_sha256={str(p): sha(p) for p in (Path(__file__).resolve(), job / 'run.json',
                      verified / 'report.json', verified / 'regions.jsonl', build / 'ready.json',
                      build / 'corpus.json', model / 'run.json', model / 'regions.jsonl')},
                  output_regions_sha256=sha(out / 'regions.jsonl'))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(pass_=True, regions=342, groups=report['groups']['all'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    for field in ('job', 'model', 'build', 'output'):
        parser.add_argument('--' + field, type=Path, required=True)
    main(parser.parse_args())
