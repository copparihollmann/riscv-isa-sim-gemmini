"""Independent synthetic ELF corruption controls for the executable-symbol parser."""
import hashlib
import json
from pathlib import Path
import struct

from spike.empirical_launch_v2 import fatal_addresses
from spike.check_empirical_refusals_v1 import elf


def check_parser(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    def changed(data, offset, fmt, value):
        result = bytearray(data)
        struct.pack_into(fmt, result, offset, value)
        return bytes(result)
    cases = {
        'reserved_absolute_symbol': elf(((0xfff1, 0x80000004, 2),)),
        'out_of_range_section_index': elf(((9, 0x80000004, 2),)),
        'nonexecutable_symbol_section': elf(((2, 0x80000004, 2),)),
        'symbol_outside_text': elf(((1, 0x80004000, 2),)),
        'ambiguous_duplicate_name': elf(((1, 0x80000000, 2), (1, 0x80000004, 2))),
        'relocatable_ELF': elf(etype=1),
        'invalid_ELF_version': elf(version=0),
        'invalid_ELF_header_size': elf(ehsize=0),
        'odd_instruction_address': elf(((1, 0x80000003, 2),)),
        'object_fatal_symbol': elf(((1, 0x80000004, 1),)),
        'nonexecutable_load': changed(elf(), 68, '<I', 4),
        'symbol_extends_past_code': changed(elf(), 0x180 + 24 + 16, '<Q', 8),
        'mismatched_section_file_mapping': changed(elf(), 0x200 + 64 + 24, '<Q', 0x80000002),
        'truncated_section_table': elf()[:-1],
        'invalid_symbol_table_stride': changed(elf(), 0x200 + 3 * 64 + 56, '<Q', 0),
        'dynamic_interpreter': changed(elf(), 64, '<I', 3),
    }
    records = []
    positives = {
        'valid': (elf(), {'z_fatal_error': 0x80000004}),
        'same_address_duplicate': (elf(((1, 0x80000004, 2), (1, 0x80000004, 2))), {'z_fatal_error': 0x80000004}),
        'undefined_symbol_ignored': (elf(((0, 0x80000004, 2),)), {}),
    }
    for name, (data, expected) in positives.items():
        path = output / (name + '.elf'); path.write_bytes(data)
        actual = fatal_addresses(path)
        if actual != expected: raise ValueError('Valid synthetic ELF refused: ' + name)
        records.append({'name': name, 'expected_refusal': False, 'pass': True})
    for name, data in cases.items():
        path = output / (name + '.elf'); path.write_bytes(data)
        try: fatal_addresses(path)
        except (ValueError, UnicodeError, struct.error): pass
        else: raise ValueError('Malformed ELF accepted: ' + name)
        records.append({'name': name, 'expected_refusal': True, 'pass': True})
    report = {'schema': 'iris.empirical_fatal_parser_controls.v2', 'pass': True,
              'controls': records, 'negative_controls': len(cases), 'guest_executed': False,
              'input_sha256': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  (Path(__file__), Path(__file__).with_name('empirical_launch_v2.py'),
                   Path(__file__).with_name('check_empirical_refusals_v1.py'))}}
    (output / 'parser-report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
