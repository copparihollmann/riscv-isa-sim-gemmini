"""Verify physical data movement and every repeated LMUL transport identity."""
import json


def golden(vl):
    value = 14695981039346656037
    for group in range(4):
        for i in range(vl):
            value = ((value ^ ((i * 17 + group * 61 + 13) & 255)) * 1099511628211) & ((1 << 64) - 1)
    return value


def validate(text, corpus):
    if corpus.get('split_id') != 'iris-rvv-context-transport-fit-v1' or type(corpus.get('trials')) is not int or corpus['trials'] != 5:
        raise ValueError('Exact five-trial transport corpus required')
    expected, order = {}, []
    for drain in (1, 0):
        for lmul in (1, 2, 4, 8):
            for vl in (1, 7, 32 * lmul):
                parent = 'rvv.context.hart2.m%d.vl%d.drain%d' % (lmul, vl, drain)
                for trial in range(5):
                    name = parent + '.trial.' + str(trial)
                    expected[name] = dict(parent_case_id=parent, lmul=lmul, avl=vl, vl=vl,
                                          drain=drain, trial_id=trial, checksum=golden(vl))
                    order.append(name)
    cases = corpus['cases']
    if [c['case_id'] for c in cases] != order:
        raise ValueError('Wrong declared transport case order')
    for c in cases:
        x = expected[c['case_id']]
        if (c['mask'] != 4 or c['region'] != 'kernel' or c['suite'] != 'rvv_context_transport'
                or c['expected_checksums'] != [0, 0, x['checksum']]
                or any(c.get(k) != x[k] for k in ('parent_case_id', 'lmul', 'avl', 'drain', 'trial_id'))):
            raise ValueError('Declared transport case/golden differs from independent generator')
    seen, began, done = [], [], []
    for line in text.splitlines():
        if line.startswith(('IRIS_FATAL', 'IRIS_PROBE_TIMEOUT')):
            raise ValueError('Guest failure: ' + line)
        if line.startswith('IRIS_PROBE_BEGIN '):
            x = json.loads(line.split(' ', 1)[1])
            if type(x.get('hart')) is not int or x['hart'] != 2:
                raise ValueError('Wrong probe hart')
            began.append(x['case_id'])
        if line.startswith('IRIS_BATCH_DONE '):
            done.append(json.loads(line.split(' ', 1)[1]))
        if not line.startswith('IRIS_REGION '):
            continue
        row = json.loads(line.split(' ', 1)[1])
        name = row.get('case_id')
        if name not in expected or name in seen:
            raise ValueError('Unexpected/duplicate transport region')
        for field in ('hart', 'lmul', 'avl', 'vl', 'drain', 'trial_id', 'start_cycle', 'end_cycle',
                      'instret_delta', 'checksum', 'expected_checksum'):
            if type(row.get(field)) is not int or not 0 <= row[field] < 2 ** 64:
                raise ValueError('Invalid unsigned transport field: ' + field)
        x = expected[name]
        if (row['hart'] != 2 or row['region'] != 'kernel' or row['suite'] != 'rvv_context_transport'
                or row['pass'] is not True or row['end_cycle'] <= row['start_cycle']
                or any(row.get(k) != v for k, v in x.items()) or row['expected_checksum'] != x['checksum']):
            raise ValueError('Independent transport identity/data/counter check failed: ' + name)
        seen.append(name)
    if seen != order or began != order or done != [{'failed': 0, 'regions': len(order)}]:
        raise ValueError('Incomplete/reordered transport batch')
    return {'functional_checks_passed': True, 'regions': len(seen), 'trials': 5,
            'per_hart_regions': {'2': len(seen)}, 'all_independent_checksums_passed': True,
            'lmul': [1, 2, 4, 8], 'fenced_and_unfenced': True,
            'qualification': 'Baremetal context-size transfer control with a polling hart0 observer; no OS context/scheduler certification.',
            'timing_certified': False, 'calibration_usable': False}
