#!/usr/bin/env python3
"""Analyze immutable captured bytes after the managed runner returns."""
import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import statistics
import tarfile

from batch_runner import digest
from setup_phase_observer import summarize as summarize_host, PREFIX as HOST_PREFIX

ROOT = Path(__file__).resolve().parents[1]


def read_archive(archive, expected_manifest_hash):
    wanted, identities = {}, {}
    with tarfile.open(archive, 'r:gz') as stream:
        members = stream.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive members')
        if any(not m.isfile() or PurePosixPath(m.name).is_absolute() or '..' in PurePosixPath(m.name).parts for m in members):
            raise ValueError('Archive contains unsafe/nonregular members')
        inventory = json.load(stream.extractfile('capture-manifest.json'))
        for row in inventory['files']:
            name = row['path']
            if name in identities:
                raise ValueError('Duplicate inventory member')
            member = stream.getmember(name)
            h = hashlib.sha256(); size = 0; keep = []
            retained = (name in ('job/run.json', 'job/corpus.json', 'job/capture-checklist.json')
                        or name.endswith('/uartlog') or name.startswith('job/manager/logs/') and name.endswith('.log')
                        or name.startswith('job/') and name.count('/') == 1 and name.endswith('.stdout'))
            with stream.extractfile(member) as data:
                for block in iter(lambda: data.read(1024 * 1024), b''):
                    h.update(block); size += len(block)
                    if retained:
                        keep.append(block)
            if h.hexdigest() != row['sha256'] or size != row['bytes'] or size != member.size:
                raise ValueError('Archive bytes do not match inventory: ' + name)
            identities[name] = h.hexdigest()
            if retained:
                wanted[name] = b''.join(keep)
        if set(names) != set(identities) | {'capture-manifest.json'}:
            raise ValueError('Uninventoried archive member')
    if identities.get('job/run.json') != expected_manifest_hash:
        raise ValueError('Archived pre-capture manifest does not match runner receipt')
    return wanted, identities


def validator_path(corpus, smoke):
    if not isinstance(corpus, dict):
        raise ValueError('Archived corpus must be an object')
    if smoke:
        return ROOT / 'benchmarks/validate_console.py'
    if corpus.get('split_id') == 'iris-zephyr-fpga-fit-v1':
        return ROOT / 'zephyr/firesim_fit_validate.py'
    if corpus.get('split_id') == 'iris-rvv-context-transport-fit-v1':
        return ROOT / 'benchmarks/rvv_context_transport/validate.py'
    if corpus.get('split_id') == 'iris-rvv-page-transport-fit-v1':
        return ROOT / 'benchmarks/rvv_page_transport/validate.py'
    return ROOT / 'benchmarks/campaign/validate.py'


