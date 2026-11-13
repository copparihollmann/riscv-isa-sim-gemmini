#!/usr/bin/env python3
"""Bound archive-backed FASED activity without assuming a complete histogram.

The archived LatencyPipe updates bins <=0, <=2, <=4 and <=8. Its advertised
overflow bin stays zero. We therefore use histogram counts as LOWER bounds on
profiled memory cycles and the driver's absolute fastest-clock count as an
UPPER bound, never as per-region elapsed time. Counter increments are at most
one per model tick. If every interval's upper bound is below 2**32, modular
differences have unique lifts. Otherwise no unwrapped totals are admitted.

Interpretation is conditional on the pinned RTL/register mapping, stable
paused snapshots, no target reset between samples, and the fastest-clock bound.
This does not infer DRAM-chip busy, physical serial-link bytes or hart attribution.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re
import tarfile

from analyze_campaign import read_archive, select_guest_uart
from batch_runner import digest
from summarize_fased import parse

MOD = 2**32
TRANSACTIONS = ('totalReads', 'totalReadBeats', 'totalWrites', 'totalWriteBeats')
HIST = {side: [f'{side}OutstandingHistogram_{i}' for i in range(5)]
        for side in ('read', 'write')}
REVIEWED_DRIVER = '8f78167b754097623b031f41d7e5f121f4ae368f716255fdcf574693a071c48a'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify_associations(manifest, evidence, audit, audit_digest, identities):
    """The interpretation evidence must be the evidence frozen for THIS run."""
    observed = manifest['observability_audit']
    require(observed['report'] == str(audit) and observed['sha256'] == audit_digest and
            manifest['input_sha256'].get(str(audit)) == audit_digest and
            identities.get('job/prepared-inputs/'+audit_digest) == audit_digest,
            'Interpretation audit not bound to this archived run')
    require(observed['fased'] == evidence['fased'], 'Archived register semantics differ')
    uri = manifest['driver']['uri']
    require(uri.startswith('file:///'), 'Only exact local reviewed driver bundle supported')
    bundle = Path(uri[len('file://'):])
    expected = manifest['driver']['sha256']
    require(evidence['input_sha256'].get(str(bundle)) == expected and
            manifest['input_sha256'].get(str(bundle)) == expected and
            identities.get('job/prepared-inputs/'+expected) == expected,
            'Actual archived driver bundle is not bound to reviewed evidence')
    members = [r for r in evidence['driver_members'] if r['name'] == 'FireSim-corigine_mimicturbo_gt']
    require(len(members) == 1 and members[0]['sha256'] == evidence['driver_binary_sha256'] == REVIEWED_DRIVER,
            'Actual bundle does not identify the reviewed driver binary')
    return bundle


def calculate(raw, names, fastest_cycle_upper_bound):
    require(type(fastest_cycle_upper_bound) is int and fastest_cycle_upper_bound > 0,
            'Positive absolute fastest-clock upper bound required')
    checked = parse(raw, names)
    require(checked.get('samples', 0) >= 2, 'Two complete counter snapshots required')
    required = set(TRANSACTIONS) | set(HIST['read']) | set(HIST['write'])
    require(required <= set(names), 'Missing target counters')
    source = list(csv.reader(io.StringIO(raw.decode('ascii'))))
    header = source[0][:-1] if source[0][-1:] == [''] else source[0]
    rows = [dict(zip(header, map(int, r[:-1] if r[-1:] == [''] else r)))
            for r in source[1:] if r]
    require(all(r[HIST[side][-1]] == 0 for r in rows for side in HIST),
            'Pinned RTL has a constant-zero overflow bin; source mapping differs')
    fields = sorted(required)
    intervals = []
    for index, (a, b) in enumerate(zip(rows, rows[1:]), 1):
        delta = {k: (b[k] - a[k]) % MOD for k in fields}
        by_side = {s: sum(delta[k] for k in HIST[s]) for s in HIST}
        intervals.append(dict(sample_interval=index, delta=delta,
            memory_cycles_lower_bound=max(by_side.values()), histogram_cycles_by_direction=by_side))
    lower = sum(r['memory_cycles_lower_bound'] for r in intervals)
    require(0 < lower <= fastest_cycle_upper_bound,
            'Histogram clock lower bound contradicts absolute clock upper bound')
    slack = fastest_cycle_upper_bound - lower
    for row in intervals:
        row['memory_cycles_upper_bound'] = row['memory_cycles_lower_bound'] + slack
    unique = all(r['memory_cycles_upper_bound'] < MOD for r in intervals)
    result = dict(schema='iris.fased_activity_bounds.v1',
        status='unique_modular_lifts' if unique else 'ambiguous_counter_wraps',
        samples=len(rows), snapshot_interval_count=len(intervals),
        profiled_memory_cycles_bounds=[lower, fastest_cycle_upper_bound],
        unexplained_cycle_budget=slack, all_interval_counter_lifts_unique=unique,
        driver_clock_role='absolute upper bound; NOT per-run/per-region elapsed time',
        scope='whole sampled workload, including initialization, preconditions, checks and console',
        per_region_attribution=False, per_hart_attribution=False,
        overflow_bin_complete=False, histogram_maxima=[0, 2, 4, 8],
        direction_activity=None,
        memory_chip_busy_fraction=None, serial_TL_bandwidth=None, NoC_link_bandwidth=None,
        usable_write_bytes=None, physical_DMA_busy_fraction=None,
        assumptions=['pinned archived RTL/register semantics apply',
          'profile snapshots are taken while target is paused',
          'no target reset between snapshots',
          'memory model ticks no faster than the reported fastest target clock'],
        intervals=intervals)
    if not unique:
        result['unwrapped_counters'] = None
        return result
    for row in intervals:
        require(all(value <= row['memory_cycles_upper_bound'] for value in row['delta'].values()),
                'Counter changes exceed one increment per model cycle')
    total = {k: sum(r['delta'][k] for r in intervals) for k in fields}
    result['unwrapped_counters'] = total
    result['direction_activity'] = {}
    for side, beat_name, request_name in (
            ('read', 'totalReadBeats', 'totalReads'),
            ('write', 'totalWriteBeats', 'totalWrites')):
        idle = total[HIST[side][0]]
        beats = total[beat_name]
        result['direction_activity'][side] = dict(
            outstanding_nonempty_fraction_bounds=[1-idle/lower, 1-idle/fastest_cycle_upper_bound],
            data_channel_accepted_beat_fraction_bounds=[beats/fastest_cycle_upper_bound, beats/lower],
            accepted_beats=beats, accepted_requests=total[request_name],
            accepted_beats_per_request=beats/total[request_name] if total[request_name] else None,
            AXI_wire_payload_capacity_bytes=8*beats,
            AXI_wire_payload_capacity_bytes_per_memory_cycle_bounds=[
                8*beats/fastest_cycle_upper_bound, 8*beats/lower],
            useful_payload_bytes=None,
            qualification='64-bit AXI bus capacity carried by accepted beats; narrow transfers/write strobes not observed. Outstanding != data-channel occupancy != DRAM-chip busy.')
    result['sampled_time_lower_fraction_of_absolute_upper_bound'] = lower/fastest_cycle_upper_bound
    return result


def summarize(job, output, audit):
    job, output, audit = job.resolve(), output.resolve(), audit.resolve()
    require(not output.exists() and job != output and job not in output.parents,
            'Fresh output outside immutable job required')
    current_digest = digest(job/'run.json')
    current = json.loads((job/'run.json').read_text())
    cap = current['capture']
    require(current.get('cleanup_status') == 'passed' and not current.get('lock_retained_for_operator')
            and not current.get('cleanup_error') and cap['status'] == 'captured',
            'Known owned cleanup and completed archive required')
    archive = Path(cap['archive'])
    require(digest(archive) == cap['archive_sha256'], 'Archive digest changed')
    data, identities = read_archive(archive, cap['captured_run_manifest_sha256'])
    manifest = json.loads(data['job/run.json'])
    for key in ('status', 'cleanup_status', 'error', 'cleanup_error'):
        require(current.get(key) == manifest.get(key), 'Archived/current result differs')
    evidence = json.loads(audit.read_text())
    bundle = verify_associations(manifest, evidence, audit, digest(audit), identities)
    require(digest(bundle) == manifest['driver']['sha256'], 'Live reviewed bundle changed')
    rtl_candidates = [(Path(p), sha) for p, sha in evidence['input_sha256'].items()
                      if p.endswith('/design/FireSim-generated.sv')]
    require(len(rtl_candidates) == 1, 'Exact archived RTL evidence required')
    rtl, expected = rtl_candidates[0]
    require(expected == 'c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64'
            and digest(rtl) == expected, 'Unsupported or changed RTL mapping')
    driver = Path('/scratch/copparihollmann/iris-model/firesim/artifacts/archived-build-driver-v1/FireSim-corigine_mimicturbo_gt')
    require(digest(driver) == evidence['driver_binary_sha256'] == REVIEWED_DRIVER,
            'Reviewed archived driver required')
    member = 'job/optional-observability/memory_stats0.csv'
    require(member in identities, 'Memory telemetry missing')
    with tarfile.open(archive, 'r:gz') as stream:
        raw = stream.extractfile(member).read()
    import hashlib
    require(hashlib.sha256(raw).hexdigest() == identities[member], 'CSV digest changed')
    uart_name, uart_selection = select_guest_uart(data, identities)
    matches = re.findall(rb'^Target Cycles Emulated: ([0-9]+)\s*$', data[uart_name], re.M)
    require(len(matches) == 1, 'One actual driver fastest-clock upper bound required')
    result = calculate(raw, manifest['observability_audit']['fased']['periodic_stats_registers'],
                       int(matches[0]))
    result.update(hardware_contacted=False, source_image_association_verified=False,
        conditional_source_mapping=True, timing_accuracy_certified=False,
        job=str(job), original_guest_status=current['status'],
        archive_sha256=cap['archive_sha256'], csv_sha256=identities[member],
        uart_selection=uart_selection,
        input_sha256={str(p): digest(p) for p in (Path(__file__).resolve(),
            Path(__file__).with_name('summarize_fased.py'), Path(__file__).with_name('analyze_campaign.py'),
            Path(__file__).with_name('batch_runner.py'), audit, rtl, driver, bundle)})
    result['evidence_locations'] = dict(
        counter_width_and_increment='archived FireSim-generated.sv:10183-10189,10442-10459',
        histogram_partition_and_missing_overflow='archived FireSim-generated.sv:10191-10216,10462-10500',
        FASED_model_and_target_clock_gate='archived FireSim-generated.sv:11434-11480,11664-11668',
        AXI_payload_width='archived FireSim-generated.sv:10988,11008',
        fastest_clock_counter='archived FireSim-generated.sv:12285-12290,12388-12391',
        reviewed_driver_pause_order='archived driver .text0x41a00 simulation_run; profile0x61070; peek_poke is_done0x6ce00',
        sample_timestamps='not present; no invented sample cadence or per-region joins')
    require(digest(job/'run.json') == current_digest and digest(archive) == cap['archive_sha256'],
            'Original evidence changed during analysis')
    output.mkdir(parents=True)
    (output/'source-reader.py').write_bytes(Path(__file__).read_bytes())
    (output/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    with (output/'intervals.csv').open('x', newline='') as stream:
        keys = ['sample_interval', 'memory_cycles_lower_bound', 'memory_cycles_upper_bound', *TRANSACTIONS]
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in result['intervals']:
            writer.writerow({**{k:row[k] for k in keys[:3]},
                             **{k:row['delta'][k] for k in TRANSACTIONS}})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit', type=Path, default=Path('/scratch/copparihollmann/iris-model/build/firesim-observability-archived-driver-v3/report.json'))
    args = parser.parse_args()
    result = summarize(args.job, args.output, args.audit)
    print(json.dumps({k: result[k] for k in ('status', 'samples', 'profiled_memory_cycles_bounds', 'direction_activity')}))
