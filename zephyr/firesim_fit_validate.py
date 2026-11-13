"""Independent identities/goldens for repeated three-hart Zephyr training."""
import collections
import json

SPLIT = 'iris-zephyr-fpga-fit-v1'


def corpus(trials=5):
    if type(trials) is not int or not 1 <= trials <= 20:
        raise ValueError('Trials1..20 required')
    cases = []
    for trial in range(trials):
        for mask in range(1, 8):
            harts = [h for h in range(3) if mask & (1 << h)]
            for operation in ('gemm16', 'conv2d8', 'vme_or_copy'):
                expected = [0, 0, 0]
                roles = {}
                for rank, hart in enumerate(harts):
                    if operation == 'gemm16':
                        expected[hart] = len(range(rank, 16, len(harts))) * 16 * 16
                    elif operation == 'conv2d8':
                        expected[hart] = len(range(rank, 6, len(harts))) * 6 * 9
                    else:
                        expected[hart] = 32 * 32
                    roles[str(hart)] = ('scalar.compute' if operation != 'vme_or_copy'
                                         else 'vme.compute' if hart < 2 else 'vector.copy')
                parent = 'zephyr.fit.' + operation + '.mask' + str(mask)
                common = {'suite': 'zephyr', 'trial_id': trial, 'workload_mask': mask, 'split': 'fitting'}
                cases.append(dict(common, case_id=parent + '.trial.' + str(trial), parent_case_id=parent,
                                  region='kernel', mask=mask, expected_checksums=expected, roles=roles))
                parent += '.dispatch'
                cases.append(dict(common, case_id=parent + '.trial.' + str(trial), parent_case_id=parent,
                                  region='dispatch_to_join', mask=1,
                                  expected_checksums=[sum(expected), 0, 0], roles={}))
    return {'schema': 'iris.zephyr_training_corpus.v1', 'split_id': SPLIT, 'trials': trials,
            'cases': cases, 'harts_online': [0, 1, 2],
            'idle_policy': 'All OS harts stay online. Unselected worker threads block on semaphores; normal Zephyr idle/timers remain active.',
            'dispatch_region': 'Fixed hart0 from semaphore dispatch through all selected workers joined; excludes boot, checksum aggregation and printing.',
            'mtime_bracketing': 'CLINT MMIO reads outside the cycle boundaries bracket each region; no cross-hart mcycle origin is assumed.',
            'heldout': False, 'calibration_usable': False}


def validate(text, specification):
    if specification.get('split_id') != SPLIT:
        raise ValueError('Wrong Zephyr training split')
    if specification != corpus(specification.get('trials')):
        raise ValueError('Training corpus differs from independent case/golden generator')
    cases = {c['case_id']: c for c in specification['cases']}
    expected = {(name, h) for name, c in cases.items() for h in range(3) if c['mask'] & (1 << h)}
    seen, done, phases = {}, [], []
    for line in text.splitlines():
        if line.startswith('IRIS_FATAL') or any(s in line for s in ('ZEPHYR FATAL ERROR', 'ASSERTION FAIL', '***FAILED***')):
            raise ValueError('Guest fatal/failure: ' + line)
        if line.startswith('IRIS_BATCH_DONE '):
            done.append(json.loads(line.split(' ', 1)[1]))
        if line.startswith('IRIS_FIT_PHASE '):
            phases.append(json.loads(line.split(' ', 1)[1]))
        if not line.startswith('IRIS_REGION '):
            continue
        row = json.loads(line.split(' ', 1)[1])
        if not isinstance(row, dict):
            raise ValueError('Region must be an object')
        for field in ('hart', 'trial_id', 'start_cycle', 'end_cycle', 'instret_delta',
                      'mtime_start', 'mtime_end', 'checksum', 'expected_checksum', 'hart_mask'):
            if type(row.get(field)) is not int or not 0 <= row[field] < 2 ** 64:
                raise ValueError('Invalid integer region field: ' + field)
        key = row.get('case_id'), row['hart']
        if key not in expected or key in seen:
            raise ValueError('Unexpected/duplicate region identity: ' + repr(key))
        c = cases[key[0]]
        for field in ('parent_case_id', 'trial_id', 'suite', 'region'):
            if row.get(field) != c[field]:
                raise ValueError('Wrong case identity field: ' + field)
        golden = c['expected_checksums'][key[1]]
        if row.get('pass') is not True or row['checksum'] != golden or row['expected_checksum'] != golden:
            raise ValueError('Independent checksum mismatch: ' + repr(key))
        if (row['end_cycle'] <= row['start_cycle'] or row['mtime_end'] < row['mtime_start']
                or row['hart_mask'] != c['workload_mask']):
            raise ValueError('Bad counter bracket/placement: ' + repr(key))
        if c['region'] == 'kernel' and row.get('role') != c['roles'][str(key[1])]:
            raise ValueError('Wrong heterogeneous worker role')
        seen[key] = row
    if set(seen) != expected:
        raise ValueError('Missing Zephyr training regions: ' + str(len(expected - set(seen))))
    want_done = {'failed': 0, 'cases': len(cases), 'regions': len(expected), 'trials': specification['trials']}
    if done != [want_done]:
        raise ValueError('Bad Zephyr batch completion')
    if phases != [{'trial_id': t, 'begin': b} for t in range(specification['trials']) for b in (True, False)]:
        raise ValueError('Bad trial phase sequence')
    return {'functional_checks_passed': True, 'cases': len(cases), 'regions': len(seen),
            'trials': specification['trials'], 'phase_markers': len(phases),
            'per_hart_regions': dict(collections.Counter(h for _, h in seen)),
            'all_independent_checksums_passed': True, 'all_seven_hart_subsets': True,
            'hart2_role': 'Ordinary vector copy during matrix cases; no hart2 VME instructions',
            'timing_certified': False, 'calibration_usable': False}
