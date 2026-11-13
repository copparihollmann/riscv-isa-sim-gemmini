"""Check known row hashes and raw column observations in managed console bytes."""
import json
from pathlib import Path

from cases import checksum, corpus, identity, row_words
from validate import expected_order, validate_record


def validate(text, supplied_corpus, elf_path):
    if supplied_corpus != corpus():
        raise ValueError('Exact independently generated column observation corpus required')
    records, done = [], []
    for line in text.splitlines():
        if line.startswith(('IRIS_FATAL ', 'IRIS_PROBE_TIMEOUT ')):
            raise ValueError('Fatal/incomplete guest')
        if line.startswith('IRIS_REGION '):
            records.append((False, json.loads(line.split(' ', 1)[1])))
        elif line.startswith('IRIS_COLUMN_OBSERVATION '):
            records.append((True, json.loads(line.split(' ', 1)[1])))
        elif line.startswith('IRIS_BATCH_DONE '):
            done.append(json.loads(line.split(' ', 1)[1]))
    if len(records) != 1152 or done != [{'failed': 0, 'regions': 768, 'column_observations': 384}]:
        raise ValueError('Exact complete controls/observations/completion required')
    elf = Path(elf_path).read_bytes()
    result = []
    for (is_column, row), expected in zip(records, expected_order()):
        h, trial, pattern, kind, index = expected
        case_id, parent = identity(trial, pattern, kind, index)
        if (is_column != (kind == 1) or row.get('case_id') != case_id
                or row.get('parent_case_id') != parent or row.get('suite') != 'vme_column_probe'
                or row.get('region') != 'kernel'):
            raise ValueError('Unexpected observed case/kind/order')
        fields = ['hart', 'trial_id', 'pattern', 'kind', 'index', 'vl', 'illegal_delta',
                  'start_cycle', 'end_cycle', 'instret_delta', 'checksum', 'trap_cause',
                  'trap_pc', 'trap_value', 'instruction_pc']
        if any(type(row.get(name)) is not int or not 0 <= row[name] < 2**64 for name in fields):
            raise ValueError('Exact unsigned observation fields required')
        meta = [0x49524953434f4c31] + [row[name] for name in fields]
        if is_column:
            words = row.get('words')
            if not isinstance(words, list) or len(words) != 32 or any(type(w) is not int or not 0 <= w < 2**32 for w in words):
                raise ValueError('All raw column words required')
        else:
            words = row_words(h, trial, pattern, index)
            if row.get('expected_checksum') != checksum(words) or row.get('pass') is not True:
                raise ValueError('Required row control checksum mismatch')
        qualified = validate_record(meta, words, expected, elf)
        qualified['row_words_observed_individually'] = False if not is_column else None
        result.append(qualified)
    return {'schema': 'iris.vme_column_console_analysis.v1', 'row_controls_passed': 768,
        'row_evidence': 'Independent full-row FNV64 checksums; console does not print individual row words.',
        'column_observations': 384, 'frames': result,
        'column_classifications': {name: sum(r.get('outcome') == name for r in result)
            for name in ('illegal', 'accepted_mathematical_column', 'accepted_other_data')},
        'mathematical_column_is_classification_reference_only': True,
        'full_functional_certified': False, 'timing_certified': False, 'calibration_usable': False}
