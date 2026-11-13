#!/usr/bin/env python3
"""Freeze a runtime binding only after matched actual counter replay and checks."""
import argparse
import hashlib
import json
import pathlib
from urllib.parse import unquote, urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(pathlib.Path(path).read_text())


def freeze(args):
    parameters, raw, report, split = [read(p) for p in (args.parameters, args.raw_parameters, args.fit_report, args.split)]
    tested, run, analysis = [read(p) for p in (args.selftest, args.reference_run, args.reference_analysis)]
    if (report.get('schema') != 'iris.empirical_priority_actual_runtime_validation.v1'
            or report.get('actual_calibrated_native_replay_completed') is not True
            or report.get('all_numeric_goldens_passed') is not True):
        raise ValueError('Successful actual byte-bound calibrated replay required')
    for field, path in [('native_binary_sha256', args.native), ('uart_library_sha256', args.uart),
                        ('fixture_sha256', args.fixture), ('parameters_sha256', args.parameters)]:
        if report.get(field) != sha(path) or (field != 'parameters_sha256' and tested.get(field) != sha(path)):
            raise ValueError('Actual replay/selftest artifact mismatch ' + field)
    if (tested.get('pass') is not True or tested.get('three_harts_numerically_verified') is not True
            or tested.get('modeled_time_sensitivity_verified') is not True):
        raise ValueError('All-three-hart numeric and modeled-time sensitivity required')
    if parameters['raw_parameters_sha256'] != sha(args.raw_parameters):
        raise ValueError('Raw fitted parameters changed')
    if report['reference_archive_sha256'] != run['capture']['archive_sha256']:
        raise ValueError('Actual reference archive mismatch')
    if (run.get('campaign_role') != 'buffered_priority_fitting_campaign_v2'
            or run.get('fitting_only') is not True or run.get('global_heldout') is not False
            or run.get('status') != 'completed_uncertified' or run.get('cleanup_status') != 'passed'
            or run.get('error') is not None or run.get('cleanup_error') is not None
            or run['capture'].get('status') != 'captured'
            or analysis.get('schema') != 'iris.buffered_priority_fitting_archive_analysis.v2'
            or analysis.get('current_run_manifest_sha256') != sha(args.reference_run)
            or analysis.get('archive_sha256') != run['capture']['archive_sha256']
            or any(analysis.get(k) is not True for k in ('pass', 'archive_verified', 'managed_run_passed', 'functional_checks_passed'))):
        raise ValueError('Exact independently checked managed fitting reference required')
    if ([(entry.get('task'), entry.get('status')) for entry in run.get('commands', [])] !=
            [('kill', 'passed'), ('infrasetup', 'passed'), ('runworkload', 'passed'), ('kill', 'passed')]
            or run.get('expected_regions') != 4050 or len(run.get('regions', [])) != 4050
            or analysis.get('guest_proof', {}).get('regions') != 4050):
        raise ValueError('All4050 reference regions and complete owned lifecycle required')
    training = sorted(k for k, v in split['split'].items() if v['partition'] == 'train')
    validation = sorted(k for k, v in split['split'].items() if v['partition'] == 'internal_validation')
    fit_parents = sorted({k for model in raw['models'].values() for k in model['training_parent_ids']})
    if set(training) & set(validation) or not set(fit_parents).issubset(training):
        raise ValueError('Parameter fitting crosses frozen partition')
    if any(v.get('global_heldout_timings_consumed') is not False for v in (parameters, raw, report, split)):
        raise ValueError('Global heldout fitting contamination')
    paths = [pathlib.Path(__file__), args.native, args.uart, args.fixture, args.parameters, args.raw_parameters,
             args.fit_report, args.split, args.selftest, args.selection_report,
             args.reference_run, args.reference_analysis]
    inputs = {str(p.resolve()): sha(p) for p in paths}
    # Bind direct source/evidence maps as well as their containing reports. Do
    # not replace any original packet or silently normalize its declared data.
    for source in (raw, report, tested, read(args.selection_report)):
        for key in ('input_sha256', 'output_sha256', 'evidence_sha256'):
            for name, digest in source.get(key, {}).items():
                path = pathlib.Path(name)
                path = path if path.is_absolute() else ROOT / path
                if sha(path) != digest:
                    raise ValueError('Fitting/runtime evidence changed ' + str(path))
                name = str(path.resolve())
                if name in inputs and inputs[name] != digest:
                    raise ValueError('Conflicting evidence identity ' + name)
                inputs[name] = digest
    model = read(args.model_manifest)
    if model.get('binary_sha256') != sha(args.native) or model.get('uart_sha256') != sha(args.uart):
        raise ValueError('Wrong frozen model capsule')
    inventory_path = args.model_manifest.parent / 'source-inventory.json'
    inventory = read(inventory_path)
    if model['artifact_sha256']['source-inventory.json'] != sha(inventory_path):
        raise ValueError('Frozen model source inventory changed')
    implementation = {}
    selected_sources = [model['native_source_relative'] + '/riscv/' + name for name in
                        ('iris_timing_adapter.cc', 'iris_timing_adapter.h', 'iris_shuttle_issue.cc',
                         'iris_counter_observations.cc', 'iris_event_graph.cc')]
    selected_sources += ['timing/empirical_cache_v5.cpp', 'timing/empirical_cache_v5.hpp']
    for name in selected_sources:
        path = args.model_manifest.parent / 'src' / name
        if sha(path) != inventory[name]:
            raise ValueError('Frozen actual feature/cost implementation changed ' + name)
        inputs[str(path.resolve())] = inventory[name]
        implementation[name] = inventory[name]
    for path in (args.model_manifest, inventory_path):
        inputs[str(path.resolve())] = sha(path)
    observability = read(args.observability)
    for field in ('image', 'driver'):
        artifact = run[field]
        uri = urlparse(artifact['uri'])
        if uri.scheme != 'file':
            raise ValueError('Exact local reference collateral required')
        name = str(pathlib.Path(unquote(uri.path)).resolve())
        if observability['input_sha256'].get(name) != artifact['sha256']:
            raise ValueError('Reference collateral differs from instrumentation audit')
    bitstreams = [entry['sha256'] for entry in observability['image_members'] if entry['name'].endswith('/firesim.bit')]
    if len(bitstreams) != 1:
        raise ValueError('Unique archived reference bitstream required')
    inputs[str(args.observability.resolve())] = sha(args.observability)
    result = {
        'schema': 'iris.empirical_runtime_binding.v1',
        'calibration_identity': parameters['calibration_identity'],
        'native_binary_sha256': sha(args.native), 'uart_library_sha256': sha(args.uart),
        'fixture_sha256': sha(args.fixture), 'parameters_sha256': sha(args.parameters),
        'fit_report_sha256': sha(args.fit_report),
        'actual_parameter_fit_performed': True, 'actual_calibrated_native_replay_completed': True,
        'base_hz': parameters['base_hz'], 'rtc_divider': parameters['rtc_divider'],
        'counter_policy': parameters['counter_policy'],
        'split': {'training_parent_case_ids': training, 'validation_parent_case_ids': validation},
        'frozen_parent_split_sha256': sha(args.split), 'fit_parent_ids': fit_parents,
        'validation_metrics': report['overall_including_unqualified_families'],
        'validation_metrics_include_unqualified_families': True,
        'internal_validation_scope': report['internal_validation_scope'],
        'measured_regions': report['regions'], 'reference_regions': report['reference_regions'],
        'unmatched_reference_regions': report['unmatched_reference_regions'],
        'reference': {'run_manifest': str(args.reference_run.resolve()),
                      'run_manifest_sha256': sha(args.reference_run),
                      'analysis': str(args.reference_analysis.resolve()),
                      'analysis_sha256': sha(args.reference_analysis),
                      'capture_archive_sha256': run['capture']['archive_sha256'],
                      'elf_sha256': run['elf_sha256'],
                      'image_archive_sha256': run['image']['sha256'],
                      'driver_archive_sha256': run['driver']['sha256'],
                      'bitstream_sha256': bitstreams[0],
                      'driver_binary_sha256': observability['driver_binary_sha256'],
                      'instrumentation_audit': str(args.observability.resolve()),
                      'instrumentation_audit_sha256': sha(args.observability),
                      'source_image_association_verified': False},
        'timing_scope': 'Experimental additional effective services fitted to the NEW priority-v2 FPGA ELF; actual matched kernel counter replay only. Internal validation is development evidence. Default full-model, arbitrary-shape, whole-Zephyr/end-to-end, and 2% guarantees are unavailable.',
        'source_fit_scope': {'costs': 'Positive runtime-event costs only; no region intercept, negative adjustment, benchmark/PC lookup or trial feature.',
                             'outer': parameters['shared_outer'], 'quantization': parameters['quantization'],
                             'unqualified': parameters['unapplied'],
                             'configured_family_actual_coverage': report['configured_family_actual_coverage'],
                             'unreached_configured_family_rules': report['unreached_configured_family_rules']},
        'normal_guest_exit_verified': False, 'whole_run_or_end_to_end_timing_validated': False,
        'feature_schema': {'prefix': 'iris.empirical.prefix.v1', 'region': 'iris.empirical.runtime_region_features.v1',
                           'source': 'Actual successful CSR read endpoints, runtime classified retired instructions and owned memory/cache events.'},
        'model_implementation': {'source_manifest': str(args.model_manifest.resolve()),
                                 'source_manifest_sha256': sha(args.model_manifest),
                                 'base_spike_commit': model['base_commit'],
                                 'source_overlay_sha256': model['source_overlay_sha256'],
                                 'selected_feature_and_cost_sources_sha256': implementation,
                                 'complete_source_inventory': str(inventory_path.resolve()),
                                 'complete_source_inventory_sha256': sha(inventory_path)},
        'global_heldout_timings_consumed': False, 'full_model_certified': False,
        'full_2pct_certified': False, 'rtl_certified': False, 'source_image_association_verified': False,
        'input_sha256': inputs,
    }
    args.output.mkdir(parents=True, exist_ok=False)
    destination = args.output / 'runtime-binding.json'
    destination.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    (args.output / 'binding-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
    print(json.dumps({'binding': str(destination), 'sha256': sha(destination), 'metrics': result['validation_metrics']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('native', 'uart', 'fixture', 'parameters', 'raw-parameters', 'fit-report', 'selftest', 'selection-report', 'output'):
        parser.add_argument('--' + name, type=pathlib.Path, required=True)
    parser.add_argument('--split', type=pathlib.Path, default=ROOT / 'calibration/empirical-priority-v2/split.json')
    parser.add_argument('--reference-run', type=pathlib.Path, default=ROOT / 'runs/fpga-buffered-priority-v2-001/run.json')
    parser.add_argument('--reference-analysis', type=pathlib.Path, default=ROOT / 'build/fpga-buffered-priority-v2-001-analysis/report.json')
    parser.add_argument('--model-manifest', type=pathlib.Path, default=ROOT / 'build/empirical-fast-frozen-28a0a52b/manifest.json')
    parser.add_argument('--observability', type=pathlib.Path, default=ROOT / 'build/firesim-observability-archived-driver-v3/report.json')
    freeze(parser.parse_args())
