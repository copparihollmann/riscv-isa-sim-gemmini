#!/usr/bin/env python3
"""Independent integer/Decimal semantic review of the VME capacity overlay.

Deliberately does not import the overlay's arithmetic or payload classifiers.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--overlay', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    report = read(a.overlay/'report.json')
    d = read(a.overlay/'overlay.json')
    source = read(ROOT/'build/throughput-limits-source-v3/report.json')
    profile = read(ROOT/'build/full-graph-VME-profile-v4/summary.json')
    require(report.get('pass') is True and d.get('pass') is True, 'Actual overlay must pass')
    require(len(d['regions']) == 6 and len(profile['observed_regions']) == 6, 'Exactly six actual regions')
    inputs = {str((a.overlay/n).resolve()): digest(a.overlay/n) for n in ('overlay.json','overlay.svg','report.json')}
    for name, expected in report['input_sha256'].items():
        require(digest(name) == expected, 'Stale input: '+name)
    for name, expected in report['artifact_sha256'].items():
        require(digest(a.overlay/name) == expected, 'Stale artifact: '+name)
    for row, actual in zip(d['regions'], profile['observed_regions']):
        h = actual['hart']; begin = actual['start_cycle']; end = actual['end_cycle']
        require(row['hart'] == h and row['region'] == actual['region'], 'Actual region identity')
        require(row['global_window']['source_core_edge_opportunities'] == end-begin, 'Actual all-divider1 edge calendar')
        require(row['global_window']['guest_mcycle_delta'] == actual['guest_mcycle_delta'], 'Do not substitute mcycle for global time')
        expected_work = 32 * 32 * 1 * 4 if h in (0,1) else 0
        require(row['algorithm']['logical_MACs'] == expected_work, 'Independent shape * instruction work')
        work = row['completion']
        require(sum(x['macs'] for x in work['credited_operations']) == expected_work, 'Credited node work sum')
        require(work['boundary_or_pending_MAC_payloads'] == [], 'No unresolved boundary MAC credit')
        require(len(work['credited_operations']) == (4 if h in (0,1) else 0), 'Actual four MAC actors per compute ROI')
        for node in work['credited_operations']:
            require(begin <= node['start'] < node['end'] < end, 'Strict actor completion before end read')
            require(row['kernel_symbol_address'] <= node['pc'] < row['kernel_symbol_end'], 'Actual ELF PC bounds')
        if h == 2:
            require(row['source_capacity'] is None and row['conditional_source_peak_fraction']['fraction'] is None, 'No invented hart2 OPU')
        else:
            matches = [r for r in source['capacity_records'] if r['hart'] == h and r['family'] == row['family']]
            require(len(matches) == 1 and matches[0]['value'] == 16*16, 'One selected physical array, no format sum')
            require(row['source_capacity'] == matches[0], 'Exact source condition/evidence propagation')
            expected_fraction = Decimal(expected_work)/Decimal((end-begin)*16*16)
            require(abs(Decimal(str(row['conditional_source_peak_fraction']['fraction']))-expected_fraction) < Decimal('1e-16'), 'Independent Decimal peak fraction')
            require(row['byte_coordinates']['retired_instruction_requested_data_bytes'] == 128+72+8, 'Data-byte denominator includes scalar/control and vector output only')
            require(row['byte_coordinates']['accepted_timing_intent_requested_data_bytes'] == 208, 'Distinct accepted intent ledger')
            require(row['byte_coordinates']['retired_VRF_row_move_bytes_excluded_from_data_denominator'] == 128, 'VRF transfer is not data-memory traffic')
        b = row['byte_coordinates']
        require(b['physical_DRAM_bytes'] is None and b['physical_L2_bytes'] is None and b['physical_arithmetic_intensity'] is None, 'Physical traffic remains unknown')
        for k in ('physical_OPU_utilization','physical_MAC_rate','memory_bandwidth_bytes_per_second','memory_slope','physical_roofline','stall_breakdown'):
            require(row[k] is None, 'No unmeasured physical inference: '+k)
    require(sum(r['algorithm']['logical_MACs'] for r in d['regions']) == 16384, 'Total logical work')
    require(d['full_graph_partial_at_exit'] is True and d['full_graph_pending_operations'] == 8, 'Do not hide partial post-ROI CPU tail')
    result = subprocess.run([sys.executable,'-m','unittest','tests.test_conditional_capacity_overlay','-v'], cwd=ROOT, text=True, capture_output=True)
    (a.output/'unit-stdout.txt').write_text(result.stdout)
    (a.output/'unit-stderr.txt').write_text(result.stderr)
    require(result.returncode == 0 and 'Ran 16 tests' in result.stderr, 'All semantic unit controls required')
    for path in (Path(__file__), ROOT/'iris_model/conditional_capacity_overlay.py', ROOT/'tests/test_conditional_capacity_overlay.py'):
        inputs[str(path.resolve())] = digest(path)
    result = dict(schema='iris.conditional_capacity_independent_semantic_review.v1',
                  pass_=True, independent_decimal_clock_capacity_check=True,
                  exact_source_conditions_propagated=True, requested_vs_physical_bytes_separated=True,
                  all16_semantic_controls_passed=True, actual_ROIs=6, logical_MACs=16384,
                  partial_graph_tail_disclosed=True, hardware_contacted=False,
                  global_heldout_timings_consumed=False, physical_roofline_available=False,
                  input_sha256=inputs)
    result['pass'] = result.pop('pass_')
    result['artifact_sha256'] = {n:digest(a.output/n) for n in ('unit-stdout.txt','unit-stderr.txt')}
    (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':True,'ROIs':6,'logical_MACs':16384,'controls':16}))


if __name__ == '__main__':
    main()
