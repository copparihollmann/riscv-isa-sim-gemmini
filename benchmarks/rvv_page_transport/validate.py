"""Independent page/beat geometry and complete-byte oracle for context transfers."""
import json


def golden(pattern):
    value = 14695981039346656037
    for index in range(1024):
        byte = ((index % 256) * 17 + (index // 256) * 61 + 13) % 256 if pattern == 1 else 0
        value = ((value ^ byte) * 1099511628211) % (1 << 64)
    return value


def specification():
    result = []
    for mode in [2, 0, 1]:
        for family in ['contained', 'load', 'store', 'both']:
            for group in ([4] if family == 'contained' else range(4)):
                for before in ([0] if family == 'contained' else range(32, 225, 32)):
                    start = 4096 - 256 * group - before if family != 'contained' else 256
                    for pattern in [0, 1]:
                        parent = f'rvv.page.hart2.{family}.g{group}.before{before}.mode{mode}.pattern{pattern}'
                        for trial in range(5):
                            result.append({'case_id': parent + '.trial.' + str(trial), 'parent_case_id': parent,
                                'trial_id': trial, 'suite': 'rvv_page_transport', 'mask': 4, 'region': 'kernel',
                                'family': family, 'crossing_group': group, 'bytes_before_page': before,
                                'input_offset': start if family in ['load', 'both'] else 256,
                                'output_offset': start if family in ['store', 'both'] else 256,
                                'mode': mode, 'pattern': pattern, 'expected_checksums': [0, 0, golden(pattern)]})
    return result


def validate(text, corpus):
    if (corpus.get('schema') != 'iris.rvv_page_transport_corpus.v1'
            or corpus.get('split_id') != 'iris-rvv-page-transport-fit-v1'
            or type(corpus.get('trials')) is not int or corpus['trials'] != 5
            or corpus.get('harts_vlenb_expected') != [32, 32, 32]
            or corpus.get('heldout') is not False or corpus.get('calibration_usable') is not False):
        raise ValueError('Exact fitting-only page/CSR corpus required')
    cases = specification()
    if corpus.get('cases') != cases:
        raise ValueError('Declared page corpus differs from independent identities/goldens')
    layout = corpus.get('layout', {})
    if set(layout) != {'input_arena', 'output_arena', 'alignment', 'arena_bytes'}:
        raise ValueError('Exact ELF arena layout required')
    if (any(type(x) is not int for x in layout.values()) or layout['alignment'] != 4096 or layout['arena_bytes'] != 8192
            or any(layout[k] % 4096 or not 0x80000000 <= layout[k] <= 0x180000000 - 8192 for k in ('input_arena', 'output_arena'))
            or abs(layout['input_arena'] - layout['output_arena']) < 8192):
        raise ValueError('Invalid page-aligned DRAM arena layout')
    expected = {c['case_id']: c for c in cases}
    order = [c['case_id'] for c in cases]
    seen, began, done, layouts, hart_reports = [], [], [], [], []
    for line in text.splitlines():
        if line.startswith(('IRIS_FATAL', 'IRIS_PROBE_TIMEOUT')):
            raise ValueError('Guest failure: ' + line)
        if line.startswith('IRIS_PAGE_LAYOUT '): layouts.append(json.loads(line.split(' ', 1)[1]))
        if line.startswith('IRIS_PAGE_HARTS '): hart_reports.append(json.loads(line.split(' ', 1)[1]))
        if line.startswith('IRIS_PROBE_BEGIN '):
            row = json.loads(line.split(' ', 1)[1])
            if type(row.get('hart')) is not int or row['hart'] != 2: raise ValueError('Wrong probe hart')
            began.append(row['case_id'])
        if line.startswith('IRIS_BATCH_DONE '): done.append(json.loads(line.split(' ', 1)[1]))
        if not line.startswith('IRIS_REGION '): continue
        row = json.loads(line.split(' ', 1)[1]); name = row.get('case_id')
        if name not in expected or name in seen: raise ValueError('Unexpected/duplicate page region')
        c = expected[name]
        for field in ('hart', 'crossing_group', 'bytes_before_page', 'input_address', 'output_address', 'mode',
                      'pattern', 'trial_id', 'start_cycle', 'end_cycle', 'instret_delta', 'checksum', 'expected_checksum'):
            if type(row.get(field)) is not int or not 0 <= row[field] < 2**64: raise ValueError('Invalid unsigned page field: ' + field)
        if (row['hart'] != 2 or row.get('pass') is not True or row.get('guards_preserved') is not True
                or row['end_cycle'] <= row['start_cycle'] or row['checksum'] != c['expected_checksums'][2]
                or row['expected_checksum'] != c['expected_checksums'][2]
                or any(row.get(k) != c[k] for k in ('parent_case_id', 'suite', 'region', 'family', 'crossing_group',
                                                     'bytes_before_page', 'mode', 'pattern', 'trial_id'))):
            raise ValueError('Independent page identity/data/counter check failed: ' + name)
        for kind, arena in [('input', 'input_arena'), ('output', 'output_arena')]:
            address = row[kind + '_address']
            if address != layout[arena] + c[kind + '_offset']: raise ValueError('Wrong actual page address')
            crossed = []
            for group in range(4):
                first = address + group * 256
                if first // 4096 != (first + 255) // 4096:
                    crossed.append((group, 4096 - first % 4096))
            should_cross = c['family'] == 'both' or c['family'] == ('load' if kind == 'input' else 'store')
            if crossed != ([(c['crossing_group'], c['bytes_before_page'])] if should_cross else []):
                raise ValueError('Actual page/beat geometry differs from declared case')
        seen.append(name)
    if (hart_reports != [{'vlenb': [32, 32, 32], 'expected': 32}] or layouts != [layout]
            or seen != order or began != order or done != [{'failed': 0, 'regions': len(order)}]):
        raise ValueError('Incomplete/reordered page batch or actual layout')
    return {'functional_checks_passed': True, 'regions': len(seen), 'trials': 5,
            'per_hart_regions': {'2': len(seen)}, 'all_independent_checksums_passed': True,
            'all_actual_addresses_and_page_splits_checked': True, 'guards_preserved': True,
            'group_positions': [0, 1, 2, 3], 'split_bytes_before_page': list(range(32, 225, 32)),
            'load_store_both_controls': True, 'zero_and_varied_data': True, 'modes': [2, 0, 1],
            'actual_vlenb_by_hart': [32, 32, 32],
            'qualification': 'Bare M-mode page/CSR diagnostic with a polling scalar observer; no Zephyr scheduler or interrupt-context qualification.',
            'timing_certified': False, 'calibration_usable': False}
