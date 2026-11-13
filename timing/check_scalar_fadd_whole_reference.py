#!/usr/bin/env python3
"""Independently check bounded saved-SoC FADD observations, never fit them."""
import argparse
import collections
import copy
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def image(path):
    """Read only file-backed PT_LOAD bytes; no objdump/decode oracle needed."""
    data = path.read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    entsize, count = struct.unpack_from('<HH', data, 54)
    segments = []
    for i in range(count):
        typ, flags, offset, va, pa, filesz, memsz, align = struct.unpack_from(
            '<IIQQQQQQ', data, phoff + i * entsize)
        if typ == 1:
            segments.append((va, data[offset:offset + filesz]))

    def word(pc):
        for va, contents in segments:
            if va <= pc and pc + 4 <= va + len(contents):
                return int.from_bytes(contents[pc - va:pc - va + 4], 'little')
        raise ValueError('PC outside file-backed ELF instruction bytes')
    return word


def read_events(path):
    events = []
    for line in path.read_text().splitlines():
        if line.startswith('SCALAR_RTL_') and ' {' in line:
            kind, payload = line.split(' ', 1)
            events.append((kind, json.loads(payload)))
    require('SCALAR_RTL_OBSERVER_DONE moves=9 counters=36' in path.read_text(),
            'exact observer terminal record')
    return events


