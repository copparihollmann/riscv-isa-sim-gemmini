#!/usr/bin/env python3
"""Local-only prototype/admission and binary audit. Never invokes hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import batch_runner as batch
import memory_observation_postrun as post
import run_prepared

ROOT = Path(__file__).resolve().parents[1]
FS = Path('/scratch/eygao/iris-cy/sims/firesim')


def binary_audit():
    path = ROOT / 'firesim/artifacts/archived-build-driver-v1/FireSim-corigine_mimicturbo_gt'
    raw = path.read_bytes()
    post.need(hashlib.sha256(raw).hexdigest() == post.DRIVER_ELF_SHA, 'Exact archived8f ELF')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    post.need(h[0][:7] == b'\x7fELF\x02\x01\x01' and h[2] == 62, 'x86-64 little endian driver ELF')
    loads = []
    for i in range(h[10]):
        typ, flags, off, address, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', raw, h[5] + i * 56)
        if typ == 1: loads.append((address, off, size))
    def read(address, n):
        for base, off, size in loads:
            if base <= address and address + n <= base + size:
                return raw[off + address - base:off + address - base + n]
        raise ValueError('Driver bytes not file backed')
    cases = {
        'readable_writeLatency_name': (0x5acff, '48b877726974654c6174'),
        'readable_writeLatency_offset0': (0x5ada6, 'c785a0fcffff00000000'),
        'readable_readLatency_offset4': (0x5adcc, 'c785c8fcffff04000000'),
        'writable_writeLatency_name': (0x5b4ca, '48b877726974654c6174'),
        'writable_writeLatency_offset0': (0x5b55b, 'c785d0fbffff00000000'),
        'writable_readLatency_offset4': (0x5b581, 'c785f8fbffff04000000'),
        'master_INIT_DONE352_PRESENCE356': (0x7cff0, struct.pack('<QQ', 352, 356).hex()),
        'master_presence_write360': (0x5a781, '48c78590fcffff68010000'),
        'presence_magic_compare': (0x6b5e4, '81fb65726946')}
    checked = []
    for name, (address, expected) in cases.items():
        post.need(read(address, len(bytes.fromhex(expected))).hex() == expected, 'Compiled map changed ' + name)
        checked.append(dict(name=name, address=address, bytes=expected))
    functions = []
    for name, address, size in [('FASEDMemoryTimingModel::init', 0x618e0, 989),
                                ('FASEDMemoryTimingModel::finish', 0x61cc0, 2172),
                                ('simif_xilinx_alveo_u250_t::fpga_shutdown', 0x59060, 73)]:
        functions.append(dict(name=name, address=address, size=size, sha256=hashlib.sha256(read(address, size)).hexdigest()))
    return dict(driver_sha256=post.DRIVER_ELF_SHA, compiled_MMIO_checks=checked, function_ranges=functions,
                actual_device_read_performed=False,
                scope='Targeted archived-driver map and shutdown-byte identity; not complete source-to-bitstream attestation')


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); out = a.output.resolve()
    post.need(not out.exists(), 'New prototype directory required')
    out.mkdir(parents=True)
    audit = binary_audit()
    (out / 'binary-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    tests = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(ROOT / 'firesim/tests'),
                            '-p', 'test_memory_observation_postrun.py', '-v'], cwd=ROOT, capture_output=True, timeout=60)
    (out / 'tests.stdout').write_bytes(tests.stdout); (out / 'tests.stderr').write_bytes(tests.stderr)
    post.need(tests.returncode == 0, 'Mock safety/control tests failed')
    deploy = FS / 'deploy'; build = ROOT / 'build/rvv-compute-asm-v5'; job = out / 'job'
    cases = json.loads((build / 'host-cases.json').read_text())
    manager, m = batch.prepare(deploy, job, build / 'guest.elf', cases,
        deploy / 'config_runtime.yaml', deploy / 'config_hwdb.yaml',
        ROOT / 'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT / 'build/firesim-observability-archived-driver-v3/report.json')
    # Bind the unchanged standing receipt for local schema/closure checks only.
    # No freshness/idle inference is made, and the prototype is disabled below.
    auth = ROOT / 'build/user-launch-authorization-focused-continuation-v1/receipt.json'
    m.update(require_regions=True, require_goldens=True,
             launch_authorization_receipt=json.loads(auth.read_text()), prototype_only=True)
    m['input_sha256'][str(auth)] = post.digest(auth)
    batch.save_manifest(job, m)
    (out / 'before-install-manifest.json').write_bytes((job / 'run.json').read_bytes())
    installed = post.install(job, post.digest(job / 'run.json'), ROOT / 'build/fased-readonly-managed-v2',
                             'sohumpc', prototype_only=True)
    run_prepared.verify(job)  # Fresh immutable closure actually verifies locally.
    # Prevent accidental run_prepared execution of a mere integration prototype.
    m = json.loads((job / 'run.json').read_text())
    m['status'] = 'prototype_only_not_for_execution'
    m['prototype_hardware_admission'] = False
    batch.save_manifest(job, m)
    rejected = False
    try: run_prepared.verify(job)
    except ValueError: rejected = True
    post.need(rejected, 'Prototype must refuse managed hardware execution')
    (out / 'installation.json').write_text(json.dumps(installed, indent=2) + '\n')
    code = Path(__file__).resolve()
    inputs = [code, ROOT / 'firesim/memory_observation_postrun.py', ROOT / 'firesim/tests/test_memory_observation_postrun.py',
              ROOT / 'firesim/MEMORY_OBSERVATION_POSTRUN.md', ROOT / 'firesim/memory_observation.py',
              ROOT / 'firesim/readonly_fased_latency.c', ROOT / 'firesim/batch_runner.py',
              ROOT / 'firesim/run_prepared.py', ROOT / 'firesim/fased-read-source-evidence.json',
              ROOT / 'firesim/fased-read-evidence/FASEDMemoryTimingModel.scala',
              ROOT / 'firesim/fased-read-evidence/Widget.scala', ROOT / 'firesim/fased-read-evidence/Lib.scala',
              ROOT / 'firesim/fased-read-evidence/LatencyBandwidthPipe.scala',
              ROOT / 'firesim/fased-read-evidence/fased_memory_timing_model.cc',
              ROOT / 'firesim/fased-read-evidence/simif_corigine_mimicturbo_gt.cc',
              ROOT / 'firesim/fased-read-evidence/FireSim-generated.const.h',
              deploy / 'runtools/workload.py', deploy / 'runtools/firesim_topology_with_passes.py',
              deploy / 'runtools/run_farm_deploy_managers.py',
              FS / 'sim/midas/src/main/cc/core/simulation.cc',
              ROOT / 'firesim/artifacts/archived-build-driver-v1/FireSim-corigine_mimicturbo_gt']
    report = {'schema': 'iris.postdriver_fased_observer_local_qualification.v1', 'pass': True,
              'mocked_unit_tests': 10, 'actual_mock_device_or_SSH_access': False,
              'compiled_driver_MMIO_checks': len(audit['compiled_MMIO_checks']),
              'prototype_prepared_closure_verified': True, 'prototype_execution_refusal_verified': True,
              'prototype_job': str(job), 'prototype_final_manifest_sha256': post.digest(job / 'run.json'),
              'installation': installed, 'hardware_contacted': False, 'hardware_control_writes': False,
              'old_runner_observer_driver_package_modified': False,
              'ready_for_root_review': True, 'actual_postdriver_observation_performed': False,
              'new_managed_hardware_job_required': True, 'calibration_usable': False,
              'input_sha256': {str(p): post.digest(p) for p in inputs},
              'report_artifact_sha256': {str(p.relative_to(out)): post.digest(p) for p in out.iterdir() if p.is_file()}}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'report_sha256': post.digest(out / 'report.json'),
                      'prototype_execution_refused': True, 'hardware_contacted': False}))


if __name__ == '__main__':
    main()
