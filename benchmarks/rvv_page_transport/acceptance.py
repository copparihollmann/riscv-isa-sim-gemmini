#!/usr/bin/env python3
"""Audit exact page diagnostic ELF/gates and reject corrupted real transcripts."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from validate import validate


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__);p.add_argument('--build', type=Path, required=True)
    p.add_argument('--gate', type=Path, action='append', required=True);p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); build = a.build.resolve(); out = a.output.resolve();out.mkdir(parents=True, exist_ok=False)
    proof = json.loads((build / 'build.json').read_text());corpus = json.loads((build / 'corpus.json').read_text())
    elf = build / 'probe.elf'
    assert sha(elf) == proof['elf_sha256'] and sha(build / 'corpus.json') == proof['corpus_sha256']
    identities = {str(Path(__file__).resolve()): sha(Path(__file__))}
    for name, expected in proof['input_sha256'].items():
        assert sha(name) == expected;identities[name] = expected
    seeds = set();gates = []
    for directory in a.gate:
        directory = directory.resolve();r = json.loads((directory / 'report.json').read_text())
        assert r['pass'] and r['proof']['regions'] == 2550 and r['elf_sha256'] == sha(elf)
        assert r['corpus_sha256'] == sha(build / 'corpus.json') and r['returncode'] == 0
        for name, expected in r['input_sha256'].items():
            assert sha(name) == expected;identities[name] = expected
        assert sha(directory / 'stdout') == r['stdout_sha256']
        validate((directory / 'stdout').read_text(), corpus)
        seeds.add(r['seed']);gates.append({'seed': r['seed'], 'report_sha256': sha(directory / 'report.json')})
    assert seeds == {0, 17}
    symbols = subprocess.check_output(['/usr/bin/readelf', '-sW', str(elf)], text=True)
    layout = {}
    for line in symbols.splitlines():
        f = line.split()
        if f and f[-1] in ('input_arena', 'output_arena'):
            assert int(f[2]) == 8192;layout[f[-1]] = int(f[1], 16)
    assert layout == {k: corpus['layout'][k] for k in ('input_arena', 'output_arena')}
    text = (a.gate[0] / 'stdout').read_text();lines = text.splitlines()
    first = next(i for i, s in enumerate(lines) if s.startswith('IRIS_REGION '))
    controls = []
    def refuse(name, modified, declared=corpus):
        try: validate('\n'.join(modified) + '\n', declared)
        except (ValueError, KeyError, TypeError): controls.append({'control': name, 'rejected': True})
        else: raise ValueError('Corrupted transcript was accepted: ' + name)
    for name, field, value in [('wrong_byte_checksum','checksum',1), ('wrong_golden','expected_checksum',1),
            ('wrong_input_page','input_address',corpus['layout']['input_arena']+288),
            ('wrong_output_page','output_address',corpus['layout']['output_arena']+288),
            ('wrong_split','bytes_before_page',32),('wrong_group','crossing_group',0),
            ('wrong_mode','mode',0),('wrong_pattern','pattern',1),('guard_overwrite','guards_preserved',False),
            ('wrong_hart','hart',1),('boolean_counter','instret_delta',True),('empty_region','end_cycle',0)]:
        changed = lines[:];row = json.loads(changed[first].split(' ',1)[1]);row[field] = value
        changed[first] = 'IRIS_REGION ' + json.dumps(row);refuse(name,changed)
    refuse('missing_region', lines[:first] + lines[first+1:])
    refuse('duplicate_region', lines[:first] + [lines[first]] + lines[first:])
    second = next(i for i in range(first+1,len(lines)) if lines[i].startswith('IRIS_REGION '))
    reordered = lines[:];reordered[first],reordered[second] = reordered[second],reordered[first];refuse('reordered_regions',reordered)
    refuse('guest_timeout', lines + ['IRIS_PROBE_TIMEOUT {}'])
    changed = [s for s in lines if not s.startswith('IRIS_BATCH_DONE ')]
    refuse('failed_completion',changed + ['IRIS_BATCH_DONE {"failed":1,"regions":2550}'])
    refuse('missing_begin',[s for i,s in enumerate(lines) if i != first-1])
    declared = copy.deepcopy(corpus);declared['cases'][0]['input_offset'] += 32;refuse('false_declared_geometry',lines,declared)
    declared = copy.deepcopy(corpus);declared['heldout'] = True;refuse('fitting_relabelled_holdout',lines,declared)
    refuse('missing_runtime_vlen',[s for s in lines if not s.startswith('IRIS_PAGE_HARTS ')])
    changed = ['IRIS_PAGE_HARTS {"vlenb":[32,32,64],"expected":32}' if s.startswith('IRIS_PAGE_HARTS ') else s for s in lines]
    refuse('wrong_hart2_runtime_vlen',changed)
    disassembly = (build / 'disassembly.txt').read_text()
    assert 'vsetvl\tzero,t0,t0' in disassembly and 'csrw\tvstart,t0' in disassembly and 'csrw\tvcsr,t0' in disassembly
    assert any(c['family']=='load' and c['crossing_group']==3 and c['bytes_before_page']==32 and c['input_offset']==0xce0 for c in corpus['cases'])
    assert any(c['family']=='load' and c['crossing_group']==2 and c['bytes_before_page']==224 and c['input_offset']==0xd20 for c in corpus['cases'])
    identities.update({str(build / name): sha(build / name) for name in ('build.json','corpus.json','probe.elf','disassembly.txt')})
    report = {'schema': 'iris.rvv_page_transport_acceptance.v1', 'pass': True, 'regions_per_seed': 2550,
        'gates': gates, 'elf_sha256': sha(elf), 'layout': corpus['layout'], 'negative_controls': controls,
        'original_ce0_and_minimal_d20_offsets_present': True,
        'closing_vsetvl_has_nonzero_rs1_register_containing_zero': True,
        'input_sha256': identities, 'hardware_contacted': False, 'timing_certified': False, 'calibration_usable': False}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'negative_controls': len(controls), 'report_sha256': sha(out / 'report.json')}))


if __name__ == '__main__': main()
