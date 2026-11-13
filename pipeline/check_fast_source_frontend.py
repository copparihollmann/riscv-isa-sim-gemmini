#!/usr/bin/env python3
"""Continuous source-RTL differential qualification of the plain C++ frontend."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    component = ROOT / 'build/frontend-rtl-peer-component-v2'
    obj = component / 'obj'
    runtime = Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    sources = ['fast_source_frontend.cpp', 'fast_source_icache.cpp', 'fast_shuttle_predictor.cpp',
               'frontend_cache_pipeline.cpp', 'frontend_cache.cpp', 'frontend_rtl_peer_context.cpp']
    headers = ['fast_source_frontend.hpp', 'fast_source_icache.hpp', 'fast_shuttle_predictor.hpp',
               'frontend_cache_pipeline.hpp', 'frontend_cache.hpp', 'frontend_rtl_peer.hpp',
               'frontend_parcels.hpp', 'frontend_queue.hpp', 'fast_source_rvc_table.hpp', 'frontend_branch.hpp']
    drivers = ['test_fast_source_frontend.cpp', 'test_fast_source_frontend_loop.cpp',
               'test_fast_source_frontend_calls.cpp']
    inputs = [Path(__file__).resolve(), Path('/usr/bin/g++').resolve(),
              *[ROOT / 'pipeline' / name for name in sources + headers + drivers],
              *[ROOT / 'timing' / name for name in ['shuttle_issue.cpp', 'shuttle_issue.hpp', 'shuttle_decode_rows.inc']],
              *[obj / name for name in ['VShuttleFrontend__ALL.a', 'verilated.o', 'verilated_threads.o']],
              component / 'results.json', component / 'zero_inputs.inc',
              ROOT / 'build/frontend-alignment-source-proof-v1/report.json',
              ROOT / 'build/fast-frontend-primitives-v2/report.json',
              *[ROOT / 'build/rtl-verilator/gen-collateral' / name for name in
                ['ShuttleFrontend.sv', 'ShuttleBTB.sv', 'ShuttleICache.sv', 'ITLB.sv', 'PMAChecker.sv']],
              *[ROOT / 'third_party/shuttle/src/main/scala/ifu' / name for name in
                ['Frontend.scala', 'FetchBuffer.scala', 'ICache.scala']]]
    identities = {str(path): sha(path) for path in inputs}
    common = ['/usr/bin/g++', '-std=c++20', '-O2', '-I' + str(ROOT / 'pipeline'),
              '-I' + str(ROOT / 'timing'), '-I' + str(component), '-I' + str(obj),
              '-I' + str(runtime), '-I' + str(runtime / 'vltstd')]
    tail = [str(ROOT / 'timing/shuttle_issue.cpp'), str(obj / 'VShuttleFrontend__ALL.a'),
            str(obj / 'verilated.o'), str(obj / 'verilated_threads.o'), '-pthread']
    commands = []

    def compile_driver(name, driver, replacements=None):
        replacements = replacements or {}
        argv = [*common, str(ROOT / 'pipeline' / driver),
                *[str(replacements.get(source, ROOT / 'pipeline' / source)) for source in sources],
                *tail, '-o', str(out / name)]
        commands.append(argv)
        result = subprocess.run(argv, capture_output=True)
        (out / (name + '.build.stdout')).write_bytes(result.stdout)
        (out / (name + '.build.stderr')).write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError('Build failed: ' + name)

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    runs = []

    def run(name, binary, argv, positive=True):
        command = [str(out / binary), *map(str, argv)]
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, timeout=30, preexec_fn=limits)
        stdout, stderr = out / (name + '.stdout'), out / (name + '.stderr')
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        if positive and result.returncode:
            raise RuntimeError('Source differential failed: ' + name + ': ' + result.stderr.decode())
        row = dict(name=name, argv=command, exit_status=result.returncode,
                   stdout_sha256=sha(stdout), stderr_sha256=sha(stderr),
                   host_seconds=time.monotonic() - started)
        if positive:
            row['result'] = json.loads(result.stdout)
        else:
            message = result.stderr.decode()
            row['rejected_by_actual_source_differential'] = result.returncode != 0 and any(
                word in message for word in ['Q.', 'A.', 'FAST_SOURCE_FRONTEND_REQUIRED_RAS_TARGET_UNINITIALIZED'])
            if not row['rejected_by_actual_source_differential']:
                raise ValueError('Mutation was not detected meaningfully: ' + name)
        runs.append(row)
        return row

    for binary, driver in zip(['stream', 'loop', 'calls'], drivers):
        compile_driver(binary, driver)
    for seed in [1, 17, 31]:
        run('stream-' + str(seed), 'stream', [seed])
        run('pma-' + str(seed), 'stream', [seed, 'pma'])
    oracle = json.loads((ROOT / 'build/frontend-alignment-source-proof-v1/report.json').read_text())
    for index, case in enumerate(oracle['results']):
        row = run('loop-' + str(index), 'loop', [hex(case['loop_pc']), case['n'], case['seed']])
        if any(case[key] != value for key, value in row['result'].items()):
            raise ValueError('Original immutable oracle trace changed')
    for depth in [1, 2, 5, 6, 7, 8, 12]:
        for seed in [1, 17, 31]:
            run(f'calls-{depth}-{seed}', 'calls', [depth, seed])
    mutations = [
        ('redirect-priority', 'fast_source_frontend.cpp', 'if(in.redirect_flush) {',
         'if(false&&in.redirect_flush) {', 'test_fast_source_frontend.cpp', [1]),
        ('trailing-half', 'fast_source_frontend.cpp',
         'previous_half_valid=c.parcels.end_half_valid&&!c.parcels.redirect;',
         'previous_half_valid=false;', 'test_fast_source_frontend.cpp', [1]),
        ('ras-wrap', 'fast_source_frontend.cpp', 's2.ras_head==5?0:',
         's2.ras_head==4?0:', 'test_fast_source_frontend_calls.cpp', [7, 1]),
        ('btb-target', 'fast_source_frontend.cpp', 'predicted.valid&&predicted.taken?',
         'false?', 'test_fast_source_frontend_loop.cpp', ['0x80000468', 256, 1]),
        ('data-beat-address', 'fast_source_icache.cpp',
         'row=pending->set*8+pending->beats;',
         'row=pending->set*8+(pending->beats^1);', 'test_fast_source_frontend.cpp', [1]),
    ]
    for name, source, old, new, driver, argv in mutations:
        text = (ROOT / 'pipeline' / source).read_text()
        if text.count(old) != 1:
            raise ValueError('Mutation no longer matches exact source: ' + name)
        mutant = out / (name + '.cpp')
        mutant.write_text(text.replace(old, new))
        compile_driver('mutant-' + name, driver, {source: mutant})
        run('mutant-' + name, 'mutant-' + name, argv, positive=False)
    if any(sha(path) != digest for path, digest in identities.items()):
        raise ValueError('Source inputs changed during qualification')
    report = dict(schema='iris.fast_source_frontend.qualified_component.v1', **{'pass': True},
                  input_sha256=identities, commands=commands, runs=runs,
                  positive_cases=65, meaningful_source_mutations_rejected=5,
                  reset_seeds=[1, 17, 31], source_state_injected=False,
                  calls_fixture='Six RAS entries explicitly repaired using real CPU port before calls; native boot tested separately without repairs.',
                  boundary='Source F0/F1/F2, parcels, FIFO, 32entryBTB/512entryBHT/sixRAS, physical Icache A/D; M-mode no PTW.',
                  memory_service='Independent synthetic external accepted-A to ordered8D fixture, not measured NoC/DRAM latency.',
                  pma_scope='Saved executable permissions including unknown-manager 0x70080000 window; permission does not allocate RAM.',
                  unreset_scope='Required unreset RAS/data payload remains unknown and refuses; qualified RTL bits only; no physical power-on attestation.',
                  production_rtl_evaluation=False, full_soc_timing=False, calibration=False,
                  ethan_image_association_verified=False, timing_2pct_certified=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'positive_cases': 65, 'mutations': 5,
                      'report_sha256': sha(out / 'report.json')}))


if __name__ == '__main__':
    main()
