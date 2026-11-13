#!/usr/bin/env python3
"""Verify fresh buffered fitting observations from the owned managed archive."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics
import struct
import tarfile

from analyze_campaign import read_archive, select_guest_uart
from batch_runner import digest
from prepare_buffered_priority import NO_TARGET_BOUND, ROLE, check_readback, corpus_cases, validator

ROOT = Path(__file__).resolve().parents[1]


def repetitions(rows, corpus):
    cases = {c['case_id']: c for c in corpus['cases']}
    groups = collections.defaultdict(list)
    for row in rows:
        case = cases[row['case_id']]
        groups[(case['parent_case_id'], row['hart'])].append(row)
    if len(groups) != 1350: raise ValueError('Complete1350 parent/hart groups required')
    result = []
    for (parent, hart), samples in sorted(groups.items()):
        samples.sort(key=lambda r: r['trial_id'])
        if [r['trial_id'] for r in samples] != [0, 1, 2]:
            raise ValueError('Missing or duplicate buffered trial')
        first = cases[samples[0]['case_id']]
        cycles = [r['end_cycle']-r['start_cycle'] for r in samples]
        mean = statistics.mean(cycles); deviation = statistics.pstdev(cycles)
        result.append({'parent_case_id': parent, 'semantic_parent_case_id': first['semantic_parent_case_id'],
            'suite': first['suite'], 'hart': hart,
            'samples': [{'trial_id': r['trial_id'], 'case_id': r['case_id'], 'cycles': r['end_cycle']-r['start_cycle'],
                         'instret_delta': r['instret_delta'], 'checksum': r['checksum']} for r in samples],
            'cycle_min': min(cycles), 'cycle_max': max(cycles), 'cycle_mean': mean,
            'cycle_population_stddev': deviation, 'cycle_coefficient_of_variation': deviation/mean if mean else None})
    return result


def analyze(job, output):
    job, output = Path(job).resolve(), Path(output).resolve()
    if output.exists() or job == output or job in output.parents:
        raise ValueError('Fresh analysis directory outside job required')
    output.mkdir(parents=True)
    current = json.loads((job/'run.json').read_text())
    sources = [Path(__file__).resolve(), ROOT/'firesim/analyze_campaign.py', ROOT/'firesim/batch_runner.py',
        ROOT/'firesim/prepare_buffered_priority.py', ROOT/'benchmarks/campaign_buffered/validate_priority.py',
        ROOT/'benchmarks/export_cases.py']
    report = {'schema': 'iris.buffered_priority_fitting_archive_analysis.v2', 'pass': False,
        'job': str(job), 'current_run_manifest_sha256': digest(job/'run.json'),
        'archive_verified': False, 'functional_checks_passed': False, 'managed_run_passed': False,
        'fitting_only': True, 'global_heldout': False, 'fitting_observations_available': False,
        'new_exact_ELF_reference_required': True, 'old_campaign_timings_applicable': False,
        'calibration_usable': False, 'timing_accuracy_certified': False,
        'loaded_image_verified': False, 'source_image_association_verified': False,
        'hardware_contacted_by_analysis': False, 'overhead_subtraction': False,
        'cleanup_status': current.get('cleanup_status'), 'capture_status': current.get('capture', {}).get('status'),
        'analysis_input_sha256': {str(p): digest(p) for p in sources}}
    try:
        capture = current['capture']; archive = Path(capture['archive'])
        if capture.get('status') != 'captured' or digest(archive) != capture['archive_sha256']:
            raise ValueError('Completed quiescent exact archive required')
        data, identities = read_archive(archive, capture['captured_run_manifest_sha256'])
        manifest = json.loads(data['job/run.json'])
        report.update(archive_verified=True, archive=str(archive), archive_sha256=capture['archive_sha256'],
                      archived_files=len(identities))
        if (manifest.get('campaign_role') != ROLE or manifest.get('expected_regions') != 4050
                or manifest.get('fitting_only') is not True or manifest.get('global_heldout') is not False
                or manifest.get('old_campaign_timings_applicable') is not False
                or manifest.get('new_exact_ELF_reference_required') is not True
                or manifest.get('require_regions') is not True or manifest.get('require_goldens') is not True
                or manifest.get('status') != current.get('status')
                or manifest.get('cleanup_status') != current.get('cleanup_status')):
            raise ValueError('Exact new buffered fitting experiment/outcome required; no old timing transfer')
        prelaunch_analyzer = manifest['input_sha256'].get(str(sources[0]))
        if prelaunch_analyzer not in identities.values():
            raise ValueError('Prelaunch analyzer source is missing')
        report['analysis_identity'] = {'prelaunch_analyzer_sha256': prelaunch_analyzer,
            'executed_analyzer_sha256': digest(sources[0]), 'post_run_analyzer_changed': prelaunch_analyzer != digest(sources[0]),
            'note': 'Analyzer identity repairs are explicit; corpus/validator/preparer/runner and measured bytes remain exact.'}
        for path in sources[1:]:
            expected = manifest['runner_sha256'] if path.name == 'batch_runner.py' else manifest['input_sha256'].get(str(path))
            if digest(path) != expected or expected not in identities.values():
                raise ValueError('Prelaunch source differs from analysis: '+str(path))
        if identities.get('job/corpus.json') != manifest['corpus_sha256']:
            raise ValueError('Archived buffered corpus differs')
        corpus = json.loads(data['job/corpus.json'])
        names = ['ready.json', 'build.json', 'qualification.json', 'original-corpus.json', 'readback-layout.json']
        with tarfile.open(archive, 'r:gz') as stream:
            extracted = {name: stream.extractfile('job/'+name).read() for name in names}
            extracted['campaign.elf'] = stream.extractfile('job/manager/workloads/iris-batch/batch.elf').read()
        for name, raw in extracted.items():
            member = 'job/manager/workloads/iris-batch/batch.elf' if name == 'campaign.elf' else 'job/'+name
            if hashlib.sha256(raw).hexdigest() != identities.get(member):
                raise ValueError('Archive changed during extraction: '+name)
            (output/name).write_bytes(raw)
        ready = json.loads(extracted['ready.json']); built = json.loads(extracted['build.json'])
        for name, field in [('ready.json', 'ready_sha256'), ('campaign.elf', 'elf_sha256')]:
            if digest(output/name) != manifest[field]: raise ValueError('Archived exact identity mismatch: '+name)
        for name, field in [('build.json', 'build_sha256'), ('qualification.json', 'qualification_sha256')]:
            if digest(output/name) != ready[field]: raise ValueError('Archived ready evidence changed: '+name)
        if (ready['elf_sha256'] != manifest['elf_sha256'] or ready['corpus_sha256'] != identities['job/corpus.json']
                or digest(output/'original-corpus.json') != corpus['original_corpus_sha256']
                or digest(output/'readback-layout.json') != built['readback_layout_sha256']):
            raise ValueError('Archived original goldens/ELF/readback packet mismatch')
        corpus_cases(corpus, json.loads(extracted['original-corpus.json']))
        check_readback(output/'campaign.elf', json.loads(extracted['readback-layout.json']), corpus)
        (output/'corpus.json').write_bytes(data['job/corpus.json'])
        member, report['guest_uart'] = select_guest_uart(data, identities)
        text = data[member].decode('utf-8', errors='strict'); (output/'uartlog').write_bytes(data[member])
        proof = validator().validate(text, corpus)
        report.update(functional_checks_passed=True, guest_proof=proof)
        rows = [json.loads(line.split(' ', 1)[1]) for line in text.splitlines() if line.startswith('IRIS_REGION ')]
        case_table = {c['case_id']: c for c in corpus['cases']}
        columns = ['case_id', 'parent_case_id', 'semantic_parent_case_id', 'suite', 'trial_id', 'hart', 'mask',
                   'start_cycle', 'end_cycle', 'cycles', 'instret_delta', 'checksum', 'expected_checksum']
        with (output/'regions.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader()
            for row in rows:
                case = case_table[row['case_id']]
                writer.writerow({key: row['end_cycle']-row['start_cycle'] if key == 'cycles' else
                    case[key] if key in ('semantic_parent_case_id', 'mask') else row[key] for key in columns})
        (output/'regions.json').write_text(json.dumps(rows, indent=2)+'\n')
        groups = repetitions(rows, corpus)
        (output/'repetitions.json').write_text(json.dumps(groups, indent=2)+'\n')
        report['repetition_groups'] = len(groups)
        report['lifecycle'] = [{key: r.get(key) for key in
            ('task', 'status', 'cleanup_phase', 'host_elapsed_seconds', 'returncode', 'timed_out')} for r in manifest['commands']]
        if ([(r['task'], r['status']) for r in manifest['commands']] !=
                [('kill', 'passed'), ('infrasetup', 'passed'), ('runworkload', 'passed'), ('kill', 'passed')]
                or current.get('status') != 'completed_uncertified' or current.get('cleanup_status') != 'passed'
                or current.get('error') is not None or current.get('cleanup_error') is not None):
            raise ValueError('Complete successful four-phase owned lifecycle required')
        loader = manifest['loader_override']
        if (loader.get('target_cycle_bound') is not None or loader.get('fesvr_step_size_target_cycles') != 128
                or loader.get('remote_wall_watchdog_seconds') != 600
                or loader.get('target_cycle_bound_omission_reason') != NO_TARGET_BOUND):
            raise ValueError('Wrong loader/watchdog contract')
        report['runtime_identity'] = {key: manifest.get(key) for key in
            ('image', 'driver', 'hw_config', 'prepared_runtime_sha256', 'prepared_manager_sha256', 'runner_sha256', 'loader_override')}
        if digest(archive) != capture['archive_sha256']:
            raise ValueError('Archive changed during analysis')
        if any(digest(path) != wanted for path, wanted in report['analysis_input_sha256'].items()):
            raise ValueError('Analysis source changed during parsing')
        report.update({'pass': True, 'managed_run_passed': True, 'fitting_observations_available': True,
            'qualification': 'Fresh exact-ELF buffered training observations only; source/image association and full/held-out2%accuracy remain unqualified. Original campaign timing is not transferred.'})
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, struct.error, tarfile.TarError) as error:
        report['error'] = str(error)
    report['artifact_sha256'] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ('pass', 'archive_verified', 'functional_checks_passed', 'managed_run_passed', 'error')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('job', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); raise SystemExit(analyze(args.job, args.output))
