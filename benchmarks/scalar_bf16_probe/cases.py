"""Disjoint fitting observations for advertised scalar BF16 decode."""

SPLIT = 'iris-scalar-bf16-decoder-fit-v1'
SENTINEL = 0x0123456789abcdef
FFLAGS = 0x1b


def checksum(values):
    result = 14695981039346656037
    for value in values:
        for shift in range(0, 64, 8):
            result = ((result ^ ((value >> shift) & 255)) * 1099511628211) & ((1 << 64) - 1)
    return result


def corpus():
    expected = checksum([1, SENTINEL, FFLAGS, 2, 1])
    cases = []
    for trial in range(5):
        for kind, base, mnemonic in [(0, 0x44800053, 'fcvt.bf16.s'),
                                     (1, 0x40600053, 'fcvt.s.bf16')]:
            for rm in range(8):
                for pattern, operand in enumerate([0, 0xffffffffffffffff, 0xffffffff3fa00000]):
                    parent = f'scalar-bf16.{mnemonic}.rm{rm}.pattern{pattern}'
                    cases.append({'case_id': f'{parent}.trial{trial}', 'parent_case_id': parent,
                        'trial_id': trial, 'kind': kind, 'rm': rm, 'pattern': pattern,
                        'instruction': base | (1 << 15) | (2 << 7) | (rm << 12),
                        'operand_bits': operand, 'expected_checksums': {str(h): expected for h in range(3)},
                        'expected_trap_cause': 2, 'expected_destination': SENTINEL,
                        'expected_fcsr': FFLAGS})
    return {'schema': 'iris.scalar_bf16_decode_corpus.v1', 'split_id': SPLIT,
            'harts_online': [0, 1, 2], 'trials': 5, 'cases': cases,
            'regions': 3 * len(cases), 'idle_policy': 'All harts boot; only one hart probes at a time, peers poll or WFI.',
            'expected_behavior_basis': 'Both complete scalar BF16 opcode families are disjoint from every pinned source decoder pattern.',
            'source_proof': 'spike/scalar-bf16-decoder-proof.json',
            'source_image_association_verified': False, 'calibration_usable': False}


if __name__ == '__main__':
    import json
    print(json.dumps(corpus(), indent=2))
