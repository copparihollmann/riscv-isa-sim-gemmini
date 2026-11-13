#!/usr/bin/env python3
"""Bounded exact-RTL differential for compute store ROB / metadata groundwork."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--verilator', type=Path, default=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator'))
    a = p.parse_args()
    o = a.output.resolve()
    if o.exists():
        raise ValueError('Fresh component directory required')
    o.mkdir(parents=True)
    (o / 'rtl').mkdir()
    sv = ROOT / 'build/rtl-verilator/gen-collateral/ReorderBuffer.sv'
    shutil.copy2(sv, o / 'rtl/ReorderBuffer.sv')
    # These activate the unchanged saved module's diagnostic guards. They do
    # not alter reset, queues, datapath or any target handshake.
    cmd = [str(a.verilator), '--cc', '--exe', '--build', '-j', '4', '--assert',
           '-Wno-fatal', '+define+ASSERT_VERBOSE_COND_=1', '+define+STOP_COND_=1',
           '--top-module', 'ReorderBuffer', '--prefix', 'VStoreRob',
           '--Mdir', str(o / 'obj'), '-CFLAGS', '-std=c++20 -O2 -I' + str(ROOT / 'timing'),
           str(o / 'rtl/ReorderBuffer.sv'), str(ROOT / 'timing/rvv_memory_fabric_boundary_v1_check.cpp')]
    def run(argv, label, bound):
        try:
            r = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=bound,
                               env=dict(os.environ, PATH=str(a.verilator.parent) + os.pathsep + os.environ.get('PATH', '')))
        except subprocess.TimeoutExpired as e:
            (o / (label + '.stdout')).write_bytes(e.stdout or b'')
            (o / (label + '.stderr')).write_bytes(e.stderr or b'')
            raise
        (o / (label + '.stdout')).write_bytes(r.stdout)
        (o / (label + '.stderr')).write_bytes(r.stderr)
        return r
    build = run(cmd, 'build', 120)
    if build.returncode:
        raise ValueError('Component build failed; preserved logs')
    binary = o / 'obj/VStoreRob'
    normal = run([str(binary)], 'normal', 30)
    if normal.returncode:
        raise ValueError('Source differential failed; preserved logs')
    checks = json.loads(normal.stdout)
    mutants = []
    for label in ('full-admit', 'no-head-forward', 'writer-high-bit', 'drop-half'):
        r = run([str(binary), '--mutant', label], 'mutant-' + label, 30)
        if r.returncode == 0:
            raise ValueError('Accepted corrupted component ' + label)
        mutants.append({'label': label, 'rejected': True, 'exit_status': r.returncode,
                        'error': r.stderr.decode().strip()})
    paths = [Path(__file__), ROOT / 'timing/rvv_memory_fabric_boundary_v1.hpp',
             ROOT / 'timing/rvv_memory_fabric_boundary_v1_check.cpp', sv,
             ROOT / 'third_party/saturn/src/main/scala/common/ReorderBuffer.scala',
             ROOT / 'build/rvv-memory-fabric-source-plan-v1/report.json',
             ROOT / 'build/shuttle-memory-system-native-v6/build.json', a.verilator,
             a.verilator.with_name('verilator_bin'), a.verilator.with_name('perl')]
    report = {
        'schema': 'iris.rvv_memory_fabric_boundary_component.v1', 'pass': True,
        'checks': checks, 'corruptions': mutants, 'build_argv': cmd,
        'build_timeout_seconds': 120, 'per_execution_timeout_seconds': 30,
        'host_environment': {'PATH_prefix': str(a.verilator.parent), 'reason': 'Use the bound Conda Perl required by its Verilator wrapper'},
        'actual_reset': True, 'continuous_computed_state': True,
        'implementation': 'Exact configured16-entry ROB control; fail-closed metadata ownership and explicit clock conversion sidecars',
        'independent_oracle': 'Unchanged saved ReorderBuffer.sv, independently compiled with Verilator; metadata invariants separately checked',
        'qualified_RTL_output_fields': ['io_reserve_valid', 'io_reserve_bits', 'io_deq_valid'],
        'seeds': [1, 17, 31],
        'source_generated_RTL_sha256': sha(sv), 'compiled_reference_sha256': sha(binary),
        'scope_limits': ['No AddrGen/SIQ/SIFQ/VRF/VMU/TL-ready integration',
                         'No System v6 or native ELF execution claimed by this component',
                         'Source-ID mapping and clock units are bound by preceding source plan, not an RTL NoC oracle',
                         'Metadata generations do not drive source readiness or add target edges',
                         'No memory data publication or physical service latency supplied'],
        'timing_labels_consumed': False, 'hardware_contacted': False,
        'selected_or_frozen_parent_modified': False, 'full_memory_timing_qualified': False,
        'input_sha256': {str(p.resolve()): sha(p) for p in paths},
        'artifact_sha256': {str(p.relative_to(o)): sha(p) for p in o.rglob('*') if p.is_file()}}
    (o / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'RTL_edges': checks['RTL_edges'], 'checks': checks['checks'],
                      'corruptions': len(mutants), 'report_sha256': sha(o / 'report.json')}))


if __name__ == '__main__':
    main()
