"""Fitting-only page-boundary controls; full four-group LMUL8 context copies."""
SPLIT = 'iris-rvv-page-transport-fit-v1'


def checksum(pattern):
    result = 14695981039346656037
    for group in range(4):
        for index in range(256):
            byte = (index * 17 + group * 61 + 13) & 255 if pattern else 0
            result = ((result ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return result


def cases():
    rows = []
    for mode in (2, 0, 1):
        for family in ('contained', 'load', 'store', 'both'):
            variants = [(4, 0)] if family == 'contained' else [(group, beats * 32) for group in range(4) for beats in range(1, 8)]
            for group, before in variants:
                shifted = 4096 - group * 256 - before if family != 'contained' else 256
                input_offset = shifted if family in ('load', 'both') else 256
                output_offset = shifted if family in ('store', 'both') else 256
                for pattern in (0, 1):
                    parent = 'rvv.page.hart2.%s.g%d.before%d.mode%d.pattern%d' % (family, group, before, mode, pattern)
                    for trial in range(5):
                        rows.append({'case_id': parent + '.trial.' + str(trial), 'parent_case_id': parent,
                            'trial_id': trial, 'suite': 'rvv_page_transport', 'mask': 4, 'region': 'kernel',
                            'family': family, 'crossing_group': group, 'bytes_before_page': before,
                            'input_offset': input_offset, 'output_offset': output_offset,
                            'mode': mode, 'pattern': pattern, 'expected_checksums': [0, 0, checksum(pattern)]})
    return {'schema': 'iris.rvv_page_transport_corpus.v1', 'split_id': SPLIT, 'trials': 5,
            'cases': rows, 'heldout': False, 'calibration_usable': False,
            'harts_vlenb_expected': [32, 32, 32],
            'modes': {'2': 'Fence after every group; original closing vector-CSR restore and app VL32 load',
                      '0': 'No per-group fences; four loads followed by four stores',
                      '1': 'No per-group fences; original closing vector-CSR restore then app VL32 load'},
            'idle_policy': 'Hart1 WFI; hart0 initializes input/output/guards and dispatches with sparse bounded CLINT polling; hart2 performs all vector traffic.',
            'scope': 'Bare M-mode identity mapping; no Zephyr scheduling, yield or interrupt-time context guarantee.'}