def validate_guest(text, corpus, smoke):
    path = validator_path(corpus, smoke)
    spec = importlib.util.spec_from_file_location('iris_campaign_guest_validator', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.validate(text, corpus, 3, True) if smoke else module.validate(text, corpus)


def repetitions(text, trials):
    groups = collections.defaultdict(list)
    for line in text.splitlines():
        if line.startswith('IRIS_REGION '):
            row = json.loads(line.split(' ', 1)[1])
            key = (row['suite'], row['parent_case_id'], row['hart'])
            groups[key].append({'trial_id': row['trial_id'], 'cycles': row['end_cycle'] - row['start_cycle'],
                                'instret_delta': row['instret_delta'], 'checksum': row['checksum']})
    rows = []
    for (suite, parent, hart), samples in sorted(groups.items()):
        samples.sort(key=lambda x: x['trial_id'])
        if [s['trial_id'] for s in samples] != list(range(trials)):
            raise ValueError('Missing/duplicate trial samples')
        cycles = [s['cycles'] for s in samples]
        mean = statistics.mean(cycles); deviation = statistics.pstdev(cycles)
        rows.append({'suite': suite, 'parent_case_id': parent, 'hart': hart, 'raw_samples': samples,
                     'cycle_min': min(cycles), 'cycle_max': max(cycles), 'cycle_mean': mean,
                     'cycle_population_stddev': deviation, 'cycle_coefficient_of_variation': deviation / mean})
    return rows


def select_guest_uart(data, identities):
    """One managed guest, with an optional byte-identical cleanup copy."""
    logs = [name for name in data if name.endswith('/uartlog')]
    primary = [name for name in logs if name.startswith('job/manager/results-workload/')]
    if len(primary) > 1:
        raise ValueError('Multiple managed guest UARTs are ambiguous')
    if len(logs) == 1:
        selected = logs[0]
    elif len(primary) == 1 and set(logs) == {primary[0], 'job/optional-observability/uartlog'}:
        selected = primary[0]
        if data[selected] != data['job/optional-observability/uartlog']:
            raise ValueError('Managed guest and owned cleanup UART copies disagree')
    else:
        raise ValueError('Exactly one managed guest UART required; found ' + str(len(logs)))
    return selected, {'member': selected, 'sha256': identities[selected],
                      'identical_cleanup_copies': [{'member': name, 'sha256': identities[name]}
                          for name in logs if name != selected]}


def analyze(job, output):
    if output.exists() or job == output or job in output.parents:
        raise ValueError('Fresh analysis directory outside job required')
    output.mkdir(parents=True)
    current = json.loads((job / 'run.json').read_text())
    report = {'schema': 'iris.managed_campaign_analysis.v1', 'job': str(job),
              'current_run_manifest_sha256': digest(job / 'run.json'),
              'guest_runner_outcome': current.get('status'), 'cleanup_status': current.get('cleanup_status'),
              'capture_status': current.get('capture', {}).get('status'),
              'archive_verified': False, 'functional_checks_passed': False,
              'calibration_usable': False, 'timing_accuracy_certified': False,
              'hardware_contacted_by_analysis': False, 'overhead_subtraction': False,
              'analysis_input_sha256': {str(path): digest(path) for path in (
                  Path(__file__).resolve(), Path(__file__).with_name('batch_runner.py').resolve(),
                  Path(__file__).with_name('setup_phase_observer.py').resolve())}}
    try:
        capture = current['capture']
        if capture['status'] != 'captured':
            raise ValueError('No completed quiescent archive: ' + str(capture.get('status')))
        archive = Path(capture['archive'])
        if digest(archive) != capture['archive_sha256']:
            raise ValueError('Archive SHA256 changed')
        data, identities = read_archive(archive, capture['captured_run_manifest_sha256'])
        report.update(archive=str(archive), archive_sha256=capture['archive_sha256'],
                      archive_verified=True, archived_files=len(identities))
        manifest = json.loads(data['job/run.json'])
        report['archived_analysis_source_sha256'] = manifest.get('input_sha256', {}).get(str(Path(__file__).resolve()))
        if 'timing_perturbed' in manifest and type(manifest['timing_perturbed']) is not bool:
            raise ValueError('Timing perturbation declaration must be boolean')
        if 'baseline_timing_equivalent' in manifest and type(manifest['baseline_timing_equivalent']) is not bool:
            raise ValueError('Baseline equivalence declaration must be boolean')
        report['experiment'] = {'campaign_role': manifest.get('campaign_role'),
                                'timing_perturbed': manifest.get('timing_perturbed', False),
                                'baseline_timing_equivalent': manifest.get('baseline_timing_equivalent'),
                                'diagnostic_variant': manifest.get('diagnostic_variant')}
        for field in ('status', 'cleanup_status'):
            if current.get(field) != manifest.get(field):
                raise ValueError('Current outcome differs from archived evidence: ' + field)
        corpus = json.loads(data['job/corpus.json'])
        if identities['job/corpus.json'] != manifest['corpus_sha256']:
            raise ValueError('Archived corpus changed')
        # The archived validator identity must also match the code being used.
        smoke = manifest['campaign_role'] == 'smoke'
        validator = validator_path(corpus, smoke)
        if digest(validator) != manifest['input_sha256'].get(str(validator)):
            raise ValueError('Guest validator source changed')
        report['lifecycle'] = [{key: row.get(key) for key in
            ('task', 'cleanup_phase', 'status', 'host_elapsed_seconds', 'returncode', 'timed_out')}
            for row in manifest.get('commands', [])]
        report['host_setup'] = []
        for row in manifest.get('commands', []):
            name = 'job/' + row['stdout_path']
            if name in data:
                host = summarize_host(data[name].decode('utf-8', errors='replace'))
                if not host['records'] and row['task']=='infrasetup':
                    # FireSim routes local observer prints through its DEBUG
                    # stream logger; preserve raw logs and recover only those
                    # exact structured records for this phase.
                    records=[]
                    for member,payload in data.items():
                        if member.startswith('job/manager/logs/') and '-infrasetup-' in member:
                            for line in payload.decode('utf-8',errors='replace').splitlines():
                                marker='[DEBUG]  '+HOST_PREFIX
                                if marker in line:records.append(HOST_PREFIX+line.split(marker,1)[1])
                    host=summarize_host('\n'.join(records))
                if host['records']:
                    report['host_setup'].append(dict(host, phase_index=row['phase_index'], task=row['task']))
        member, report['guest_uart'] = select_guest_uart(data, identities)
        text = data[member].decode('utf-8', errors='strict')
        proof = validate_guest(text, corpus, smoke)
        report['guest_proof'] = proof
        if not smoke:
            report['repetitions'] = repetitions(text, corpus['trials'])
        report['functional_checks_passed'] = True
        report['managed_run_passed'] = (current.get('status') == 'completed_uncertified'
                                        and current.get('cleanup_status') == 'passed')
        report['loaded_image_verified'] = False
        report['qualification'] = 'Archive-bound guest correctness/repetition evidence only; loaded-image/source association and timing accuracy remain unqualified.'
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, UnicodeError) as error:
        report.update(error=str(error), managed_run_passed=False)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('job', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); report = analyze(args.job.resolve(), args.output.resolve())
    print(json.dumps({key: report.get(key) for key in ('archive_verified', 'functional_checks_passed', 'managed_run_passed', 'error')}))
    return 0 if report.get('managed_run_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
