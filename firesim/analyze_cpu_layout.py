#!/usr/bin/env python3
"""Validate CPU layout training observations from a quiescent managed archive."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics
import tarfile

from analyze_campaign import read_archive, select_guest_uart
from batch_runner import digest
from prepare_cpu_layout import ROLE, TARGET_BOUND_REASON, check_cases, check_rows, load_validator

ROOT = Path(__file__).resolve().parents[1]


def repeat_statistics(rows):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[(row['mode'], row['loop_offset'], row['n'], row['hart'])].append(row)
    if len(groups) != 771:
        raise ValueError('Every layout/N/hart repetition group is required')
    result = []
    for (mode, offset, n, hart), samples in sorted(groups.items()):
        samples.sort(key=lambda r: r['repeat'])
        if [r['repeat'] for r in samples] != [0, 1, 2]:
            raise ValueError('Missing/duplicate immediate repetition')
        cycles = [r['end_cycle']-r['start_cycle'] for r in samples]
        mean = statistics.mean(cycles)
        deviation = statistics.pstdev(cycles)
        result.append({'mode': mode, 'loop_offset': offset, 'n': n, 'hart': hart,
            'parent_case_id': f'cpu.layout.v2.{mode}.off{offset}.n{n}',
            'loop_pc': samples[0]['loop_pc'], 'begin_pc': samples[0]['begin_pc'], 'end_pc': samples[0]['end_pc'],
            'samples': [{'repeat': r['repeat'], 'cycles': r['end_cycle']-r['start_cycle'],
                         'instret_delta': r['instret_delta'], 'checksum': r['checksum']} for r in samples],
            'cycle_min': min(cycles), 'cycle_max': max(cycles), 'cycle_mean': mean,
            'cycle_population_stddev': deviation, 'cycle_coefficient_of_variation': deviation/mean if mean else None})
    return result


def analyze(job, output):
    job, output = Path(job).resolve(), Path(output).resolve()
    if output.exists() or job == output or job in output.parents:
        raise ValueError('Fresh analysis directory outside the job required')
    output.mkdir(parents=True)
    current = json.loads((job/'run.json').read_text())
    sources = [Path(__file__).resolve(), ROOT/'firesim/analyze_campaign.py', ROOT/'firesim/batch_runner.py',
               ROOT/'firesim/prepare_cpu_layout.py', ROOT/'benchmarks/cpu_layout_v2/verify.py']
    report = {'schema': 'iris.cpu_layout_archive_analysis.v1', 'pass': False,
        'job': str(job), 'current_run_manifest_sha256': digest(job/'run.json'),
        'archive_verified': False, 'functional_checks_passed': False, 'managed_run_passed': False,
        'fitting_only': True, 'global_heldout': False, 'fitting_observations_available': False,
        'calibration_usable': False, 'timing_accuracy_certified': False,
        'loaded_image_verified': False, 'source_image_association_verified': False,
        'hardware_contacted_by_analysis': False, 'overhead_subtraction': False,
        'cleanup_status': current.get('cleanup_status'), 'capture_status': current.get('capture', {}).get('status'),
        'analysis_input_sha256': {str(path): digest(path) for path in sources}}
    try:
        capture = current['capture']; archive = Path(capture['archive'])
        if capture['status'] != 'captured' or digest(archive) != capture['archive_sha256']:
            raise ValueError('Exact completed quiescent archive required')
        data, identities = read_archive(archive, capture['captured_run_manifest_sha256'])
        manifest = json.loads(data['job/run.json'])
        report.update(archive_verified=True, archive=str(archive), archive_sha256=capture['archive_sha256'],
                      archived_files=len(identities))
        if (manifest.get('campaign_role') != ROLE or manifest.get('fitting_only') is not True
                or manifest.get('global_heldout') is not False or manifest.get('expected_regions') != 2313
                or manifest.get('require_regions') is not True or manifest.get('require_goldens') is not True
                or manifest.get('status') != current.get('status')
                or manifest.get('cleanup_status') != current.get('cleanup_status')):
            raise ValueError('Archived original-order training identity/outcome mismatch')
        frozen_analyzer = manifest['input_sha256'][str(sources[0])]
        if frozen_analyzer not in identities.values():
            raise ValueError('Prelaunch analyzer source bytes are missing')
        report['analysis_identity'] = {'prelaunch_analyzer_sha256': frozen_analyzer,
            'executed_analyzer_sha256': digest(sources[0]), 'post_run_analyzer_changed': frozen_analyzer != digest(sources[0]),
            'note': 'Analyzer identity repairs are disclosed; validator/preparer/runner and all archived evidence remain exact.'}
        for path in sources[1:]:
            expected = manifest['runner_sha256'] if path.name == 'batch_runner.py' else manifest['input_sha256'].get(str(path))
            if expected != digest(path) or expected not in identities.values():
                raise ValueError('Exact prelaunch validator/preparer/runner source required: '+str(path))
        ready = json.loads(data['job/corpus.json'])
        if (identities['job/corpus.json'] != manifest['corpus_sha256']
                or identities['job/corpus.json'] != manifest['ready_sha256']
                or ready.get('schema') != 'iris.cpu_layout_ready.v1'
                or ready.get('fitting_only') is not True or ready.get('global_heldout') is not False
                or ready.get('required_regions') != 2313 or ready.get('elf_sha256') != manifest['elf_sha256']):
            raise ValueError('Frozen v2 ready/ELF packet mismatch')
        expected = {'job/binary-proof.json': ready['binary_proof_sha256'],
                    'job/qualification.json': ready['qualification_sha256'], 'job/build.json': ready['build_sha256'],
                    'job/cases.json': ready['cases_sha256'], 'job/ready.json': manifest['ready_sha256'],
                    'job/manager/workloads/iris-batch/batch.elf': manifest['elf_sha256'],
                    'job/layout-meta.json': ready['source_inputs_sha256'][str(Path(ready['elf']).parent/'layout-meta.json')]}
        extracted = {}
        with tarfile.open(archive, 'r:gz') as stream:
            for name, wanted in expected.items():
                if identities.get(name) != wanted:
                    raise ValueError('Archived input identity mismatch: '+name)
                raw = stream.extractfile(name).read()
                if hashlib.sha256(raw).hexdigest() != wanted:
                    raise ValueError('Archive changed during extraction: '+name)
                extracted[name] = raw
        for name in ('binary-proof.json', 'qualification.json', 'build.json', 'cases.json', 'ready.json', 'layout-meta.json'):
            (output/name).write_bytes(extracted['job/'+name])
        (output/'batch.elf').write_bytes(extracted['job/manager/workloads/iris-batch/batch.elf'])
        case_doc = json.loads(extracted['job/cases.json']); check_cases(case_doc)
        proof = json.loads(extracted['job/binary-proof.json'])
        built = json.loads(extracted['job/build.json'])
        toolroot = Path(built['argv'][0]).parent; nm = toolroot/'riscv64-unknown-elf-nm'
        if digest(nm) != manifest['input_sha256'].get(str(nm)) or digest(nm) not in identities.values():
            raise ValueError('Exact recorded ELF symbol reader required')
        report['analysis_input_sha256'][str(nm)] = digest(nm)
        if load_validator().inspect(output, toolroot) != proof:
            raise ValueError('Archived actual ELF binary/CSR-PC proof mismatch')
        member, report['guest_uart'] = select_guest_uart(data, identities)
        text = data[member].decode('utf-8', errors='strict')
        (output/'uartlog').write_bytes(data[member])
        rows = check_rows(text.splitlines(), proof)
        report['guest_proof'] = {'regions': len(rows), 'regions_by_hart': {str(h): sum(r['hart'] == h for r in rows) for h in range(3)},
            'independent_checksum': 'hart+1+3*N', 'exact_instret': '3*N+2 forShuttle0/1;3*N+3 forRocket2',
            'actual_loop_CSR_PCs_match_binary': True, 'noop_regions': sum(r['mode'] == 'noop' for r in rows),
            'all_word_checksums_match': True, 'counter_semantics': 'Actual guest mcycle/minstret; no host-derived cycles or overhead subtraction.'}
        report['functional_checks_passed'] = True
        columns = ['case_id', 'parent_case_id', 'hart', 'mode', 'loop_offset', 'n', 'repeat', 'loop_pc', 'begin_pc',
                   'end_pc', 'start_cycle', 'end_cycle', 'cycles', 'instret_delta', 'checksum', 'counter_end']
        with (output/'regions.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader()
            for row in rows:
                writer.writerow({key: (row['end_cycle']-row['start_cycle'] if key == 'cycles' else
                    f"cpu.layout.v2.{row['mode']}.off{row['loop_offset']}.n{row['n']}" if key == 'parent_case_id' else row[key]) for key in columns})
        (output/'regions.json').write_text(json.dumps(rows, indent=2)+'\n')
        repetitions = repeat_statistics(rows)
        (output/'repetitions.json').write_text(json.dumps(repetitions, indent=2)+'\n')
        report['repetition_groups'] = len(repetitions)
        report['lifecycle'] = [{key: row.get(key) for key in ('task', 'status', 'cleanup_phase', 'host_elapsed_seconds', 'returncode', 'timed_out')}
                               for row in manifest.get('commands', [])]
        if ([(r['task'], r['status']) for r in manifest.get('commands', [])] !=
                [('kill', 'passed'), ('infrasetup', 'passed'), ('runworkload', 'passed'), ('kill', 'passed')]
                or current.get('status') != 'completed_uncertified' or current.get('cleanup_status') != 'passed'
                or current.get('error') is not None or current.get('cleanup_error') is not None):
            raise ValueError('Complete successful owned four-phase lifecycle required')
        loader = manifest['loader_override']
        if (loader.get('target_cycle_bound') is not None or loader.get('fesvr_step_size_target_cycles') != 128
                or loader.get('remote_wall_watchdog_seconds') != 600
                or loader.get('target_cycle_bound_omission_reason') != TARGET_BOUND_REASON):
            raise ValueError('Wrong loader/watchdog policy; target bound could terminate startup')
        report['runtime_identity'] = {key: manifest.get(key) for key in ('image', 'driver', 'hw_config',
            'prepared_runtime_sha256', 'prepared_manager_sha256', 'runner_sha256', 'loader_override')}
        if digest(archive) != capture['archive_sha256']:
            raise ValueError('Archive changed during analysis')
        if any(digest(path) != wanted for path, wanted in report['analysis_input_sha256'].items()):
            raise ValueError('Analysis source/tool input changed')
        report.update({'pass': True, 'managed_run_passed': True, 'fitting_observations_available': True})
        report['qualification'] = ('Archive-bound actual original-order CPU layout training observations only. '
            'Raw per-hart cycles and three immediate repetitions are available for fitting; image/source equivalence, '
            'global held-out validation, full SoC accuracy and +/-2% certification remain unproven.')
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, AssertionError, tarfile.TarError) as error:
        report['error'] = str(error)
    report['artifact_sha256'] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ('pass', 'archive_verified', 'functional_checks_passed', 'managed_run_passed', 'error')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('job', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); raise SystemExit(analyze(args.job, args.output))
