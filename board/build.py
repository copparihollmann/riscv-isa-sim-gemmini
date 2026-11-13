#!/usr/bin/env python3
"""Build/test source-backed board helpers and retain exact local evidence."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    hardware = json.loads((HERE / 'manifest.json').read_text())
    for source in hardware['sources'].values():
        if sha(HERE / source['snapshot']) != source['sha256']:
            raise ValueError('Frozen board source digest mismatch: ' + source['snapshot'])
    if sha(HERE / 'physical_map.hpp') != hardware['physical_map_sha256']:
        raise ValueError('Generated physical map digest mismatch')
    result = subprocess.run(['bash', str(HERE / 'run_tests.sh')], text=True, capture_output=True)
    build = HERE / 'build'
    build.mkdir(exist_ok=True)
    (build / 'tests.stdout').write_text(result.stdout)
    (build / 'tests.stderr').write_text(result.stderr)
    artifacts = [build / name for name in ('boot_test', 'libiris_board_boot.so', 'iris.dtb',
                                          'tests.stdout', 'tests.stderr', 'dtc.log')]
    sources = [p for p in HERE.rglob('*') if p.is_file() and p.name != 'test-results.json'
               and 'build' not in p.relative_to(HERE).parts
               and p.suffix in {'.hpp', '.cpp', '.py', '.sh', '.json', '.img', '.scala', '.dts', '.ld', '.S'}]
    spike = HERE.parent / 'third_party/riscv-isa-sim'
    spike_build = HERE.parent / 'spike/build'
    # These are the actual linked binaries. A source association is deliberately
    # not certified while another agent develops the parent core concurrently.
    linked = [spike_build / ('lib' + name + '.a') for name in ('riscv', 'disasm', 'softfloat', 'fesvr', 'fdt')]
    record = {'schema_version': 1, 'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'passed_helper_tests' if result.returncode == 0 else 'failed',
              'exit_status': result.returncode, 'core_integration': False,
              'zephyr_smp_certified': False, 'rtl_certified': False,
              'input_sha256': {str(p.relative_to(HERE)): sha(p) for p in sorted(sources)},
              'linked_library_sha256': {str(p): sha(p) for p in linked if p.exists()},
              'artifacts': {str(p.relative_to(HERE)): sha(p) for p in artifacts if p.exists()},
              'spike_source_revision': subprocess.check_output(['git', '-C', str(spike), 'rev-parse', 'HEAD'], text=True).strip(),
              'spike_current_diff_sha256': hashlib.sha256(subprocess.check_output(['git', '-C', str(spike), 'diff', '--binary', 'HEAD'])).hexdigest(),
              'note': 'Native fixtures execute actual ROM on Spike processors; this is not an ordinary Spike/Zephyr board run or timing calibration.'}
    (HERE / 'test-results.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'artifact': str(HERE / 'test-results.json')}))
    if result.returncode:
        print(result.stderr)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
