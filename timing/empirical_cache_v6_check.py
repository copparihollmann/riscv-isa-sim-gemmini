#!/usr/bin/env python3
"""Freeze the NEW owned-store predicate component; no native integration."""
import hashlib
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    out = ROOT / 'build/empirical-cache-v6-qualified-v1'
    out.mkdir(exist_ok=False)
    sources = [pathlib.Path(__file__).resolve(), ROOT / 'timing/empirical_cache_v6_test.cpp',
               ROOT / 'timing/empirical_cache_v5.cpp', ROOT / 'timing/empirical_cache_v6.cpp']
    sources += [ROOT / 'timing' / name for name in ('empirical_cache.hpp', 'empirical_cache_v2.hpp', 'empirical_cache_v3.hpp',
                                                   'empirical_cache_v4.hpp', 'empirical_cache_v5.hpp', 'empirical_cache_v6.hpp')]
    compiler = pathlib.Path(shutil.which('g++')).resolve()
    inputs = {str(path): sha(path) for path in [*sources, compiler]}
    runs = []
    for label, flags in [('optimized', ['-O2']), ('debug-bounds', ['-O0', '-g', '-D_GLIBCXX_ASSERTIONS', '-D_GLIBCXX_DEBUG'])]:
        executable = out / label
        argv = [str(compiler), '-std=c++20', *flags, '-I' + str(ROOT / 'timing'),
                *map(str, [ROOT / 'timing/empirical_cache_v5.cpp', ROOT / 'timing/empirical_cache_v6.cpp', ROOT / 'timing/empirical_cache_v6_test.cpp']), '-o', str(executable)]
        with (out / (label + '.compile.stdout')).open('w') as stdout, (out / (label + '.compile.stderr')).open('w') as stderr:
            subprocess.run(argv, check=True, stdout=stdout, stderr=stderr)
        result = subprocess.run([str(executable)], capture_output=True, text=True, check=True)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        observed = json.loads(result.stdout)
        if (observed.get('pass') is not True or observed.get('checks') != 150102
                or observed.get('legacy_parity_requests') != 50000 or observed.get('owned_store_requests', 0) <= 50
                or observed.get('guard_refusals') != 12):
            raise ValueError('Component checks did not qualify')
        runs.append({'label': label, 'compile_argv': argv, 'run_argv': [str(executable)], 'exit_status': 0, 'observed': observed})
    for name, expected in inputs.items():
        if sha(name) != expected:
            raise ValueError('Component source changed ' + name)
    archive = out / 'src'
    archive.mkdir()
    for path in sources:
        shutil.copy2(path, archive / path.name)
    report = {'schema': 'iris.empirical_owned_store_query_component.v1', 'pass': True,
              'scope': 'Nonmutating conservative predicate and publication-edge reservation in approximate runtime cache history; no native CPU storefront or hardware behavior certification.',
              'new_api': ['owned_store_hit(hart,address,bytes) const', 'begin_owned_store(Access)'],
              'legacy_v5_behavior_unchanged_requests_per_build': 50000,
              'native_integrated': False, 'actual_native_storefront_tested': False,
              'no_latency_or_parameter_changes': True, 'hardware_contacted': False,
              'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
              'input_sha256': inputs, 'runs': runs,
              'output_sha256': {str(path): sha(path) for path in out.iterdir() if path.is_file()}}
    (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'pass': True, 'report': str(out / 'report.json'), 'sha256': sha(out / 'report.json')}))


if __name__ == '__main__':
    main()
