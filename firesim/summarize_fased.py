#!/usr/bin/env python3
"""Archive-bound raw FASED telemetry summary; no hardware access or time inference."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

from analyze_campaign import read_archive
from batch_runner import digest

TRANSACTIONS = ('totalReads', 'totalReadBeats', 'totalWrites', 'totalWriteBeats')
STATUS = ('brespError', 'rrespError')


def parse(raw, expected, tail_samples=4):
    if type(tail_samples) is not int or tail_samples < 2:
        raise ValueError('At least two tail samples required')
    if not expected or len(expected) != len(set(expected)):
        raise ValueError('Unambiguous audited register names required')
    rows = list(csv.reader(io.StringIO(raw.decode('ascii'))))
    if not rows:
        return {'status': 'empty', 'samples': 0}
    header = rows[0][:-1] if rows[0][-1:] == [''] else rows[0]
    if len(header) != len(set(header)) or set(header) != set(expected):
        raise ValueError('CSV columns differ from audited instantiated registers')
    values = []
    for row in rows[1:]:
        if not row:
            continue
        cells = row[:-1] if row[-1:] == [''] else row
        if len(cells) != len(header) or any(not re.fullmatch(r'[0-9]+', x) or int(x) >= 2**32 for x in cells):
            raise ValueError('Invalid/truncated 32-bit FASED snapshot')
        values.append(dict(zip(header, map(int, cells))))
    if not values:
        return {'status': 'no_samples', 'samples': 0, 'register_names': header}
    tail = values[-tail_samples:]
    stable = {key: len(tail) >= 2 and len({r[key] for r in tail}) == 1 for key in header}
    counter_names = [k for k in header if k not in STATUS]
    return {'status': 'summarized_raw_snapshots', 'samples': len(values), 'register_names': header,
        'readout_width_bits': 32, 'first_raw': values[0], 'last_raw': values[-1],
        'tail_raw': tail, 'tail_observed_constant': stable,
        'tail_transaction_registers_all_observed_constant':
            len(tail) >= 2 and all(stable.get(k, False) for k in TRANSACTIONS),
        'tail_modular_counter_deltas': {key: [(b[key] - a[key]) % 2**32 for a, b in zip(tail, tail[1:])]
                                       for key in counter_names},
        'raw_decrease_sample_indices': {key: [index for index in range(1, len(values))
                                              if values[index][key] < values[index-1][key]] for key in counter_names},
        'status_registers_raw': {k: values[-1][k] for k in STATUS if k in header},
        'raw_status_zero_is_not_a_complete_bus_error_proof': True,
        'counter_unwrapping': 'Not performed: full wraps, resets and sample-clock alignment need separate proof.',
        'snapshot_atomicity_verified': False, 'sample_target_timestamps': None,
        'elapsed_target_cycles': None, 'bandwidth_bytes_per_cycle': None,
        'per_hart_attribution': None, 'occupancy_bin_thresholds_verified': False,
        'latency_distribution': None,
        'qualification': 'Raw register stability and modular differences only; no missing timing/width, transaction ownership, histogram thresholds or global unwrapped counts are inferred.'}


def summarize(job, output):
    if output.exists() or output == job or job in output.parents:
        raise ValueError('Fresh summary directory outside the job required')
    output.mkdir(parents=True)
    current = json.loads((job / 'run.json').read_text())
    capture = current.get('capture', {})
    if current.get('cleanup_status') != 'passed' or capture.get('status') != 'captured':
        raise ValueError('Completed owned cleanup and immutable capture required')
    archive = Path(capture['archive'])
    if digest(archive) != capture['archive_sha256']:
        raise ValueError('Archive digest changed')
    data, identities = read_archive(archive, capture['captured_run_manifest_sha256'])
    manifest = json.loads(data['job/run.json'])
    if manifest['status'] != current['status'] or manifest['cleanup_status'] != current['cleanup_status']:
        raise ValueError('Current outcome differs from captured run')
    member = 'job/optional-observability/memory_stats0.csv'
    report = {'schema': 'iris.archived_fased_raw_telemetry.v1', 'job': str(job),
        'guest_status': manifest['status'], 'guest_error': manifest.get('error'),
        'archive_verified': True, 'archive_sha256': digest(archive),
        'hardware_contacted': False, 'calibration_usable': False,
        'source_image_association_verified': False, 'full_batch_functional_pass_claimed': False,
        'input_sha256': {str(Path(__file__).resolve()): digest(Path(__file__)),
                         str(Path(__file__).with_name('analyze_campaign.py').resolve()): digest(Path(__file__).with_name('analyze_campaign.py'))}}
    report['input_sha256'][str(Path(__file__).with_name('batch_runner.py').resolve())] = digest(Path(__file__).with_name('batch_runner.py'))
    if member not in identities:
        report['telemetry'] = {'status': 'missing', 'samples': 0}
    else:
        with tarfile.open(archive, 'r:gz') as stream:
            raw = stream.extractfile(member).read()
        if hashlib.sha256(raw).hexdigest() != identities[member]:
            raise ValueError('Counter bytes changed after archive verification')
        names = manifest['observability_audit']['fased']['periodic_stats_registers']
        report.update(csv_member=member, csv_sha256=identities[member], telemetry=parse(raw, names))
    if digest(archive) != capture['archive_sha256']:
        raise ValueError('Archive changed during summary')
    (output / 'source-snapshot.py').write_bytes(Path(__file__).read_bytes())
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__);p.add_argument('job', type=Path);p.add_argument('--output', type=Path, required=True)
    a = p.parse_args();r = summarize(a.job.resolve(), a.output.resolve())
    print(json.dumps({'archive_verified': r['archive_verified'], 'guest_status': r['guest_status'],
                      'telemetry_status': r['telemetry']['status'], 'samples': r['telemetry']['samples']}))
