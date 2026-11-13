#!/usr/bin/env python3
"""Close the frozen selected-28a0 epoch after its owned replay succeeds."""
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    replay = ROOT / 'build/empirical-priority-28a0-calibrated-v2'
    joined = ROOT / 'build/empirical-priority-28a0-calibrated-features-v2'
    actual = ROOT / 'calibration/empirical-priority-28a0-actual-v2'
    binding = ROOT / 'calibration/empirical-priority-28a0-binding-v2'
    selected = ROOT / 'calibration/empirical-priority-28a0-runtime-v2'
    raw = ROOT / 'calibration/empirical-priority-28a0-fit-v2'
    baseline = ROOT / 'build/empirical-priority-28a0-features-v1'
    capsule = ROOT / 'build/empirical-fast-frozen-28a0a52b'
    out = ROOT / 'build/empirical-priority-28a0-finalize-v2'
    out.mkdir(exist_ok=False)
    sources = [pathlib.Path(__file__).resolve(),
               ROOT / 'timing/empirical_priority_live_features.py',
               ROOT / 'timing/empirical_live_features_v3.py',
               ROOT / 'timing/empirical_priority_runtime_report.py',
               ROOT / 'timing/empirical_priority_bind.py']
    expected = {str(path): sha(path) for path in sources}
    receipt = {'schema': 'iris.empirical_priority_epoch_finalization.v1', 'status': 'awaiting_owned_calibrated_replay',
               'input_sha256': expected, 'hardware_contacted': False,
               'global_heldout_timings_consumed': False}

    def save():
        (out / 'report.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    save()
    while True:
        try:
            replay_receipt = json.loads((replay / 'run.json').read_text())
        except json.JSONDecodeError:
            time.sleep(1)
            continue
        if replay_receipt['status'] != 'running':
            break
        time.sleep(5)
    if replay_receipt.get('pass') is not True:
        receipt.update(status='refused_failed_calibrated_replay', replay_error=replay_receipt.get('error'))
        save()
        raise SystemExit('Actual calibrated replay did not qualify')
    for path, digest in expected.items():
        if sha(path) != digest:
            raise ValueError('Finalization source changed ' + path)
    receipt['status'] = 'processing_completed_replay'
    save()
    commands = [
        [sys.executable, str(ROOT / 'timing/empirical_priority_live_features.py'),
         '--receipt', str(replay / 'run.json'), '--regions', str(replay / 'regions.jsonl'),
         '--features', str(replay / 'features.jsonl'), '--output', str(joined)],
        [sys.executable, str(ROOT / 'timing/empirical_priority_runtime_report.py'),
         '--baseline', str(baseline / 'regions.jsonl'), '--baseline-report', str(baseline / 'report.json'),
         '--calibrated', str(joined / 'regions.jsonl'), '--calibrated-report', str(joined / 'report.json'),
         '--parameters', str(selected / 'parameters.json'), '--fixture', str(selected / 'runtime.fixture'),
         '--output', str(actual)],
        [sys.executable, str(ROOT / 'timing/empirical_priority_bind.py'),
         '--native', str(capsule / 'spike'), '--uart', str(capsule / 'libsifive_uart.so'),
         '--fixture', str(selected / 'runtime.fixture'), '--parameters', str(selected / 'parameters.json'),
         '--raw-parameters', str(raw / 'parameters.json'), '--fit-report', str(actual / 'report.json'),
         '--selftest', str(ROOT / 'build/empirical-priority-28a0-selected-selftest-v2/report.json'),
         '--selection-report', str(selected / 'selection-report.json'), '--output', str(binding)],
    ]
    receipt['commands'] = []
    try:
        for index, argv in enumerate(commands):
            with (out / ('phase%d.stdout' % index)).open('w') as stdout, (out / ('phase%d.stderr' % index)).open('w') as stderr:
                result = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr)
            receipt['commands'].append({'argv': argv, 'exit_status': result.returncode})
            save()
            if result.returncode:
                raise ValueError('Finalization phase%d refused; inspect raw stderr' % index)
        final = json.loads((binding / 'runtime-binding.json').read_text())
        receipt.update(status='frozen_actual_partial_runtime_binding_ready', pass_=True,
                       runtime_binding=str(binding / 'runtime-binding.json'), runtime_binding_sha256=sha(binding / 'runtime-binding.json'),
                       actual_fit_report=str(actual / 'report.json'), actual_fit_report_sha256=sha(actual / 'report.json'),
                       fixture=str(selected / 'runtime.fixture'), fixture_sha256=sha(selected / 'runtime.fixture'),
                       validation_metrics=final['validation_metrics'],
                       full_2pct_certified=False, full_model_certified=False)
        receipt['pass'] = receipt.pop('pass_')
    except (ValueError, OSError, KeyError) as error:
        receipt.update(status='finalization_refused', pass_=False, error=str(error))
        receipt['pass'] = receipt.pop('pass_')
    save()
    print(json.dumps({k: receipt.get(k) for k in ('status', 'runtime_binding', 'actual_fit_report', 'validation_metrics', 'error')}, indent=2))
    if receipt.get('pass') is not True:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
