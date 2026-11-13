#!/usr/bin/env python3
"""Join qualified NEW compute reference and own native epoch counter features."""
import argparse
import collections
import hashlib
import json
import pathlib
import sys

from empirical_live_features_v3 import join, read_complete

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.compute_fit.validate import check_rows


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main(args):
    build = args.build.resolve()
    analysis = json.loads(args.analysis.read_text())
    reference_run = json.loads(args.reference_run.read_text())
    if (analysis.get('schema') != 'iris.compute_fitting_archive_analysis.v1'
            or any(analysis.get(k) is not True for k in ('pass', 'archive_verified', 'functional_checks_passed', 'managed_run_passed', 'fitting_observations_available'))
            or analysis.get('fitting_only') is not True or analysis.get('global_heldout') is not False
            or analysis.get('current_run_manifest_sha256') != sha(args.reference_run)
            or analysis.get('archive_sha256') != reference_run['capture']['archive_sha256']):
        raise ValueError('Fresh independently checked compute fitting archive required')
    archive = pathlib.Path(reference_run['capture']['archive'])
    if sha(archive) != analysis['archive_sha256']:
        raise ValueError('Actual reference archive bytes changed')
    if (reference_run.get('campaign_role') != 'compute_fitting_campaign_v1'
            or reference_run.get('cleanup_status') != 'passed' or reference_run.get('status') != 'completed_uncertified'
            or reference_run.get('global_heldout') is not False):
        raise ValueError('Wrong actual reference role/outcome')
    for name, digest in analysis['artifact_sha256'].items():
        if sha(args.analysis.parent / name) != digest:
            raise ValueError('Reference artifact changed ' + name)
    for name, digest in analysis['analysis_input_sha256'].items():
        if sha(name) != digest:
            raise ValueError('Reference analysis source changed ' + name)
    corpus = json.loads((build / 'corpus.json').read_text())
    split = json.loads((build / 'split.json').read_text())
    elf = build / 'campaign.elf'
    if sha(elf) != reference_run['elf_sha256'] or sha(build / 'corpus.json') != reference_run['corpus_sha256']:
        raise ValueError('New reference/native corpus/ELF identity mismatch')
    raw_reference = json.loads((args.analysis.parent / 'regions.json').read_text())
    check_rows(raw_reference, corpus)
    native_receipt = json.loads(args.receipt.read_text())
    if (native_receipt.get('schema') != 'iris.compute_fitting_native_readback.v1'
            or native_receipt.get('pass') is not True or native_receipt.get('all_numeric_goldens_passed') is not True
            or native_receipt.get('status') != 'completed_measured_regions_with_intentional_debugger_stop'
            or native_receipt.get('normal_guest_exit_verified') is not False
            or native_receipt.get('hardware_contacted') is not False
            or native_receipt.get('global_heldout_timings_consumed') is not False
            or native_receipt['argv'][-1] != str(elf)):
        raise ValueError('Own qualified actual complete1008 native counter readback required')
    combined = {**native_receipt['input_sha256'], **native_receipt['output_sha256']}
    for name, digest in combined.items():
        if sha(name) != digest:
            raise ValueError('Native replay artifact changed ' + name)
    for path in (args.regions, args.features):
        if combined.get(str(path.resolve())) != sha(path):
            raise ValueError('Unbound native artifact')
    native = [json.loads(s) for s in args.regions.read_text().splitlines()]
    check_rows(native, corpus)
    cases = {c['case_id']: c for c in corpus['cases']}
    observations = []
    for r in raw_reference:
        case = cases[r['case_id']]
        entry = split['split'][case['parent_case_id']]
        observations.append({'schema': 'iris.empirical_fitting_observation.v1',
                             'case_id': case['case_id'], 'parent_case_id': case['parent_case_id'],
                             'semantic_parent_case_id': case['semantic_parent_case_id'],
                             'semantic_group': entry['semantic_group'], 'partition': entry['partition'],
                             'family': entry['family'], 'hart': r['hart'], 'trial_id': case['trial_id'],
                             'cycles': r['end_cycle'] - r['start_cycle'], 'instret_delta': r['instret_delta'],
                             'checksum': r['checksum'], 'expected_checksum': r['expected_checksum'],
                             'actual_FPGA_reference': True, 'global_heldout': False})
    _, lines = read_complete(args.features)
    prefixes = [json.loads(s) for s in lines]
    fixture = pathlib.Path(next(v.split('=', 1)[1] for v in native_receipt['argv'] if v.startswith('--iris-timing-fixture=')))
    identity = [line.split()[2] for line in fixture.read_text().splitlines() if line.startswith('empirical_profile ')]
    if len(identity) != 1 or any(p.get('calibration_identity') != identity[0] for p in prefixes):
        raise ValueError('Native/fixture feature identity mismatch')
    rows, stats = join(observations, native, [p for p in prefixes if p.get('result_discarded') is False])
    if len(rows) != 1008 or stats['partial']:
        raise ValueError('Incomplete new compute counter join')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'observations.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in observations))
    (args.output / 'regions.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    coverage = collections.Counter()
    for row in rows:
        for family, values in row['features'].items():
            coverage[family] += values['instructions']
    canonical = {'schema': 'iris.empirical_training_native_replay.v1',
                 'status': 'qualified_all_measured_regions_post_ROI_stop',
                 'argv': native_receipt['argv'], 'input_sha256': {**combined, str(args.receipt.resolve()): sha(args.receipt)},
                 'all_observed_numeric_goldens_passed': True, 'normal_guest_exit_verified': False,
                 'hardware_contacted': False, 'global_heldout_timings_consumed': False, 'native_region_count': 1008}
    (args.output / 'native-baseline.json').write_text(json.dumps(canonical, indent=2, sort_keys=True) + '\n')
    report = {'schema': 'iris.empirical_compute_runtime_feature_join.v1', 'pass': True,
              'regions': 1008, 'calibration_identity': identity[0], 'partial': False,
              'native_binary_sha256': sha(native_receipt['argv'][0]), 'fixture_sha256': sha(fixture),
              'reference_archive_sha256': analysis['archive_sha256'], 'reference_elf_sha256': sha(elf),
              'runtime_family_instruction_coverage': dict(coverage),
              'reference': {'run_manifest': str(args.reference_run.resolve()), 'analysis': str(args.analysis.resolve())},
              'actual_parameter_fit_performed': False, 'normal_guest_exit_verified': False,
              'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
              'old_timing_labels_imported': False, 'case_ids_are_runtime_features': False,
              'input_sha256': {str(p.resolve()): sha(p) for p in (pathlib.Path(__file__), ROOT / 'timing/empirical_live_features_v3.py',
                                args.analysis, args.reference_run, build / 'campaign.elf', build / 'corpus.json', build / 'split.json',
                                args.receipt, args.regions, args.features, ROOT / 'benchmarks/compute_fit/validate.py',
                                args.analysis.parent / 'regions.json', archive)},
              'output_sha256': {str(p.resolve()): sha(p) for p in args.output.iterdir() if p.is_file()}}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'pass': True, 'regions': 1008, 'report': str(args.output / 'report.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=pathlib.Path, default=ROOT / 'build/compute-fit-v3')
    for name in ('analysis', 'reference-run', 'receipt', 'regions', 'features', 'output'):
        parser.add_argument('--' + name, type=pathlib.Path, required=True)
    main(parser.parse_args())
