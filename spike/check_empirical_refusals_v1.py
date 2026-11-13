#!/usr/bin/env python3
"""Independent metadata/ELF corruption controls; never executes a guest."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def elf(symbols=((1, 0x80000004, 2),), etype=2, version=1, ehsize=64):
    blob = bytearray(0x200 + 5 * 64)
    ident = b'\x7fELF\x02\x01\x01' + b'\x00' * 9
    struct.pack_into('<16sHHIQQQIHHHHHH', blob, 0, ident, etype, 243, version, 0x80000000, 64, 0x200, 0, ehsize, 56, 1, 64, 5, 4)
    struct.pack_into('<IIQQQQQQ', blob, 64, 1, 5, 0x100, 0x80000000, 0x80000000, 8, 8, 0x1000)
    blob[0x100:0x108] = b'\x13\0\0\0' * 2
    names = b'\0.text\0.strtab\0.symtab\0.shstrtab\0'
    strings = b'\0z_fatal_error\0'
    blob[0x120:0x120 + len(names)] = names
    blob[0x160:0x160 + len(strings)] = strings
    for i, (index, value, typ) in enumerate(symbols, 1):
        struct.pack_into('<IBBHQQ', blob, 0x180 + i * 24, 1, 0x10 | typ, 0, index, value, 0)
    sections = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                (1, 1, 6, 0x80000000, 0x100, 8, 0, 0, 4, 0),
                (7, 3, 0, 0, 0x160, len(strings), 0, 0, 1, 0),
                (15, 2, 0, 0, 0x180, (len(symbols) + 1) * 24, 2, 1, 8, 24),
                (23, 3, 0, 0, 0x120, len(names), 0, 0, 1, 0)]
    for i, values in enumerate(sections):
        struct.pack_into('<IIQQQQIIQQ', blob, 0x200 + i * 64, *values)
    return bytes(blob)


def main(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    provider = module('empirical_provider_audit', args.provider)
    launcher = module('empirical_launcher_audit', args.launcher)
    records = []
    cases = [('reserved_absolute_symbol', elf(((0xfff1, 0x80000004, 2),))),
             ('out_of_range_section_index', elf(((9, 0x80000004, 2),))),
             ('nonexecutable_symbol_section', elf(((2, 0x80000004, 2),))),
             ('symbol_outside_text', elf(((1, 0x80004000, 2),))),
             ('ambiguous_duplicate_fatal_name', elf(((1, 0x80000000, 2), (1, 0x80000004, 2)))),
             ('relocatable_not_executable', elf(etype=1)),
             ('invalid_ELF_version', elf(version=0)), ('invalid_ELF_header_size', elf(ehsize=0))]
    valid = out / 'valid.elf'
    valid.write_bytes(elf())
    if launcher.fatal_addresses(valid) != {'z_fatal_error': 0x80000004}:
        raise ValueError('Independent valid ELF fixture did not decode')
    for name, data in cases:
        path = out / (name + '.elf')
        path.write_bytes(data)
        try:
            accepted = launcher.fatal_addresses(path)
        except (ValueError, UnicodeError, struct.error):
            records.append({'name': name, 'expected_refusal': True, 'refused': True})
        else:
            records.append({'name': name, 'expected_refusal': True, 'refused': False, 'accepted_mapping': accepted})
    for name, data in [('null_manifest', None), ('list_manifest', []),
                       ('list_input_map', {'schema': 'iris.empirical_simulator.v1', 'mode': 'experimental_fpga_empirical',
                                           'runtime_environment': {k: os.environ.get(k) for k in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT')}, 'input_sha256': []})]:
        path = out / (name + '.json')
        path.write_text(json.dumps(data))
        try:
            result = provider.experimental_empirical_simulator(path)
        except Exception as error:
            records.append({'name': name, 'expected_refusal': True, 'refused': False,
                            'exception_escaped': type(error).__name__, 'message': str(error)})
        else:
            records.append({'name': name, 'expected_refusal': True, 'refused': result.get('available') is False})
    baseline = json.loads(args.manifest.read_text())
    if provider.experimental_empirical_simulator(args.manifest).get('available') is not True:
        raise ValueError('Valid published package baseline unavailable')
    for name in ('boolean_matrix_harts', 'float_device_ABI', 'boolean_fatal_receipt_harts'):
        changed = copy.deepcopy(baseline)
        if name == 'boolean_matrix_harts':
            changed['matrix_hart_ids'] = [False, True]
        elif name == 'float_device_ABI':
            changed['native_device_abi'] = 4.0
        else:
            info = changed['native_launcher']
            original = Path(info['selftest'])
            receipt = json.loads(original.read_text())
            receipt['fatal_harts_verified'] = [False, True, 2]
            path = out / 'changed-launcher-selftest.json'
            path.write_text(json.dumps(receipt))
            info['selftest'] = str(path)
            info['selftest_sha256'] = sha(path)
            changed['input_sha256'][str(path)] = sha(path)
        path = out / (name + '.json')
        path.write_text(json.dumps(changed))
        try:
            result = provider.experimental_empirical_simulator(path)
        except Exception as error:
            records.append({'name': name, 'expected_refusal': True, 'refused': False, 'exception_escaped': type(error).__name__})
        else:
            records.append({'name': name, 'expected_refusal': True, 'refused': result.get('available') is False})
    report = {'schema': 'iris.empirical_package_refusal_audit.v1',
              'status': 'all_refused' if all(r['refused'] for r in records) else 'meaningful_gaps_observed',
              'valid_synthetic_ELF_and_published_package_passed': True, 'controls': records,
              'all_expected_refusals_passed': all(r['refused'] for r in records),
              'guest_executed': False, 'hardware_contacted': False, 'model_fit_or_holdout_analysis_performed': False,
              'input_sha256': {str(p.resolve()): sha(p) for p in (Path(__file__), args.provider, args.launcher, args.manifest)}}
    (out / 'audit-source.py').write_bytes(Path(__file__).read_bytes())
    (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': report['status'], 'gaps': [r['name'] for r in records if not r['refused']], 'report_sha256': sha(out / 'report.json')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
