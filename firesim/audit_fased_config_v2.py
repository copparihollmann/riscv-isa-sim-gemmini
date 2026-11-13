#!/usr/bin/env python3
"""Exact archived8f readable/writable configuration-map audit; no device access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'firesim/artifacts/archived-build-driver-v1/FireSim-corigine_mimicturbo_gt'
DRIVER_SHA = '8f78167b754097623b031f41d7e5f121f4ae368f716255fdcf574693a071c48a'
REGISTERS = {'writeLatency': 0, 'readLatency': 4, 'writeMaxReqs': 8,
             'readMaxReqs': 12, 'relaxFunctionalModel': 72}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def audit():
    raw = DRIVER.read_bytes()
    if sha(DRIVER) != DRIVER_SHA: raise ValueError('Exact original8f driver required')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    if h[0][:7] != b'\x7fELF\x02\x01\x01' or h[2] != 62: raise ValueError('x86-64 ELF required')
    loads = []
    for i in range(h[10]):
        t, _, o, v, _, n, _, _ = struct.unpack_from('<IIQQQQQQ', raw, h[5] + 56*i)
        if t == 1: loads.append((v, o, n))
    def read(a, n):
        for b, o, s in loads:
            if b <= a and a+n <= b+s: return raw[o+a-b:o+a-b+n]
        raise ValueError('Compiled proof not file backed')
    checks = {
        'readable_writeLatency_name': (0x5acff, '48b877726974654c6174'),
        'readable_writeLatency_offset0': (0x5ada6, 'c785a0fcffff00000000'),
        'readable_readLatency_offset4': (0x5adcc, 'c785c8fcffff04000000'),
        'writable_writeLatency_name': (0x5b4ca, '48b877726974654c6174'),
        'writable_writeLatency_offset0': (0x5b55b, 'c785d0fbffff00000000'),
        'writable_readLatency_offset4': (0x5b581, 'c785f8fbffff04000000'),
        'readable_writeMaxReqs_name_prefix': (0x5ad3d, '48b877726974654d6178'),
        'readable_readMaxReqs_name_prefix': (0x5ad5c, '48b8726561644d617852'),
        'readable_writeMaxReqs_name_suffix': (0x5add6, 'c785e8fcffff52657173'),
        'readable_writeMaxReqs_offset8': (0x5adf2, 'c785f0fcffff08000000'),
        'readable_readMaxReqs_name_suffix': (0x5adfc, 'c7850ffdffff52657173'),
        'readable_readMaxReqs_offset12': (0x5ae18, 'c78518fdffff0c000000'),
        'writable_writeMaxReqs_name_prefix': (0x5b508, '48b877726974654d6178'),
        'writable_readMaxReqs_name_prefix': (0x5b527, '48b8726561644d617852'),
        'writable_writeMaxReqs_name_suffix': (0x5b58b, 'c78518fcffff52657173'),
        'writable_writeMaxReqs_offset8': (0x5b5a7, 'c78520fcffff08000000'),
        'writable_readMaxReqs_name_suffix': (0x5b5b1, 'c7853ffcffff52657173'),
        'writable_readMaxReqs_offset12': (0x5b5cd, 'c78548fcffff0c000000'),
        'relaxFunctionalModel_rodata_prefix': (0x7d180, b'relaxFunctionalM'.hex()),
        'readable_relaxFunctionalModel_name_suffix': (0x5b2e8, 'c740106f64656c'),
        'readable_relaxFunctionalModel_offset72': (0x5b339, 'c78570ffffff48000000'),
        'writable_relaxFunctionalModel_name_suffix': (0x5b5f4, 'c740106f64656c'),
        'writable_relaxFunctionalModel_offset72': (0x5b61f, 'c78570fcffff48000000'),
        'master_INIT352_presence356': (0x7cff0, struct.pack('<QQ', 352, 356).hex()),
        'presence_magic': (0x6b5e4, '81fb65726946')}
    out = []
    for name, (a, expected) in checks.items():
        if read(a, len(bytes.fromhex(expected))).hex() != expected: raise ValueError('Compiled map changed: '+name)
        out.append(dict(name=name, address=a, bytes=expected))
    source = ROOT / 'firesim/fased-read-evidence'
    header = (source / 'FireSim-generated.const.h').read_text()
    for name, offset in REGISTERS.items():
        token = '{ R"ESC(' + name + ')ESC", ' + str(offset) + ' }'
        if header.count(token) != 2: raise ValueError('Both generated R/W maps required: '+name)
    # These are plain RegisterEntry mappings, not decoupled read-to-clear FIFOs.
    widget = (source / 'Widget.scala').read_text(); lib = (source / 'Lib.scala').read_text()
    for phrase in ['case ActualDirection.Input  =>', 'genAndAttachReg(b, name, getInitValue(b, parent), substruct = false)',
                   'attach(reg, name, substruct = substruct)']:
        if phrase not in widget: raise ValueError('Configuration-register attachment changed')
    for phrase in ['when(write(index).valid)', 'reg.node := write(index).bits', 'read(index).bits := reg.node']:
        if phrase not in lib: raise ValueError('Plain non-clearing register read semantics changed')
    paths = [Path(__file__), DRIVER, source/'FireSim-generated.const.h', source/'Widget.scala', source/'Lib.scala',
             source/'FASEDMemoryTimingModel.scala', source/'LatencyBandwidthPipe.scala',
             source/'fased_memory_timing_model.cc', source/'simif_corigine_mimicturbo_gt.cc',
             ROOT/'build/firesim-observability-archived-driver-v3/report.json']
    return {'schema': 'iris.archived_fased_configuration_MMIO_audit.v2', 'pass': True,
            'driver_binary_sha256': DRIVER_SHA, 'registers_readable': REGISTERS, 'registers_writable': REGISTERS,
            'compiled_binary_checks': out, 'presence_byte_offset': 356, 'presence_magic': 0x46697265,
            'read_side_effects': 'Plain RegisterEntry read exposes node; node assignment is write.valid only',
            'relax_register_domain': 'Bool exposed through32-bit MMIO; only integer0/1 admitted',
            'source_default_values_used_as_observations': False, 'hardware_contacted': False,
            'full_source_image_association_verified': False, 'calibration_usable': False,
            'input_sha256': {str(p): sha(p) for p in paths}}


def main():
    p = argparse.ArgumentParser(__doc__); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise ValueError('Fresh audit output required')
    report = audit(); a.output.mkdir(parents=True)
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(pass_=True, binary_checks=len(report['compiled_binary_checks']), report_sha256=sha(a.output/'report.json'))))


if __name__ == '__main__': main()
