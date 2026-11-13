"""Archive-bound total-cost comparison of the admitted scalar im2col candidates.

No FPGA access. Whole clean caller intervals select observed candidates; profile
phases are descriptive and are never substituted for clean timing. All current
transform cases are development data, not held-out compiler validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time

JOBS = ('conv-transform-nchw', 'conv-transform-nhwc')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text())


def checked(path, expected):
    require(Path(path).is_absolute() and sha(path) == expected, 'Changed input: ' + str(path))


def summarize(plan, profile):
    require(profile.get('pass') is True and profile.get('counter_semantics') == 'target_mcycle_uncalibrated',
            'Accepted actual FPGA target counters required; native/model counts refused')
    cases = plan['cases']
    require(sorted(c['tile_m'] for c in cases) == [0, 32, 128, 512], 'Exact four panel candidates required')
    require(len({(c['m'], c['n'], c['k'], c['expected_checksum'], json.dumps(c['input_sha256'], sort_keys=True))
                 for c in cases}) == 1, 'Panel candidates must use identical operands, shape and oracle')
    geometry = ('batch', 'ci', 'co', 'h', 'w', 'kh', 'kw', 'stride', 'pads', 'oh', 'ow',
                'layout', 'weight_layout', 'warmup', 'measured')
    require(len({json.dumps({k: c[k] for k in geometry}, sort_keys=True) for c in cases}) == 1,
            'Panel candidates must share the exact convolution and conditioning contract')
    results = []
    for index, case in enumerate(cases):
        m, n, k = (case[v] for v in ('m', 'n', 'k'))
        require(min(m, n, k) > 0 and case['kind'] == 'conv_im2col_i8', 'Positive convolution GEMM required')
        record = dict(case=case['name'], m=m, n=n, k=k, tile_rows=case['tile_m'],
                      A_panel_capacity_bytes=k * min(m, case['tile_m'] or m),
                      B_packed_capacity_bytes=k*n, output_capacity_bytes=4*m*n, routes={})
        for backend in ('RVV', 'VME'):
            variant = backend + '_I8_clean'
            rows = [r for r in profile['rows'] if r['case_index'] == index and
                    r['variant'] == variant and not r['warmup']]
            require(len(rows) == case['measured'] >= 2, 'All measured clean repetitions required')
            require(len({r['repetition'] for r in rows}) == len(rows), 'Duplicate repetitions refused')
            require({r['repetition'] for r in rows} == set(range(case['warmup'], case['warmup']+case['measured'])),
                    'Unexpected measured repetition identities')
            for r in rows:
                require(r['pass'] is True and r['hart'] == 0 and
                        all(r.get(key, 0) == 0 for key in ('checksum_errors', 'sample_errors', 'full_word_errors', 'guard_errors')) and
                        r['checksum'] == r['expected_checksum'] == case['expected_checksum'],
                        'Strict numeric/guard admission required')
                require(r['end_cycle'] > r['start_cycle'] and
                        r['instret_delta'] == r['end_instret'] - r['start_instret'], 'Invalid counter endpoints')
            ticks = [r['end_cycle'] - r['start_cycle'] for r in rows]
            median = statistics.median(ticks)
            summary = next(x for x in profile['metrics'] if x['case'] == case['name'] and x['variant'] == variant)
            require(median == summary['cycles_median'], 'Summary differs from raw clean counters')
            profile_metric = next(x for x in profile['metrics'] if x['case'] == case['name'] and
                                  x['variant'] == backend + '_I8_profile')
            instrumented = [r for r in profile['rows'] if r['case_index'] == index and
                            r['variant'] == backend + '_I8_profile' and not r['warmup']]
            require(len(instrumented) == case['measured'], 'Complete profile observer controls required')
            profile_ticks = statistics.median(r['end_cycle']-r['start_cycle'] for r in instrumented)
            profile_phases = [statistics.median(r['caller_phase_ticks'][i] for r in instrumented) for i in range(5)]
            require(profile_ticks == profile_metric['cycles_median'] and
                    profile_phases == profile_metric['caller_phase_ticks_median'],
                    'Profile summary differs from raw observer controls')
            record['routes'][backend] = dict(total_cycle_samples=ticks, total_cycle_median=median,
                total_cycle_min=min(ticks), total_cycle_max=max(ticks), useful_MACs_per_cycle=m*n*k/median,
                profile_caller_cycle_median=profile_metric['cycles_median'],
                profile_phase_ticks=profile_metric['caller_phase_ticks_median'],
                profile_over_clean_observed_ratio=profile_metric['cycles_median']/median,
                clean_preparation_phase_cycles=None,
                phase_scope='profile-only combined A unfolding and B reorder; not exact clean overhead subtraction')
        record['RVV_over_VME_total_ratio'] = record['routes']['RVV']['total_cycle_median'] / record['routes']['VME']['total_cycle_median']
        results.append(record)
    baseline = next(x for x in results if x['tile_rows'] == 0)
    for result in results:
        for route in ('RVV', 'VME'):
            result['routes'][route]['full_unfold_baseline_over_candidate_total_ratio'] = (
                baseline['routes'][route]['total_cycle_median'] / result['routes'][route]['total_cycle_median'])
    lowest = min(((r['routes'][route]['total_cycle_median'], r['tile_rows'], route)
                  for r in results for route in ('RVV', 'VME')))
    return dict(candidates=results, observed_lowest_median=dict(cycles=lowest[0], tile_rows=lowest[1], route=lowest[2]),
                selection_scope='lowest observed clean median among these eight development candidates; no heldout certification',
                physical_busy=None, physical_memory_bytes=None, DMA_busy=None)


def admitted_job(queue, name, state):
    job, analysis = queue/'jobs'/name, queue/'analysis'/name
    require(state.get('status') == 'passed_archive_postgate' and state.get('analysis_passed') is True,
            'Full archived postgate required')
    checked(job/'run.json', state['run_sha256'])
    checked(analysis/'report.json', state['analysis_sha256'])
    run, gate, built = read(job/'run.json'), read(analysis/'report.json'), read(job/'build.json')
    require(run['status'] == 'completed_uncertified' and run['cleanup_status'] == 'passed' and
            not run.get('lock_retained_for_operator') and gate['passed'] is True, 'Owned cleanup and strict admission required')
    require([c['task'] for c in run['commands']] == ['kill', 'infrasetup', 'runworkload', 'kill'] and
            all(c['status'] == 'passed' for c in run['commands']), 'All four managed phases required')
    cap = run['capture']
    require(cap['status'] == 'captured' and cap['archive_sha256'] == gate['archive_sha256'], 'Archive identity mismatch')
    checked(cap['archive'], cap['archive_sha256'])
    require(built['elf_sha256'] == run['elf_sha256'], 'Wrong measured ELF')
    checked(built['elf'], built['elf_sha256'])
    for path, expected in built['input_sha256'].items():
        checked(path, expected)
    plans = [Path(p) for p in built['input_sha256'] if p.endswith('/plan.json')]
    require(len(plans) == 1, 'Unique bound source plan required')
    plan = read(plans[0])
    profile_path = analysis/'profile/report.json'
    profile = read(profile_path)
    checked(analysis/'uartlog', gate['guest_uart']['sha256'])
    raw_rows = [json.loads(line[len('IRIS_REGION '):]) for line in (analysis/'uartlog').read_text().splitlines()
                if line.startswith('IRIS_REGION ')]
    require(raw_rows == profile['rows'], 'Profile changed from the exact archived UART records')
    result = summarize(plan, profile)
    result['input_sha256'] = {str(p): sha(p) for p in (job/'run.json', job/'build.json', analysis/'report.json',
                                                     profile_path, plans[0], Path(cap['archive']))}
    result['ELF_sha256'] = run['elf_sha256']
    result['source_image_association_verified'] = False
    return result


def collect(queue, output, wait_seconds):
    require(not output.exists(), 'Fresh output directory required')
    output.mkdir(parents=True)
    # Only this successful exclusive mkdir authorizes progress/error writes.
    # Refusing somebody else's existing output must leave it byte-for-byte alone.
    try:
        return _collect_owned(queue, output, wait_seconds)
    except Exception as error:
        failure = dict(status='failed_or_refused', error=repr(error), hardware_contacted=False)
        with (output/'collector-failure.json').open('x') as stream:
            stream.write(json.dumps(failure, indent=2)+'\n')
        (output/'status.json').write_text(json.dumps(failure, indent=2)+'\n')
        raise


def _collect_owned(queue, output, wait_seconds):
    deadline = time.monotonic() + wait_seconds
    code = sha(__file__)
    while True:
        state = read(queue/'queue-status.json')
        jobs = state.get('jobs', {})
        ready = [n for n in JOBS if jobs.get(n, {}).get('status') == 'passed_archive_postgate']
        complete = (queue/'arming-status.json').exists() and read(queue/'arming-status.json').get('status') in (
            'finite_queue_finished', 'withheld_or_failed')
        (output/'status.json').write_text(json.dumps(dict(status='waiting_for_owned_cleanup_archive_postgates', ready=ready,
            hardware_contacted=False, heldout_compiler_validation=False), indent=2)+'\n')
        if len(ready) == len(JOBS) or complete or state.get('hardware_stopped') or time.monotonic() >= deadline:
            break
        time.sleep(min(20, max(0, deadline-time.monotonic())))
    require(sha(__file__) == code, 'Collector source changed while waiting')
    results = {name: admitted_job(queue, name, jobs[name]) for name in ready}
    report = dict(schema='iris.compiler_transform_total_costs.v1', status='completed' if len(ready) == len(JOBS) else 'partial_or_unavailable',
        admitted_jobs=results, missing_jobs=[n for n in JOBS if n not in ready], source_sha256=code,
        hardware_contacted=False, data_usage='compiler_transform_development', compiler_default_changed=False,
        physical_unit_busy_available=False, timing_model_accuracy_claimed=False,
        scope='raw signed-I8 convolution; scalar layout packing plus exact admitted RVV/VME primitives; no new quantization')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'status.json').write_text(json.dumps(dict(status=report['status'], admitted_jobs=list(results),
        missing_jobs=report['missing_jobs'], hardware_contacted=False), indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--queue-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait-seconds', type=int, default=18000)
    args = parser.parse_args()
    require(0 <= args.wait_seconds <= 18000, 'Finite at-most-five-hour read-only wait required')
    collect(args.queue_root.resolve(), args.output.resolve(), args.wait_seconds)