def validate(events, elf_word):
    grouped = collections.defaultdict(list)
    last_edge = {}
    unique = set()
    checks = 0
    for kind, row in events:
        h = row['hart']
        require(h in (0, 1, 2) and row['edge'] > 2000, 'actual post-reset hart edge')
        key = kind, h
        require(row['edge'] >= last_edge.get(key, 0), 'monotonic event edges')
        last_edge[key] = row['edge']
        identity = kind, h, row['edge']
        require(identity not in unique, 'duplicate physical event')
        unique.add(identity)
        if 'raw' in row:
            require(elf_word(row['pc']) == row['raw'], 'exact instruction PC/raw ELF bytes')
            checks += 1
        grouped[key].append(row)
    report = []
    for h in range(3):
        ex = grouped['SCALAR_RTL_EX', h]
        writes = {x['edge']: x for x in grouped['SCALAR_RTL_WRITE', h]}
        counters = grouped['SCALAR_RTL_COUNTER', h]
        readouts = grouped['SCALAR_RTL_READOUT', h]
        require(len(ex) == 96 and len(counters) == 12 and len(readouts) == 3,
                'all96 accepts/12 counter reads/3 numerical outputs per hart')
        require(len({x['cycle'] for x in ex}) == 96, 'unique actual core-cycle accepts')
        for w, fmt in enumerate((2, 0, 1)):
            body = [x for x in ex if x['raw'] >> 25 == fmt]
            require(len(body) == 32, '32 independent source FADD accepts per width')
            require(len({x['pc'] for x in body}) == 1, 'actual counted-loop FADD PC')
            latency = 4 if h < 2 else 3
            write_to_next = collections.Counter()
            for j, row in enumerate(body):
                require((row['raw'] & 0xfe00007f) in (0x53, 0x02000053, 0x04000053),
                        'finite H/S/D FADD encoding')
                require(((row['raw'] >> 7) & 31) == 0 and
                        ((row['raw'] >> 15) & 31) == 0 and
                        ((row['raw'] >> 20) & 31) == 1,
                        'actual ft0 <- ft0 + ft1 dependency')
                physical = writes.get(row['edge'] + latency)
                require(physical is not None and physical['rd'] == 0,
                        'actual matching physical FPR write at source latency')
                require(physical['rf0_before'] == row['rf0_before'],
                        'RF holds accepted old operand until the matching write edge')
                require(row['operand1'] == row['rf0_before'],
                        'actual physical operand reads current FPR value')
                if h < 2:
                    require(row['ready0_before'] == 1 and physical['ready0_before'] == 0,
                            'Shuttle pre-edge scoreboard ready/held until actual write')
                if j:
                    older = body[j - 1]
                    require(row['cycle'] - older['cycle'] == row['edge'] - older['edge'],
                            'observed source edges equal independent uninhibited core counter progression')
                    gap = row['edge'] - (older['edge'] + latency)
                    require(gap >= 1, 'no same-edge old-FPR write/read acceptance')
                    require(row['rf0_before'] != older['rf0_before'],
                            'next accepted operand sees prior numerical result')
                    write_to_next[gap] += 1
                checks += 8 if h < 2 else 7
            require(write_to_next[1] > 0, 'actual shortest WRITE+1 dependent-EX witness')
            cs = counters[4 * w:4 * w + 4]
            require([x['csr'] for x in cs] == [0xb00, 0xb02, 0xb00, 0xb02],
                    'actual measured mcycle/minstret boundary order')
            require(cs[0]['edge'] < body[0]['edge'] <= body[-1]['edge'] < cs[2]['edge'],
                    'accepted source operations inside exact counter region')
            cycle_count = cs[2]['value'] - cs[0]['value']
            instret = cs[3]['value'] - cs[1]['value']
            require(instret == (98 if h < 2 else 99), 'exact independently derived loop instret')
            require(cycle_count > 0, 'positive measured region')
            output = readouts[w]
            require((output['raw'] & 0xfff0707f) == (0xe4000053, 0xe0000053, 0xe2000053)[w],
                    'actual width-specific FMV scalar output')
            require(output['bits'] == (0x5000, 0x42000000, 0x4040000000000000)[w],
                    'independent exact IEEE representation of integer32')
            report.append(dict(hart=h, width=(16, 32, 64)[w], rtl_cycles=cycle_count,
                               rtl_instret=instret, accepted_fadds=32,
                               source_latency=latency,
                               write_to_next_EX_gaps=dict(sorted(write_to_next.items())),
                               mathematical_readout=output['bits']))
            checks += 8
    return report, checks


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--native-dep-report', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    run = json.loads((a.run / 'run.json').read_text())
    require(run['exit_status'] == 0 and not run['timed_out'] and run['inputs_unchanged'],
            'bounded observer completed without input changes')
    for name, digest in run['input_sha256'].items():
        require(sha(name) == digest, 'run input byte binding')
    require(sha(a.run / 'stderr') == run['stderr_sha256'], 'raw stderr binding')
    elf = Path(run['argv'][-1])
    word = image(elf)
    events = read_events(a.run / 'stderr')
    rows, checks = validate(events, word)
    native = json.loads(a.native_dep_report.read_text())
    require(native['pass'] and native['input_sha256'][str(elf)] == sha(elf),
            'native comparison is actual identical ELF')
    values = {(r['hart'], r['width']): r for r in native['regions']}
    for row in rows:
        n = values[row['hart'], row['width']]
        require(n['instret'] == row['rtl_instret'], 'same retired dynamic region instruction count')
        row['native_cycles'] = n['cycles']
        row['signed_error_percent'] = 100 * (n['cycles'] / row['rtl_cycles'] - 1)
    mutations = []
    for name in ('missing_accept', 'early_write', 'same_edge_consumer', 'operand_corruption',
                 'scoreboard_corruption', 'wrong_readout', 'wrong_instret', 'foreign_PC',
                 'duplicate_accept', 'missing_counter'):
        v = copy.deepcopy(events)
        def first(kind, hart=0):
            return next(i for i, (k, x) in enumerate(v) if k == kind and x['hart'] == hart)
        i = first('SCALAR_RTL_EX')
        if name == 'missing_accept':
            v.pop(i)
        elif name == 'early_write':
            edge = v[i][1]['edge'] + 4
            j = next(j for j, (k, x) in enumerate(v) if k == 'SCALAR_RTL_WRITE' and x['hart'] == 0 and x['edge'] == edge)
            v[j][1]['edge'] -= 1
        elif name == 'same_edge_consumer':
            indices = [j for j, (k, x) in enumerate(v) if k == 'SCALAR_RTL_EX' and x['hart'] == 0]
            v[indices[1]][1]['edge'] = v[indices[0]][1]['edge'] + 4
        elif name == 'operand_corruption':
            v[i][1]['operand1'][0] ^= 1
        elif name == 'scoreboard_corruption':
            v[i][1]['ready0_before'] = 0
        elif name == 'wrong_readout':
            v[first('SCALAR_RTL_READOUT')][1]['bits'] ^= 1
        elif name == 'wrong_instret':
            indices = [j for j, (k, x) in enumerate(v) if k == 'SCALAR_RTL_COUNTER' and x['hart'] == 0]
            v[indices[3]][1]['value'] += 1
        elif name == 'foreign_PC':
            v[i][1]['pc'] += 2
        elif name == 'duplicate_accept':
            v.insert(i + 1, copy.deepcopy(v[i]))
        else:
            v.pop(first('SCALAR_RTL_COUNTER'))
        try:
            validate(v, word)
        except (ValueError, IndexError, KeyError) as e:
            mutations.append(dict(name=name, rejected=True, reason=str(e)))
        else:
            raise ValueError('accepted corruption: ' + name)
    bindings = {str(p.resolve()): sha(p) for p in
                (a.run / 'run.json', a.run / 'stderr', a.run / 'stdout',
                 a.native_dep_report, Path(__file__), elf)}
    r = dict(schema='iris.scalar_fadd_independent_whole_saved_RTL_phase_proof.v1',
             status='qualified_finite_phase_numeric_and_counter_comparison',
             input_sha256=bindings, checks=checks, accepted_source_fadds=288,
             mathematical_outputs=9, regions=rows, corruption_controls=mutations,
             all_ten_corruptions_rejected=True, hardware_contacted=False,
             normal_guest_exit_claimed=False, timing_parameters_fitted=False,
             full_timing_certified=False, full_four_state_definedness_available=False,
             source_image_association_verified=False,
             source_FIR_sha256=run['source_FIR_sha256'],
             counter_scope='actual source CSR-retire pre-edge values; same ELF and dynamic instret',
             reset_scope='actual reset gating; no unreset-prefix FPR write claims',
             observation_scope='stop after9 retired numerical readouts and36 CSR reads; before UART',
             unmodeled_scope=['whole native memory/frontend timing equivalence',
                              'shared scalar/vector CP arbitration', 'exact IRQ delivery phase',
                              'other scalar FP operations', 'deployed FireSim image equivalence'])
    (out / 'report.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(dict(status=r['status'], checks=checks, corruptions=len(mutations),
                          report_sha256=sha(out / 'report.json'))))


if __name__ == '__main__':
    main()
