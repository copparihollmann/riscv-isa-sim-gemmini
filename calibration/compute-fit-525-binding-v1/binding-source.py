#!/usr/bin/env python3
"""Bind fresh compute training, OWN525 runtime selection and tested artifacts."""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spike.empirical_provider import runtime_binding_inputs


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(pathlib.Path(path).read_text())


def main():
    selected = ROOT / 'calibration/compute-fit-525-selected-v1'
    model = ROOT / 'build/empirical-vme-work-frozen-525cc4af'
    raw_path = ROOT / 'calibration/compute-fit-525-constrained-v1/parameters.json'
    fit_path = ROOT / 'calibration/compute-fit-525-selected-evaluation-v1/report.json'
    features_path = ROOT / 'build/compute-fit-features-525-selected-v1/report.json'
    test_path = ROOT / 'build/compute-fit-525-selected-selftest-v1/report.json'
    split_path = ROOT / 'build/compute-fit-v3/split.json'
    run_path = ROOT / 'runs/fpga-compute-fit-v1-001/run.json'
    analysis_path = ROOT / 'build/fpga-compute-fit-v1-001-analysis/report.json'
    prior_path = ROOT / 'calibration/empirical-priority-28a0-binding-v2/runtime-binding.json'
    parameters, raw, fit, features, tested, split, run, analysis, prior = map(read, (selected / 'parameters.json', raw_path, fit_path, features_path, test_path, split_path, run_path, analysis_path, prior_path))
    for field, path in [('native_binary_sha256', model / 'spike'), ('uart_library_sha256', model / 'libsifive_uart.so'),
                        ('fixture_sha256', selected / 'runtime.fixture')]:
        if tested.get(field) != sha(path):
            raise ValueError('Selected byte-bound selftest mismatch ' + field)
    if (tested.get('pass') is not True or tested.get('three_harts_numerically_verified') is not True
            or tested.get('modeled_time_sensitivity_verified') is not True):
        raise ValueError('Three-hart numeric/time sensitivity selftest required')
    if (fit.get('pass') is not True or fit.get('actual_calibrated_native_replay_completed') is not True
            or fit['regions'] != 1008 or features.get('pass') is not True
            or fit['native_binary_sha256'] != sha(model / 'spike')
            or fit['fixture_sha256'] != sha(selected / 'runtime.fixture')
            or fit['calibration_identity'] != parameters['calibration_identity']):
        raise ValueError('Own final525 complete1008 counter validation required')
    if (raw.get('actual_parameter_fit_performed') is not True
            or raw['native_inputs_sha256'].get(str(model / 'spike')) != sha(model / 'spike')):
        raise ValueError('Own525 parameter fit baseline required; no previous-epoch qualification transfer')
    if (analysis.get('schema') != 'iris.compute_fitting_archive_analysis.v1'
            or any(analysis.get(k) is not True for k in ('pass', 'archive_verified', 'managed_run_passed', 'functional_checks_passed'))
            or analysis['current_run_manifest_sha256'] != sha(run_path)
            or run.get('campaign_role') != 'compute_fitting_campaign_v1'
            or run.get('cleanup_status') != 'passed' or run['capture']['archive_sha256'] != analysis['archive_sha256']
            or run['elf_sha256'] != features['reference_elf_sha256']):
        raise ValueError('Fresh complete managed compute reference required')
    training = sorted(k for k, v in split['split'].items() if v['partition'] == 'train')
    validation = sorted(k for k, v in split['split'].items() if v['partition'] == 'internal_validation')
    raw_parents = sorted({p for model_fit in raw['models'].values() for p in model_fit['training_parent_ids']})
    if set(training) & set(validation) or not set(raw_parents) <= set(training):
        raise ValueError('Frozen parent split contamination')
    inputs = {}

    def add(path):
        path = pathlib.Path(path).resolve()
        digest = sha(path)
        if str(path) in inputs and inputs[str(path)] != digest:
            raise ValueError('Conflicting input identity')
        inputs[str(path)] = digest

    paths = [pathlib.Path(__file__).resolve(), selected / 'parameters.json', selected / 'runtime.fixture', selected / 'selection.json',
             raw_path, fit_path, features_path, test_path, split_path, run_path, analysis_path, prior_path,
             model / 'manifest.json', model / 'verification.json', model / 'source-inventory.json',
             model / 'spike', model / 'libsifive_uart.so', ROOT / 'calibration/empirical-priority-28a0-runtime-v2/parameters.json',
             ROOT / 'build/compute-fit-independent-audit-v1/report.json']
    for path in paths:
        add(path)
    for document in (raw, fit, features, tested, read(selected / 'selection.json')):
        for key in ('input_sha256', 'output_sha256', 'evidence_sha256'):
            for name, expected in document.get(key, {}).items():
                path = pathlib.Path(name)
                path = path if path.is_absolute() else ROOT / path
                if sha(path) != expected:
                    raise ValueError('Changed actual training/runtime evidence ' + str(path))
                add(path)
    # Prior28 memory values retain their complete independent calibration
    # provenance. They are explicitly NOT qualified as new525 physical costs.
    inputs.update(runtime_binding_inputs(prior))
    prior_reference = prior['reference']
    reference = {'run_manifest': str(run_path), 'run_manifest_sha256': sha(run_path),
                 'analysis': str(analysis_path), 'analysis_sha256': sha(analysis_path),
                 'capture_archive_sha256': analysis['archive_sha256'], 'elf_sha256': run['elf_sha256']}
    result = {'schema': 'iris.empirical_runtime_binding.v1', 'calibration_identity': parameters['calibration_identity'],
              'native_binary_sha256': sha(model / 'spike'), 'uart_library_sha256': sha(model / 'libsifive_uart.so'),
              'fixture_sha256': sha(selected / 'runtime.fixture'), 'parameters_sha256': sha(selected / 'parameters.json'),
              'fit_report_sha256': sha(fit_path), 'actual_parameter_fit_performed': True,
              'actual_calibrated_native_replay_completed': True, 'own_native_epoch_fit_and_runtime_validation': True,
              'base_hz': 500000000, 'rtc_divider': 1000, 'counter_policy': 'source-ungated-stall',
              'vme_work': 'source-shape-subtiles-v1',
              'split': {'training_parent_case_ids': training, 'validation_parent_case_ids': validation},
              'frozen_parent_split_sha256': sha(split_path), 'fit_parent_ids': training,
              'raw_nnls_fit_parent_ids': raw_parents,
              'validation_metrics': fit['overall_including_unqualified_families'],
              'validation_metrics_include_unqualified_families': True,
              'internal_validation_scope': 'Development split; earlier diagnostic errors viewed. Not blind acceptance.',
              'reference': reference,
              'additional_prior_reference': {'reference': prior_reference, 'runtime_binding': str(prior_path),
                                             'runtime_binding_sha256': sha(prior_path), 'qualified_for_new_epoch': False},
              'timing_scope': 'Experimental source525 event model with effective costs selected using fresh1008compute FPGA TRAIN parents and actual own-epoch replays. Shared-outer/TCM/scratch values retain prior28 provenance and are unqualified transfers. Inspect all signed errors: fullmodel, arbitrary shapes, wholeZephyr/end-to-end and2%guarantees remain unavailable.',
              'source_fit_scope': {'cost_semantics': parameters['cost_semantics'], 'unqualified': parameters['unqualified'],
                                   'logical_unit_issue_interval1_and_capacity1_are_not_independently_fitted_physical_peaks': True,
                                   'no_runtime_benchmark_ID_or_golden_PC_lookup': True,
                                   'source_model_manifest': str(model / 'manifest.json'), 'source_model_manifest_sha256': sha(model / 'manifest.json'),
                                   'raw_fit': str(raw_path), 'raw_fit_sha256': sha(raw_path)},
              'normal_guest_exit_verified': False, 'whole_run_or_end_to_end_timing_validated': False,
              'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
              'full_model_certified': False, 'rtl_certified': False, 'source_image_association_verified': False,
              'input_sha256': inputs}
    out = ROOT / 'calibration/compute-fit-525-binding-v1'
    out.mkdir(exist_ok=False)
    (out / 'binding-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
    destination = out / 'runtime-binding.json'
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'binding': str(destination), 'sha256': sha(destination), 'input_files': len(inputs), 'validation_metrics': result['validation_metrics']}, indent=2))


if __name__ == '__main__':
    main()
