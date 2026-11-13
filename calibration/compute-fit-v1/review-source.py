#!/usr/bin/env python3
"""Independent typed/source/ELF review of the NEW compute-only reference."""
import collections
import copy
import hashlib
import json
import pathlib
import re
import struct

import empirical_priority_review as priority

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/compute-fit-v3'
PARENT = ROOT / 'build/campaign-buffered-priority-v2-final'


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def audit_cases(corpus, parent, canonical, split, oldsplit):
    if (corpus.get('schema') != 'iris.compute_fitting_corpus.v1' or corpus.get('split_id') != 'iris-compute-fitting-v1'
            or corpus.get('trials') != 3 or type(corpus['trials']) is not int
            or corpus.get('physical_harts') != 3 or corpus.get('expected_region_count') != 1008
            or corpus.get('ordering_uses_measured_cycles') is not False):
        raise ValueError('Wrong new compute corpus contract')
    original = [c for c in parent['cases'] if c['suite'] == 'distribution' and c['kind'] not in ('memory', 'vme_memory')]
    semantic = {c['case_id']: c for c in canonical['distribution']}
    expected = []
    for c in original:
        gold = semantic[c['semantic_parent_case_id']]
        for field in ('kind', 'n', 'mask', 'sew', 'lmul', 'mode', 'bytes', 'protocol', 'edge', 'tk', 'tiles', 'expected_checksums'):
            if c[field] != gold[field]:
                raise ValueError('Parent differs from independent canonical source/golden ' + field)
        e = copy.deepcopy(c)
        e['reference_parent_case_id'] = e['parent_case_id']
        e['case_id'] = 'compute.v1.' + e['case_id'][len('buffered.v2.'):]
        e['parent_case_id'] = 'compute.v1.' + e['semantic_parent_case_id']
        expected.append(e)
    if len(corpus['cases']) != 456 or corpus['cases'] != expected:
        raise ValueError('Compute subset/order/fields/goldens differ')
    integer_fields = ('n', 'mask', 'sew', 'lmul', 'mode', 'bytes', 'protocol', 'edge', 'tk', 'tiles', 'trial_id')
    for c in corpus['cases']:
        if any(type(c[field]) is not int for field in integer_fields) or any(type(v) is not int for v in c['expected_checksums']):
            raise ValueError('Boolean/float is not a source integer')
        if c['kind'] in ('memory', 'vme_memory') or c['suite'] != 'distribution':
            raise ValueError('Excluded bulk storage case admitted')
    parents = {c['parent_case_id'] for c in expected}
    if len(parents) != 152 or set(split['split']) != parents:
        raise ValueError('Wrong split domain')
    if (split.get('schema') != 'iris.compute_fitting_parent_split.v1'
            or split.get('frozen_before_hardware') is not True
            or split.get('timing_labels_used_for_selection') is not False):
        raise ValueError('Wrong frozen compute split contract')
    for c in expected:
        entry = dict(oldsplit['split'][c['reference_parent_case_id']], reference_parent_case_id=c['reference_parent_case_id'])
        if split['split'][c['parent_case_id']] != entry:
            raise ValueError('Inherited semantic partition changed')
    if sum(bin(c['mask']).count('1') for c in expected) != 1008:
        raise ValueError('Active-hart region count')
    return expected


