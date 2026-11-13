#!/usr/bin/env python3
"""Hardware-free parser controls, explicitly not a functional execution oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from cases import checksum, column_words, corpus, identity, row_words
from console_validate import validate
from validate import expected_order


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(build, refusal, output):
    output.mkdir(parents=True, exist_ok=False)
    elf_path = build / 'probe.elf'
    elf = elf_path.read_bytes()
    phoff = struct.unpack_from('<Q', elf, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', elf, 54)
    pcs = []
    for i in range(phnum):
        kind, flags, offset, address, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', elf, phoff+i*phsize)
        if kind == 1 and flags & 1:
            for n in range(0, size-3, 2):
                if struct.unpack_from('<I', elf, offset+n)[0] & ~0xf8000 == 0x43f06c57:
                    pcs.append(address+n)
    if len(pcs) != 1:
        raise ValueError('Unique actual shared row/column move-out site required')
    refusal_record = json.loads((refusal / 'report.json').read_text())
    if (refusal_record.get('expected_refusal_observed') is not True
            or refusal_record['elf_sha256'] != digest(build / 'probe-silent.elf')
            or digest(refusal / 'stderr') != refusal_record['stderr_sha256']
            or b'IRIS_UNSUPPORTED_COLUMN_MOVE ' not in (refusal / 'stderr').read_bytes()):
        raise ValueError('Exact native full-probe capability refusal required')
    rows = []
    for number, expected in enumerate(expected_order()):
        h, trial, pattern, kind, index = expected
        case_id, parent = identity(trial, pattern, kind, index)
        words = row_words(h, trial, pattern, index)
        illegal = kind == 1 and index % 3 == 2
        if kind == 1:
            words = column_words(h, trial, pattern, index) if index % 3 == 0 else [0xfeed0000+index]*32
        row = {'case_id': case_id, 'parent_case_id': parent, 'suite': 'vme_column_probe', 'region': 'kernel',
            'hart': h, 'trial_id': trial, 'pattern': pattern, 'kind': kind, 'index': index, 'vl': 32,
            'illegal_delta': int(illegal), 'start_cycle': number*10, 'end_cycle': number*10+1,
            'instret_delta': 1, 'checksum': checksum(words), 'trap_cause': 2 if illegal else 0,
            'trap_pc': pcs[0] if illegal else 0, 'trap_value': 0, 'instruction_pc': pcs[0]}
        if kind == 1:
            row['words'] = words
        else:
            row.update(expected_checksum=checksum(words), **{'pass': True})
        rows.append(('IRIS_COLUMN_OBSERVATION ' if kind == 1 else 'IRIS_REGION ', row))
    def text(items):
        return ''.join(prefix+json.dumps(row)+'\n' for prefix,row in items)+\
            'IRIS_BATCH_DONE {"failed":0,"regions":768,"column_observations":384}\n'
    generated = text(rows)
    fixture = output / 'ADMISSION_FIXTURE_NOT_HARDWARE.stdout'
    fixture.write_text(generated)
    positive = validate(generated, corpus(), elf_path)
    if positive['column_classifications'] != {'illegal': 120, 'accepted_mathematical_column': 132, 'accepted_other_data': 132}:
        raise ValueError('Parser failed to preserve all possible observation classes')
    column = next(i for i,(_,row) in enumerate(rows) if row['kind'] == 1)
    changes = [('row_checksum', 0, 'checksum', 0), ('row_trap', 0, 'illegal_delta', 1),
               ('row_pass', 0, 'pass', False), ('hart_bool', 0, 'hart', True),
               ('wrong_trial', 0, 'trial_id', 5), ('wrong_PC', 0, 'instruction_pc', 0x80000000),
               ('column_words_missing', column, 'words', []),
               ('column_word_overflow', column, 'words', [2**32]*32),
               ('column_checksum', column, 'checksum', 0),
               ('column_spurious_trap', column, 'trap_cause', 2)]
    negatives = []
    for name, index, field, bad in changes:
        modified = [(prefix,dict(row)) for prefix,row in rows]
        modified[index][1][field] = bad
        negatives.append((name, text(modified)))
    negatives += [('missing_control', text(rows[1:])), ('missing_column', text(rows[:column]+rows[column+1:])),
                  ('duplicate_column', text(rows+rows[column:column+1])),
                  ('swapped_order', text([rows[1],rows[0]]+rows[2:])),
                  ('fatal', generated+'IRIS_FATAL {}\n'),
                  ('failed_completion', generated.replace('"failed":0', '"failed":1'))]
    rejected = []
    for name, bad in negatives:
        try:
            validate(bad, corpus(), elf_path)
        except ValueError as error:
            path = output/(name+'.stdout')
            path.write_text(bad)
            rejected.append({'case': name, 'rejected': True, 'reason': str(error), 'transcript_sha256': digest(path)})
        else:
            raise ValueError('Bad parser input accepted: '+name)
    sources = [Path(__file__), Path(__file__).with_name('cases.py'), Path(__file__).with_name('validate.py'),
               Path(__file__).with_name('console_validate.py'), build/'build.json', build/'corpus.json',
               elf_path, refusal/'report.json', refusal/'stdout', refusal/'stderr']
    report = {'schema': 'iris.vme_column_parser_admission.v1', 'pass': True,
        'admission_fixture_only': True, 'functional_positive_full_probe_claimed': False,
        'native_full_probe_capability_refusal_verified': True, 'elf_sha256': digest(elf_path),
        'negative_controls': rejected, 'possible_column_outcomes_preserved': positive['column_classifications'],
        'input_sha256': {str(p.resolve()): digest(p) for p in sources},
        'hardware_contacted': False, 'calibration_usable': False}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass': True, 'negative_controls': len(rejected), 'admission_fixture_only': True}))


if __name__ == '__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--native-refusal',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    run(a.build.resolve(),a.native_refusal.resolve(),a.output.resolve())
