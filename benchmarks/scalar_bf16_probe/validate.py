"""Independent trap/state/ELF validation; no trust in guest pass booleans."""
import hashlib
import json
from pathlib import Path
import struct

from cases import FFLAGS, SENTINEL, SPLIT, checksum, corpus


def instruction_at(elf, pc):
    if elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', elf, 18)[0] != 243:
        raise ValueError('Little-endian RV64 ELF required')
    phoff = struct.unpack_from('<Q', elf, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', elf, 54)
    matches = []
    for i in range(phnum):
        kind, flags, offset, address, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', elf, phoff+i*phsize)
        if kind == 1 and flags & 1 and address <= pc and pc+4 <= address+size:
            matches.append(struct.unpack_from('<I', elf, offset+pc-address)[0])
    if len(matches) != 1:
        raise ValueError('Trap PC must name one actual executable ELF word')
    return matches[0]


def validate(text, supplied_corpus, elf_path):
    if supplied_corpus != corpus() or supplied_corpus['split_id'] != SPLIT:
        raise ValueError('Frozen independently generated BF16 corpus required')
    elf = Path(elf_path).read_bytes()
    regions, begins, done = [], [], []
    for line in text.splitlines():
        if line.startswith(('IRIS_FATAL ', 'IRIS_PROBE_TIMEOUT ')):
            raise ValueError('Fatal or incomplete guest probe')
        for prefix, target in [('IRIS_REGION ', regions), ('IRIS_PROBE_BEGIN ', begins), ('IRIS_BATCH_DONE ', done)]:
            if line.startswith(prefix):
                target.append(json.loads(line[len(prefix):]))
    expected = [(case, hart) for case in supplied_corpus['cases'] for hart in range(3)]
    if len(regions) != len(expected) or len(begins) != len(expected) or done != [{'failed': 0, 'regions': len(expected)}]:
        raise ValueError('Exact complete region/begin/completion coverage required')
    harts = [0, 0, 0]
    word_pcs = set()
    for row, begin, (case, hart) in zip(regions, begins, expected):
        if any(type(row.get(key)) is not int for key in (
                'hart', 'trial_id', 'instruction', 'operand_bits', 'start_cycle', 'end_cycle',
                'instret_delta', 'illegal_delta', 'trap_cause', 'trap_pc', 'trap_value',
                'pc_match', 'destination_bits', 'fcsr', 'checksum', 'expected_checksum')):
            raise ValueError('Exact integer observation fields required')
        if begin != {'case_id': case['case_id'], 'hart': hart}:
            raise ValueError('Probe identity/order mismatch')
        identity = {'case_id': case['case_id'], 'parent_case_id': case['parent_case_id'],
                    'suite': 'scalar_bf16_decode', 'region': 'kernel', 'hart': hart,
                    'trial_id': case['trial_id'], 'instruction': case['instruction'],
                    'operand_bits': case['operand_bits']}
        if any(row.get(k) != v for k, v in identity.items()):
            raise ValueError('Observed corpus/encoding/hart mismatch')
        if row['trap_cause'] != 2 or row['illegal_delta'] != 1 or row['pc_match'] != 1:
            raise ValueError('Missing or imprecise illegal-instruction trap')
        if row['destination_bits'] != SENTINEL or row['fcsr'] != FFLAGS:
            raise ValueError('Illegal instruction changed destination or floating-point flags')
        if instruction_at(elf, row['trap_pc']) != case['instruction']:
            raise ValueError('Trap PC disagrees with actual ELF instruction')
        if not 0 <= row['start_cycle'] < row['end_cycle'] < 2**64 or not 0 < row['instret_delta'] < 2**64:
            raise ValueError('Invalid observed counter region')
        if not 0 <= row['trap_value'] < 2**64:
            raise ValueError('Invalid trap-value observation')
        expected_hash = checksum([1, SENTINEL, FFLAGS, 2, 1])
        if row['checksum'] != expected_hash or row['expected_checksum'] != expected_hash or row.get('pass') is not True:
            raise ValueError('Independent checksum mismatch')
        harts[hart] += 1
        word_pcs.add((case['instruction'], row['trap_pc']))
    return {'regions': len(regions), 'per_hart': harts, 'trials': 5,
            'distinct_encoding_PC_pairs': len(word_pcs), 'all_source_expected_illegal': True,
            'destination_and_flags_preserved': True,
            'trap_value_policy': 'Raw observation retained; no source/image assumption for mtval payload.',
            'elf_sha256': hashlib.sha256(elf).hexdigest(), 'calibration_usable': False}
