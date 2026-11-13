"""Known row controls and explicitly observational column encodings."""
import struct

SPLIT = 'iris-vme-column-observation-fit-v1'


def base(hart, trial, pattern):
    return 0x12000000 + (hart << 20) + (pattern << 16) + (trial << 12)


def row_words(hart, trial, pattern, index):
    return [base(hart, trial, pattern) + (index << 6) + c for c in range(32)]


def column_words(hart, trial, pattern, index):
    return [base(hart, trial, pattern) + (r << 6) + index for r in range(32)]


def checksum(words):
    value = 14695981039346656037
    for byte in struct.pack('<32I', *words):
        value = ((value ^ byte) * 1099511628211) & ((1 << 64)-1)
    return value


def identity(trial, pattern, kind, index):
    name = ['pre-row', 'column-observation', 'post-row'][kind]
    parent = f'vme.column.{name}.pattern{pattern}.index{index}'
    return parent + f'.trial{trial}', parent


def corpus():
    controls, observations = [], []
    for trial in range(3):
        for pattern in range(2):
            for kind in (0, 1, 2):
                for index in range(32):
                    case_id, parent = identity(trial, pattern, kind, index)
                    row = {'case_id': case_id, 'parent_case_id': parent, 'trial_id': trial,
                           'pattern': pattern, 'kind': kind, 'index': index, 'active_harts': [0, 1]}
                    if kind == 1:
                        row['expected_architectural_column_checksums'] = {
                            str(h): checksum(column_words(h, trial, pattern, index)) for h in (0, 1)}
                        row['source_or_hardware_outcome_assumed'] = False
                        observations.append(row)
                    else:
                        row['expected_checksums'] = {str(h): checksum(row_words(h, trial, pattern, index)) for h in (0, 1)}
                        controls.append(row)
    return {'schema': 'iris.vme_column_observation_corpus.v1', 'split_id': SPLIT,
            'trials': 3, 'harts_online': [0, 1, 2], 'active_harts': [0, 1],
            'cases': controls, 'observations': observations, 'regions': 768,
            'column_observations': 384, 'idle_policy': 'Both compute harts collect concurrently; hart2 boots, joins barriers, then parks.',
            'expected_column_policy': 'Mathematical transpose is a classification reference, never an asserted source/hardware golden.',
            'all_tile_cells_initialized_explicitly': True,
            'collection_before_console_output': True, 'calibration_usable': False}
