#!/usr/bin/env python3
"""Validate BF16 observations against the exact quiescent managed-run archive."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

from analyze_campaign import read_archive, repetitions, select_guest_uart
from batch_runner import digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks/scalar_bf16_probe'))
from validate import validate


def analyze(job, output):
    if output.exists() or job == output or job in output.parents:
        raise ValueError('Fresh analysis directory outside job required')
    output.mkdir(parents=True)
    current = json.loads((job / 'run.json').read_text())
    sources = [Path(__file__).resolve(), Path(__file__).with_name('analyze_campaign.py').resolve(),
               Path(__file__).with_name('batch_runner.py').resolve(),
               ROOT / 'benchmarks/scalar_bf16_probe/validate.py', ROOT / 'benchmarks/scalar_bf16_probe/cases.py']
    report = {'schema': 'iris.scalar_bf16_archive_analysis.v1', 'pass': False,
        'hardware_contacted': False, 'calibration_usable': False, 'timing_certified': False,
        'source_image_association_verified': False, 'input_sha256': {str(p): digest(p) for p in sources},
        'current_manifest_sha256': digest(job / 'run.json'), 'archive_verified': False}
    try:
        capture = current['capture']
        archive = Path(capture['archive'])
        if capture['status'] != 'captured' or digest(archive) != capture['archive_sha256']:
            raise ValueError('Exact quiescent archive required')
        data, identities = read_archive(archive, capture['captured_run_manifest_sha256'])
        manifest = json.loads(data['job/run.json'])
        report.update(archive_verified=True, archive_sha256=capture['archive_sha256'])
        if (manifest['status'] != current['status'] or manifest['cleanup_status'] != current['cleanup_status']
                or manifest['campaign_role'] != 'scalar_bf16_decoder_diagnostic'
                or manifest['require_goldens'] is not True or manifest['require_regions'] is not True):
            raise ValueError('Archived outcome or diagnostic contract mismatch')
        for path in sources[-2:]:
            if manifest['input_sha256'].get(str(path)) != digest(path):
                raise ValueError('Archived independent validator/corpus source changed')
            if digest(path) not in identities.values():
                raise ValueError('Independent validator source missing from archive')
        if identities['job/corpus.json'] != manifest['corpus_sha256']:
            raise ValueError('Archived corpus binding mismatch')
        corpus = json.loads(data['job/corpus.json'])
        elf_name = 'job/manager/workloads/iris-batch/batch.elf'
        if identities.get(elf_name) != manifest['elf_sha256']:
            raise ValueError('Actual archived ELF binding mismatch')
        with tarfile.open(archive, 'r:gz') as stream:
            elf = stream.extractfile(elf_name).read()
        if hashlib.sha256(elf).hexdigest() != manifest['elf_sha256']:
            raise ValueError('Archived ELF changed while extracting')
        elf_path = output / 'observed.elf'
        elf_path.write_bytes(elf)
        member, report['guest_uart'] = select_guest_uart(data, identities)
        uart = data[member].decode('utf-8', errors='strict')
        (output / 'uartlog').write_bytes(data[member])
        (output / 'corpus.json').write_bytes(data['job/corpus.json'])
        report['guest_proof'] = validate(uart, corpus, elf_path)
        report['repetitions'] = repetitions(uart, 5)
        report['lifecycle'] = [{k: row.get(k) for k in
            ('task', 'status', 'cleanup_phase', 'host_elapsed_seconds', 'returncode', 'timed_out')}
            for row in manifest['commands']]
        if ([(r['task'], r['status']) for r in manifest['commands']] != [
                ('kill', 'passed'), ('infrasetup', 'passed'), ('runworkload', 'passed'), ('kill', 'passed')]
                or current['status'] != 'completed_uncertified' or current['cleanup_status'] != 'passed'
                or current.get('error') is not None or current.get('cleanup_error') is not None):
            raise ValueError('Complete successful four-phase lifecycle required')
        if digest(archive) != capture['archive_sha256']:
            raise ValueError('Archive changed during analysis')
        if any(digest(name) != expected for name, expected in report['input_sha256'].items()):
            raise ValueError('Analysis sources changed during validation')
        report['pass'] = True
        report['qualification'] = 'Actual selected FPGA image observations for these16instruction encodings only; full image/source association and complete dtype/timing certification remain unproven.'
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, tarfile.TarError) as error:
        report['error'] = str(error)
    report['artifact_sha256'] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ('pass', 'archive_verified', 'guest_proof', 'error')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('job', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raise SystemExit(analyze(a.job.resolve(), a.output.resolve()))
