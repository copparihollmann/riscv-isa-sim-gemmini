#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    capsule = ROOT / 'build/opu-fence-frozen-ee65eee0-v1'
    manifest = capsule / 'manifest.json'
    native = json.loads(manifest.read_text())
    assert native['pass'] is True
    bindings, reports = {}, []

    def bind(path, expected=None):
        path = Path(path).resolve()
        actual = sha(path)
        assert expected is None or actual == expected, path
        if str(path) in bindings:
            assert bindings[str(path)] == actual, path
        bindings[str(path)] = actual

    def report(path):
        value = json.loads(path.read_text())
        assert value.get('pass') is True, path
        bind(path)
        reports.append({'path': str(path), 'sha256': sha(path), 'schema': value.get('schema')})
        for field in ('input_sha256', 'output_sha256'):
            for name, digest in value.get(field, {}).items():
                bind(name, digest)
        return value

    bind(Path(__file__))
    bind(manifest)
    for name, digest in native['artifact_sha256'].items():
        bind(capsule / name, digest)
    bind(capsule / 'verification.json')
    assert json.loads((capsule / 'verification.json').read_text())['manifest_sha256'] == sha(manifest)
    for name, digest in native['qualification_sha256'].items():
        bind(name, digest)
    source = report(ROOT / 'build/opu-fence-source-v1/report.json')
    phase = report(ROOT / 'build/opu-fence-phase-v1/report.json')
    refusal = report(ROOT / 'build/opu-fence-refusals-v2/report.json')
    finite = [report(ROOT / f'build/opu-fence-finite-ON-seed{s}-v2/report.json') for s in (0, 17)]
    full = [report(ROOT / f'build/opu-fence-ON-fullcell-TK{tk}-v1/report.json') for tk in (2, 4)]
    for name in ('timing/opu_fence_guest_v1.c', 'timing/opu_fence_guest_v2.c',
                 'timing/opu_fence_guest_build_v1.py', 'timing/opu_fence_guest_build_v2.py',
                 'timing/opu_fence_guest_run_v1.py', 'timing/opu_fence_refusal_check_v1.py',
                 'timing/opu_fence_refusal_check_v2.py', 'timing/opu_fence_freeze_v1.py'):
        bind(ROOT / name)
    report(ROOT / 'build/opu-fence-finite-guest-v2/build.json')
    for name, digest in json.loads((capsule / 'native-inventory.json').read_text()).items():
        bind(Path(native['source']) / name, digest)
    for name, digest in json.loads((capsule / 'compiled-inputs.json').read_text()).items():
        bind(name, digest)
    for name in ('ON.fixture', 'OFF.fixture', 'parent-ON.json', 'parent-OFF.json', 'parent-reference-OFF.json'):
        bind(ROOT / 'build/opu-fence-inputs-v1' / name)
    for name in ('pipeline-build.pre-full-overlay.json', 'native.failed-const.log'):
        bind(ROOT / 'build/opu-fence-native-v1' / name)
    for path in [ROOT / 'build/opu-fence-refusals-v1/report.json',
                 *[ROOT / f'build/opu-fence-finite-ON-seed{s}-v1/report.json' for s in (0, 17)]]:
        bind(path)

    result = {
        'schema': 'iris.OPU_FM0_FENCE_experimental_closure.v1', 'pass': True,
        'source_frozen': True, 'native_capsule_manifest': str(manifest),
        'native_capsule_manifest_sha256': sha(manifest),
        'native_binary_sha256': native['binary_sha256'], 'uart_library_sha256': native['uart_sha256'],
        'default': 'OFF', 'enable': 'empirical_opu_fence source-MM-only-FM0-busy-not-numeric-tail-v1',
        'parent': 'exact frozen C12 TK124', 'parameters_fitted': False,
        'actual_native_phase_witnesses': sum(len(r['witnesses']) for r in phase['actual_native_runs']),
        'actual_source_Core_runs': source['core_actual_runs'],
        'numeric_finite_words_per_seed': [r['numeric_words'] for r in finite],
        'numeric_fullcell_words_per_TK': [r['numeric_words'] for r in full],
        'normal_HTIF_guests_required': True,
        'native_shape_knownness_IRQ_parser_refusals': len(refusal['cases']),
        'trace_phase_corruptions_rejected': len(phase['corruption_controls']),
        'default_OFF_byte_parity_artifacts': len(phase['default_OFF_parity']),
        'source_and_runtime_reports': reports,
        'history': {
            'cold_first_finite_guest': 'v1 fully correct, no early admission: other conservative/front/cache domains consumed the tail; preserved, not used as positive activation',
            'preexecuted_reset_finite_guest': 'v2 explicitly pre-calls the body then fully reinitializes operand/tile state; all 16 cases/full MRF checked after the measured call. No physical cache-hit assumption.',
            'parser_check_draft': 'v1 refused correctly but expected wrong error substrings; v2 checks actual declared source messages',
            'initial_build_metadata': 'Pre-full-overlay metadata preserved. Unchanged source bytes were added as git intent-to-add, then exact no-op native/plugin rebuild refreshed the full overlay. Final capsule independently reconstructs all 2,139 files and the clean four-file companion.'
        },
        'limitations': [
            'Finite h0/1 M-mode MM-only specialization; non-MM vector/config/consumers still drain numeric owners.',
            'Full source backend/trap-check composition proved independently; runtime uses conservative CPU/scoreboard/memory/FADD quiescence and successful COM+1 front bridge, not a whole CPU/VU wire certification.',
            'FENCE admission may precede FP8 tail; its COM and following CSR can already follow the last MRF write. No claim that FENCE retires before the tail.',
            'Only canonical FM0 0330000f/0ff0000f. FENCE.I and other encodings remain conservative.',
            'Intermediate-K MRF projection, IRQ/context while active, memory visibility/chaining, and exact FENCE memory-ACK timing remain outside this change.',
            'No coefficients changed, no new hardware/reference run, no held-out timing used to choose offsets, no 2% claim, no provider/default activation.'
        ],
        'hardware_contacted': False, 'global_heldout_timing_consumed': False,
        'source_image_association': False, 'timing_2pct_certified': False, 'input_sha256': bindings
    }
    (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'README.txt').write_text(
        'This default-OFF C12 successor admits the two canonical FM0 FENCE instructions after the finite MM-only source control queues drain, while keeping FP8 numeric MRF owners until their source-relative writes. Memory/FADD/IRQ/consumer restrictions and the explicit successful-COM+1 CPU bridge remain.\n\n'
        'The source proof covers full Saturn backend/trap-check composition and 48 actual cached-Core runs. Native witnesses on both compute harts and seeds 0/17 admit FENCE one edge after the last source busy microissue; later MRF writes remain, and the following CSR read stays six edges after admission. Independent matrix checks pass 65,536 words per finite run and 106,496 words for each TK2/TK4 guard run. Wrong-path and active-IRQ/unknown-VRF refusals remain. Default-OFF stdout/readback/features/async streams match the frozen C12 parent byte for byte.\n\n'
        'Enable only with the paired native/UART and explicit C12 mode plus: empirical_opu_fence source-MM-only-FM0-busy-not-numeric-tail-v1\n'
        'Review OPU-FM0-fence-on-C12.patch in the capsule. This finite experimental timing correction does not certify complete CPU/VU/memory timing. No coefficients or selected provider changed.\n')
    print(json.dumps({'pass': True, 'report_sha256': sha(output / 'report.json'),
                      'inputs': len(bindings), 'capsule_manifest_sha256': sha(manifest)}))


if __name__ == '__main__':
    main()
