"""Independent byte-level oracle and ordering for Rocket vector context traffic."""
SPLIT = 'iris-rvv-context-transport-fit-v1'


def checksum(vl):
    value = 14695981039346656037
    for group in range(4):
        for i in range(vl):
            value = ((value ^ ((i * 17 + group * 61 + 13) & 255)) * 1099511628211) & ((1 << 64) - 1)
    return value


def cases(trials=5):
    rows = []
    # Fenced cases precede all unfenced controls; the previously untested
    # largest four-group transfers are last. This preserves useful earlier
    # controls if an unfenced request cannot complete on the physical image.
    for drain in (1, 0):
        for lmul in (1, 2, 4, 8):
            for vl in (1, 7, 32 * lmul):
                for trial in range(trials):
                    parent = 'rvv.context.hart2.m%d.vl%d.drain%d' % (lmul, vl, drain)
                    rows.append({'case_id': parent + '.trial.' + str(trial), 'parent_case_id': parent,
                                 'trial_id': trial, 'suite': 'rvv_context_transport', 'mask': 4,
                                 'lmul': lmul, 'avl': vl, 'drain': drain, 'region': 'kernel',
                                 'expected_checksums': [0, 0, checksum(vl)]})
    return {'schema': 'iris.rvv_context_transport_corpus.v1', 'split_id': SPLIT, 'trials': trials,
            'cases': rows, 'heldout': False, 'hart2_context': 'Bare machine mode, FS/VS enabled by the shared CRT; no OS lazy context restore or scheduling.',
            'idle_policy': 'Hart1 parks in WFI. Hart0 dispatches and polls completion with bounded CLINT checks; its traffic perturbs the shared fabric.',
            'watchdog': 'Hart0 fails the guest after250000 CLINT ticks without a case completion. This is a diagnostic bound, not a calibrated wall time.'}
