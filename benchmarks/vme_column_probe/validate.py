"""Validate known rows and classify raw column results without inventing semantics."""
import hashlib
import struct
from pathlib import Path

from cases import checksum, column_words, identity, row_words

SIGNATURE_BYTES = 295040
RECORD_BYTES = 256


def instruction_at(elf, pc):
    if elf[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Little-endian ELF64 required')
    offset = struct.unpack_from('<Q', elf, 32)[0]
    size, count = struct.unpack_from('<HH', elf, 54)
    words = []
    for i in range(count):
        kind, flags, file_offset, address, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', elf, offset+i*size)
        if kind == 1 and flags & 1 and address <= pc and pc+4 <= address+length:
            words.append(struct.unpack_from('<I', elf, file_offset+pc-address)[0])
    if len(words) != 1:
        raise ValueError('Instruction PC is outside one executable ELF segment')
    return words[0]


def validate_record(meta, words, expected, elf):
    hart, trial, pattern, kind, index = expected
    if meta[:6] != [0x49524953434f4c31, hart, trial, pattern, kind, index] or meta[6] != 32:
        raise ValueError('Record identity/geometry mismatch')
    if not 0 <= meta[8] < meta[9] < 2**64 or not 0 < meta[10] < 2**64:
        raise ValueError('Invalid source cycle/retirement observation')
    if checksum(words) != meta[11]:
        raise ValueError('Raw word checksum mismatch')
    instruction = instruction_at(elf, meta[15])
    if instruction & ~0xf8000 != 0x43f06c57:
        raise ValueError('Record PC does not name the actual tile move-out encoding')
    if meta[7] == 0:
        if meta[12:15] != [0, 0, 0]:
            raise ValueError('Unexpected trap metadata on a nontrapping observation')
    elif meta[7] == 1 and kind == 1:
        if meta[12] != 2 or meta[13] != meta[15]:
            raise ValueError('Column trap does not identify the probed instruction')
    else:
        raise ValueError('Unexpected trap on a required row control')
    case_id, parent = identity(trial, pattern, kind, index)
    row = {'case_id': case_id, 'parent_case_id': parent, 'hart': hart, 'trial_id': trial,
           'pattern': pattern, 'kind': kind, 'index': index, 'vl': meta[6],
           'illegal_delta': meta[7], 'start_cycle': meta[8], 'end_cycle': meta[9],
           'instret_delta': meta[10], 'checksum': meta[11], 'trap_cause': meta[12],
           'trap_pc': meta[13], 'trap_value': meta[14], 'instruction_pc': meta[15], 'words': words}
    if kind != 1:
        if words != row_words(hart, trial, pattern, index):
            raise ValueError('Independently initialized tile row mismatch')
    else:
        mathematical = column_words(hart, trial, pattern, index)
        row['mathematical_column_checksum'] = checksum(mathematical)
        row['mathematical_column_mismatching_words'] = sum(a != b for a,b in zip(words, mathematical))
        row['outcome'] = ('illegal' if meta[7] else 'accepted_mathematical_column'
                          if words == mathematical else 'accepted_other_data')
    return row


def expected_order():
    for hart in range(2):
        for trial in range(3):
            for pattern in range(2):
                for row in range(32):
                    yield hart, trial, pattern, 0, row
                for col in range(32):
                    yield hart, trial, pattern, 1, col
                    yield hart, trial, pattern, 2, col


def signature(path, elf_path):
    lines = Path(path).read_text().splitlines()
    if len(lines) != SIGNATURE_BYTES // 8 or any(len(line) != 16 for line in lines):
        raise ValueError('Exact complete signature length required')
    try:
        data = b''.join(struct.pack('<Q', int(line, 16)) for line in lines)
    except (ValueError, struct.error) as error:
        raise ValueError('Invalid signature word') from error
    header = list(struct.unpack_from('<16Q', data))
    if (header[:4] != [0x49524953434f4c30, 1, 576, 256] or header[4:7] != [1,1,1]
            or header[7:10] != [32,32,32] or header[10:12] != [0,0] or header[12:14] != [576,576]
            or header[14:] != [0,0]):
        raise ValueError('Incomplete/malformed all-hart signature header')
    elf = Path(elf_path).read_bytes()
    rows = []
    for i, expected in enumerate(expected_order()):
        offset = 128 + i*RECORD_BYTES
        meta = list(struct.unpack_from('<16Q', data, offset))
        words = list(struct.unpack_from('<32I', data, offset+128))
        rows.append(validate_record(meta, words, expected, elf))
    classifications = {name: sum(r.get('outcome') == name for r in rows)
                       for name in ('illegal', 'accepted_mathematical_column', 'accepted_other_data')}
    return {'schema': 'iris.vme_column_signature_analysis.v1', 'row_controls_passed': 768,
            'column_observations': 384, 'column_classifications': classifications,
            'frames': rows, 'signature_sha256': hashlib.sha256(data).hexdigest(),
            'mathematical_column_is_classification_reference_only': True,
            'full_functional_certified': False, 'timing_certified': False, 'calibration_usable': False}