def main():
    out = ROOT / 'calibration/compute-fit-v1'
    out.mkdir(exist_ok=False)
    paths = [BUILD / n for n in ('corpus.json', 'split.json', 'build.json', 'readback-layout.json')]
    corpus, split, built, layout = [json.loads(p.read_text()) for p in paths]
    parent = json.loads((PARENT / 'corpus.json').read_text())
    oldsplit_path = ROOT / 'calibration/empirical-priority-v2/split.json'
    oldsplit = json.loads(oldsplit_path.read_text())
    if split['inherited_parent_split_sha256'] != sha(oldsplit_path):
        raise ValueError('Inherited frozen split identity')
    canonical = priority.canonical_cases()
    cases = audit_cases(corpus, parent, canonical, split, oldsplit)
    for name, digest in built['input_sha256'].items():
        if sha(name) != digest or sha(BUILD / 'inputs' / digest) != digest:
            raise ValueError('Actual compiler source/input snapshot changed ' + name)
    new = (BUILD / 'distribution.c').read_text()
    old = (PARENT / 'distribution.c').read_text()
    start, end = 'static unsigned active_count', 'void campaign_distribution_run(unsigned h) {'
    if new[new.index(start):new.index(end)] != old[old.index(start):old.index(end)]:
        raise ValueError('Kernel/preparation/measured windows changed')
    prefix = new[:new.index(start)]
    for name in ('data[3][262144]', 'shared_data[262144]', 'eviction[3][524288]'):
        a = 'static uint32_t ' + name + ' __attribute__((aligned(64),section(".noinit.compute_unused")));'
        b = 'static uint32_t ' + name + ' __attribute__((aligned(64)));'
        if prefix.count(a) != 1:
            raise ValueError('Missing exact unused-storage attribute')
        prefix = prefix.replace(a, b)
    if prefix != old[:old.index(start)]:
        raise ValueError('Other declaration/source change')
    expected_footer = end + '\n  (void)h;\n  barrier();\n  for(unsigned i=0;i<CAMPAIGN_CASES;++i)run(&experiments[i]);\n}\n'
    if new[new.index(end):] != expected_footer:
        raise ValueError('Unexpected startup/dispatch replacement')
    main_old = (ROOT / 'benchmarks/campaign_buffered/main_reordered.c').read_text()
    dispatch = '  campaign_memory_run(hart);campaign_distribution_run(hart);\n  for(unsigned trial=0;trial<CAMPAIGN_TRIALS;++trial) campaign_baseline_run(hart,trial);'
    if main_old.count(dispatch) != 1 or (BUILD / 'main.c').read_text() != main_old.replace(dispatch, '  campaign_distribution_run(hart);'):
        raise ValueError('Other orchestration/source change')
    elf = BUILD / 'campaign.elf'
    blob = elf.read_bytes()
    header, symbols = priority.base.elf_symbols(blob)
    if sha(elf) != built['elf_sha256'] or sha(elf) != layout['elf_sha256']:
        raise ValueError('Wrong exact ELF')
    program_headers = [struct.unpack_from('<IIQQQQQQ', blob, header[5] + i * header[9]) for i in range(header[10])]

    def file_bytes(address, count):
        found = [p for p in program_headers if p[0] == 1 and p[3] <= address and address + count <= p[3] + p[5]]
        if len(found) != 1:
            raise ValueError('ELF bytes not uniquely file-backed')
        p = found[0]
        return blob[p[2] + address - p[3]:p[2] + address - p[3] + count]

    def string(address):
        data = bytearray()
        for i in range(256):
            byte = file_bytes(address + i, 1)
            if byte == b'\0':
                return bytes(data).decode()
            data += byte
        raise ValueError('Unbounded compiled identity')

    # Decode the actual RV64 LP64D call table, independently of the builder's
    # textual tables. Alignment: pointer0, enum8, ten uint32s12, golden[3]56.
    enum = re.search(r'enum\s*\{([^}]+)\}', new, re.S)
    kinds = [v.strip().removeprefix('K_') for v in enum.group(1).split(',')]
    table_address, table_size = symbols['experiments']
    if table_size != 456 * 80:
        raise ValueError('Actual case_t ABI/table geometry differs')
    integer_fields = ('n', 'mask', 'sew', 'lmul', 'mode', 'bytes', 'protocol', 'edge', 'tk', 'tiles')
    for i, case in enumerate(cases):
        data = file_bytes(table_address + 80 * i, 80)
        if string(struct.unpack_from('<Q', data)[0]) != case['case_id']:
            raise ValueError('Actual compiled case identity/order differs')
        k = struct.unpack_from('<I', data, 8)[0]
        if k >= len(kinds) or kinds[k] != case['kind']:
            raise ValueError('Actual compiled case kind differs')
        if list(struct.unpack_from('<10I', data, 12)) != [case[k] for k in integer_fields]:
            raise ValueError('Actual compiled kernel arguments differ')
        if list(struct.unpack_from('<3Q', data, 56)) != case['expected_checksums']:
            raise ValueError('Actual compiled expected output differs')
    # Parse sections directly; NOBITS is not assumed to be outside p_memsz.
    section_headers = [struct.unpack_from('<IIQQQQIIQQ', blob, header[6] + i * header[11]) for i in range(header[12])]
    names_header = section_headers[header[13]]
    names = blob[names_header[4]:names_header[4] + names_header[5]]
    sections = {names[s[0]:].split(b'\0', 1)[0].decode(): s for s in section_headers}
    unused, bss = sections['.noinit.compute_unused'], sections['.bss']
    if unused[1] != 8 or unused[2] & 3 != 3 or unused[5] != 10 * 1024 * 1024:
        raise ValueError('Wrong allocated NOBITS unused-storage region')
    if bss[1] != 8 or bss[5] != 79680 or symbols['__bss_start'][0] != bss[3] or symbols['__bss_end'][0] != bss[3] + bss[5]:
        raise ValueError('CRT BSS extent differs')
    intervals = sorted((symbols[n][0], symbols[n][0] + symbols[n][1], n) for n in ('data', 'shared_data', 'eviction'))
    if intervals[0][0] != unused[3] or intervals[-1][1] != unused[3] + unused[5] or any(a[1] != b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError('Unused symbols do not exclusively cover noinit storage')
    if not (bss[3] + bss[5] <= unused[3] and 0x80000000 <= unused[3] and unused[3] + unused[5] <= 0x180000000):
        raise ValueError('Noinit overlap/address range')
    for name, geometry in layout['objects'].items():
        if symbols[name] != (geometry['address'], geometry['size']):
            raise ValueError('Actual readback geometry differs')
    if symbols['buffered_records'][1] != 1008 * 64 or file_bytes(symbols['buffered_measurements_done'][0], 8) != b'\xff' * 8:
        raise ValueError('Record capacity/completion sentinel')
    negatives = []
    for name in ('golden', 'reordered', 'boolean_trial', 'unknown_field', 'memory_case', 'wrong_dataset', 'split_partition'):
        bad, badsplit = copy.deepcopy(corpus), copy.deepcopy(split)
        if name == 'golden': bad['cases'][0]['expected_checksums'][0] += 1
        elif name == 'reordered': bad['cases'][0], bad['cases'][1] = bad['cases'][1], bad['cases'][0]
        elif name == 'boolean_trial': bad['cases'][0]['trial_id'] = False
        elif name == 'unknown_field': bad['cases'][0]['golden_cycles'] = 7
        elif name == 'memory_case': bad['cases'][0]['kind'] = 'memory'
        elif name == 'wrong_dataset': bad['cases'][0]['case_id'] = 'buffered.v2.wrong'
        else: badsplit['split'][bad['cases'][0]['parent_case_id']]['partition'] = 'train'
        try: audit_cases(bad, parent, canonical, badsplit, oldsplit)
        except (ValueError, KeyError): negatives.append({'name': name, 'rejected': True})
        else: raise ValueError('Corrupted compute packet accepted ' + name)
    inputs = [pathlib.Path(__file__).resolve(), ROOT / 'timing/empirical_priority_review.py', ROOT / 'timing/empirical_buffered_review.py',
              ROOT / 'benchmarks/golden.py', ROOT / 'benchmarks/v2/cases.py', ROOT / 'benchmarks/memory_routes/cases.py',
              ROOT / 'benchmarks/calibration-corpus.json', oldsplit_path, PARENT / 'corpus.json', PARENT / 'distribution.c',
              ROOT / 'benchmarks/campaign_buffered/main_reordered.c', *paths, elf, BUILD / 'main.c', BUILD / 'distribution.c',
              BUILD / 'distribution_cases.inc', BUILD / 'buffered_cases.inc']
    noinit_load_segments = [{'virtual_address': p[3], 'file_bytes': p[5], 'memory_bytes': p[6]} for p in program_headers if p[0] == 1 and p[3] <= unused[3] and unused[3] + unused[5] <= p[3] + p[6]]
    report = {'schema': 'iris.compute_fitting_independent_review.v1', 'pass': True,
              'ELF_sha256': sha(elf), 'elf_sha256': sha(elf), 'corpus_sha256': sha(BUILD / 'corpus.json'), 'split_sha256': sha(BUILD / 'split.json'),
              'cases': 456, 'semantic_parents': 152, 'regions': 1008, 'bss_bytes': 79680,
              'kernel_preparation_window_source_equal': True, 'compiled_table_identity_order_verified': True,
              'independent_goldens_verified': True, 'no_bulk_memory_cases': True,
              'noinit_symbols': intervals, 'noinit_bytes': unused[5], 'noinit_start': unused[3],
              'noinit_pt_load_coverage': noinit_load_segments,
              'noinit_unknown_reset_claimed': False,
              'noinit_scope': 'Unreachable for admitted fixed kinds; NOLOAD/NOBITS does not itself promise unknown memory because FESVR may zero the PT_LOAD tail. CRT never clears these bytes.',
              'unused_access_proof': 'All admitted immutable call-table kinds exclude memory/vme_memory. Unchanged prepare/kernel only reference data/shared_data/eviction in those branches; unrelated startup bulk fills are removed. This is a source/control-flow proof, not a runtime memory trace.',
              'split_partitions': dict(collections.Counter(v['partition'] for v in split['split'].values())),
              'negative_controls': negatives, 'old_timing_labels_reused': False,
              'numeric_functional_execution_claimed': False, 'hardware_contacted': False,
              'global_heldout_timings_consumed': False, 'full_2pct_certified': False,
              'input_sha256': {str(p): sha(p) for p in inputs}}
    (out / 'review-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
    (out / 'review.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'pass': True, 'review': str(out / 'review.json'), 'sha256': sha(out / 'review.json'), 'noinit_pt_load_coverage': noinit_load_segments}, indent=2))


if __name__ == '__main__':
    main()
