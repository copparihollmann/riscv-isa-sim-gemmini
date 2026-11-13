#!/usr/bin/env python3
"""New exact-ELF compute fitting corpus, without unrelated bulk-memory startup."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PARENT = ROOT / 'build/campaign-buffered-priority-v2-final'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    parent_build = json.loads((PARENT / 'build.json').read_text())
    for name, digest in parent_build['input_sha256'].items():
        if sha(name) != digest: raise ValueError('Frozen parent input changed: ' + name)
    original = json.loads((PARENT / 'corpus.json').read_text())
    selected = [c for c in original['cases'] if c['suite'] == 'distribution'
                and c['kind'] not in ('memory', 'vme_memory')]
    assert len(selected) == 456 and len({c['semantic_parent_case_id'] for c in selected}) == 152
    assert sum(bin(c['mask']).count('1') for c in selected) == 1008
    cases = copy.deepcopy(selected)
    for c in cases:
        c['reference_parent_case_id'] = c['parent_case_id']
        c['case_id'] = 'compute.v1.' + c['case_id'].removeprefix('buffered.v2.')
        c['parent_case_id'] = 'compute.v1.' + c['semantic_parent_case_id']
    corpus = dict(original, schema='iris.compute_fitting_corpus.v1',
        split_id='iris-compute-fitting-v1', cases=cases, expected_region_count=1008,
        original_corpus_sha256=sha(PARENT / 'corpus.json'),
        purpose='New compute-only fitting execution; all old timing labels are inapplicable',
        excluded_kinds=['memory', 'vme_memory'],
        unused_storage_policy='Unused bulk-memory buffers are NOLOAD/noinit and never read by admitted cases.',
        console_policy='All numeric checks and records before bulk UART; post-ROI debugger readback permitted',
        cache_policy='New code/data/predictor layout/history; no inherited cold/warm or timing claim',
        ordering_uses_measured_cycles=False, memory_regions={})
    corpus.pop('priority_prefix_cases', None); corpus.pop('priority_prefix_regions', None)
    (output / 'corpus.json').write_text(json.dumps(corpus, indent=2) + '\n')
    (output / 'original-corpus.json').write_bytes((PARENT / 'corpus.json').read_bytes())
    parent_split = ROOT / 'calibration/empirical-priority-v2/split.json'
    old_split = json.loads(parent_split.read_text())
    split = {c['parent_case_id']: {**old_split['split'][c['reference_parent_case_id']],
                                  'reference_parent_case_id': c['reference_parent_case_id']}
             for c in cases}
    (output / 'split.json').write_text(json.dumps({'schema': 'iris.compute_fitting_parent_split.v1',
        'frozen_before_hardware': True, 'inherited_parent_split_sha256': sha(parent_split),
        'timing_labels_used_for_selection': False, 'split': split}, indent=2) + '\n')
    (output / 'campaign_counts.h').write_text('#pragma once\n#define CAMPAIGN_TRIALS 3\n'
        '#define CAMPAIGN_CASES 456\n#define CAMPAIGN_REGIONS 1008\n')
    fields = ('n', 'mask', 'sew', 'lmul', 'mode', 'bytes', 'protocol', 'edge', 'tk', 'tiles')
    (output / 'distribution_cases.inc').write_text('static const case_t experiments[]={\n' + ',\n'.join(
        '{' + json.dumps(c['case_id']) + ',K_' + c['kind'] + ',' + ','.join(str(c[k]) for k in fields)
        + ',{' + ','.join(str(v) + 'ULL' for v in c['expected_checksums']) + '}}' for c in cases) + '\n};\n')
    tables = []
    for name, key in [('original_ids', 'case_id'), ('ids', 'case_id'), ('parent_ids', 'parent_case_id'), ('suites', 'suite')]:
        tables.append('static const char *const buffered_' + name + '[]={' + ','.join(json.dumps(c[key]) for c in cases) + '};')
    for name, key in [('masks', 'mask'), ('trials', 'trial_id')]:
        tables.append('static const unsigned buffered_' + name + '[]={' + ','.join(str(c[key]) for c in cases) + '};')
    tables.append('static const uint64_t buffered_goldens[][3]={' + ','.join(
        '{' + ','.join(str(v) + 'ULL' for v in c['expected_checksums']) + '}' for c in cases) + '};')
    (output / 'buffered_cases.inc').write_text('\n'.join(tables) + '\n')
    main = (ROOT / 'benchmarks/campaign_buffered/main_reordered.c').read_text()
    before = '  campaign_memory_run(hart);campaign_distribution_run(hart);\n  for(unsigned trial=0;trial<CAMPAIGN_TRIALS;++trial) campaign_baseline_run(hart,trial);'
    assert main.count(before) == 1
    (output / 'main.c').write_text(main.replace(before, '  campaign_distribution_run(hart);'))
    original_source = (PARENT / 'distribution.c').read_text()
    source = original_source
    for name in ('data[3][262144]', 'shared_data[262144]', 'eviction[3][524288]'):
        before = 'static uint32_t ' + name + ' __attribute__((aligned(64)));'
        assert source.count(before) == 1
        source = source.replace(before, 'static uint32_t ' + name +
            ' __attribute__((aligned(64),section(".noinit.compute_unused")));')
    marker = 'void campaign_distribution_run(unsigned h) {'
    assert source.count(marker) == 1
    source = source[:source.index(marker)] + marker + '\n  (void)h;\n  barrier();\n' + \
        '  for(unsigned i=0;i<CAMPAIGN_CASES;++i)run(&experiments[i]);\n}\n'
    start = 'static unsigned active_count'
    assert source[source.index(start):source.index(marker)] == original_source[original_source.index(start):original_source.index(marker)]
    (output / 'distribution.c').write_text(source)
    argv = []
    for arg in parent_build['argv']:
        if arg in (str(PARENT / 'baseline.c'), str(PARENT / 'memory.c')): continue
        if arg == '-I' + str(PARENT): arg = '-I' + str(output)
        if arg == str(ROOT / 'benchmarks/campaign_buffered/main_reordered.c'): arg = str(output / 'main.c')
        if arg == str(PARENT / 'distribution.c'): arg = str(output / 'distribution.c')
        if arg == str(PARENT / 'campaign.elf'): arg = str(output / 'campaign.elf')
        argv.append(arg)
    result = subprocess.run(argv, capture_output=True)
    (output / 'build.stdout').write_bytes(result.stdout); (output / 'build.stderr').write_bytes(result.stderr)
    if result.returncode: raise ValueError('Compute build failed; inspect preserved build.stderr')
    compiler = Path(argv[0]); nm = compiler.with_name('riscv64-unknown-elf-nm')
    table = subprocess.check_output([str(nm), '-S', '--defined-only', str(output / 'campaign.elf')], text=True)
    (output / 'symbols.txt').write_text(table)
    symbols = {}; objects = {}
    for line in table.splitlines():
        parts = line.split()
        if len(parts) in (3, 4): symbols[parts[-1]] = int(parts[0], 16)
        if len(parts) == 4 and parts[-1] in ('buffered_records', 'buffered_measurements_done', 'buffered_record_count', 'buffered_case_count'):
            objects[parts[-1]] = {'address': int(parts[0], 16), 'size': int(parts[1], 16)}
    if len(objects) != 4 or objects['buffered_records']['size'] != 1008 * 64:
        raise ValueError('Exact compute readback geometry required')
    bss_bytes = symbols['__bss_end'] - symbols['__bss_start']
    if not 0 < bss_bytes <= 131072: raise ValueError('Unrelated bulk BSS initialization remains')
    elf = output / 'campaign.elf'; raw = elf.read_bytes()
    phoff = struct.unpack_from('<Q', raw, 32)[0]; size, count = struct.unpack_from('<HH', raw, 54)
    sentinel = None
    for i in range(count):
        kind, flags, offset, va, pa, file_bytes, memory_bytes, align = struct.unpack_from('<IIQQQQQQ', raw, phoff + i * size)
        address = objects['buffered_measurements_done']['address']
        if kind == 1 and pa <= address and address + 8 <= pa + file_bytes:
            sentinel = int.from_bytes(raw[offset + address - pa:offset + address - pa + 8], 'little')
    if sentinel != (1 << 64) - 1: raise ValueError('Known file-backed completion sentinel required')
    layout = {'schema': 'iris.buffered_campaign_readback_layout.v1', 'elf_sha256': sha(elf), 'objects': objects,
        'fields': ['case_index', 'hart', 'start', 'end', 'instret', 'checksum', 'expected', 'pass'],
        'record_bytes': 64, 'records': 1008, 'stop_sentinel_initial_value': sentinel,
        'stop_sentinel_complete_value': 0, 'file_backed_initial_sentinel_verified': True,
        'intentional_debugger_stop_is_normal_guest_exit': False}
    (output / 'readback-layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    objdump = compiler.with_name('riscv64-unknown-elf-objdump')
    with (output / 'disassembly.txt').open('wb') as stream:
        subprocess.run([str(objdump), '-d', str(elf)], stdout=stream, check=True)
    (output / 'sections.txt').write_text(subprocess.check_output([str(objdump), '-h', str(elf)], text=True))
    paths = [Path(__file__).resolve(), PARENT / 'build.json', PARENT / 'corpus.json', PARENT / 'distribution.c',
        ROOT / 'benchmarks/campaign_buffered/main_reordered.c', parent_split, compiler, nm, objdump]
    paths += [Path(arg) for arg in argv if Path(arg).is_file() and not arg.endswith('campaign.elf')]
    paths += [p for p in output.iterdir() if p.suffix in ('.json', '.inc', '.h')]
    paths += list(HERE.glob('*.py')) + [ROOT / 'benchmarks/campaign_buffered/validate_priority.py']
    inputs = {**parent_build['input_sha256'], **{str(p): sha(p) for p in paths}}
    (output / 'inputs').mkdir()
    for name, digest in inputs.items(): (output / 'inputs' / digest).write_bytes(Path(name).read_bytes())
    report = {'schema': 'iris.compute_fitting_build.v1', 'argv': argv, 'input_sha256': inputs,
        'elf_sha256': sha(elf), 'corpus_sha256': sha(output / 'corpus.json'),
        'readback_layout_sha256': sha(output / 'readback-layout.json'),
        'kernel_preparation_and_measured_window_source_unchanged': True,
        'unchanged_kernel_source_sha256': hashlib.sha256(source[source.index(start):source.index(marker)].encode()).hexdigest(),
        'cases': 456, 'regions': 1008, 'trials': 3, 'semantic_parents': 152, 'bss_bytes': bss_bytes,
        'old_campaign_timings_applicable': False, 'new_exact_ELF_reference_required': True, 'hardware_contacted': False}
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('--output', type=Path, required=True)
    result = build(parser.parse_args().output.resolve())
    print(json.dumps({k: result[k] for k in ('elf_sha256', 'cases', 'regions', 'bss_bytes')}))
