#!/usr/bin/env python3
"""Replay the written-entry ledger of a bounded actual whole-CPU capture."""
import argparse
import copy
import hashlib
import json
import re
import struct
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse(text):
    return [json.loads(line.split(' ', 1)[1]) for line in text.splitlines()
            if line.startswith('WHOLE_RAS {')]


def validate(rows):
    known = [0, 0]
    last_edge = [0, 0]
    read_count = [0, 0]
    write_count = [0, 0]
    witnesses = []
    for row in rows:
        h = row['hart']
        require(h in (0, 1), 'actual Shuttle hart')
        require(row['edge'] > last_edge[h], 'one observed edge event per hart')
        last_edge[h] = row['edge']
        require(row['known_before'] == known[h], 'continuous prior-write ledger; no state reinjection')
        require(row['head'] < 8 and row['write_index'] < 8, 'source3-bit index widths')
        selected = row['head'] if row['head'] < 6 else 0
        unknown = row['required_read'] and not (known[h] & (1 << selected))
        require(bool(row['unwritten_read']) == bool(unknown), 'pre-edge read checks prior writes only')
        read_count[h] += int(row['required_read'])
        if unknown:
            witnesses.append(row)
        if row['write'] and row['write_index'] < 6:
            known[h] |= 1 << row['write_index']
            write_count[h] += 1
    return dict(actual_events=len(rows), actual_required_reads=read_count,
                actual_writes=write_count, final_written_masks=known,
                last_observed_RAS_event_source_edges=last_edge,
                independently_replayed_unwritten_reads=witnesses)


def elf_word_reader(path):
    data = path.read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01', 'actual ELF64 little endian')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    entry_size, count = struct.unpack_from('<HH', data, 54)
    segments = []
    for i in range(count):
        typ, flags, off, va, pa, filesz, memsz, align = struct.unpack_from(
            '<IIQQQQQQ', data, phoff + entry_size * i)
        if typ == 1:
            segments.append((va, data[off:off + filesz]))

    def word(pc):
        for va, contents in segments:
            if va <= pc and pc + 4 <= va + len(contents):
                return int.from_bytes(contents[pc - va:pc - va + 4], 'little')
        raise ValueError('actual COM PC outside file-backed ELF')
    return word


def check_commits(commits, word, expansions):
    for row in commits:
        raw = word(row['pc'])
        expanded = raw if raw & 3 == 3 else expansions[(raw & 3) * 16384 + ((raw & 65535) >> 2)]
        require(expanded == row['raw'], 'actual committed instruction agrees with exact ELF/source RVC expansion')
    return len(commits)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    run_path = a.run / 'run.json'
    receipt = json.loads(run_path.read_text())
    require(receipt['status'] != 'running', 'run must close before qualification')
    require(receipt['inputs_unchanged'], 'actual launch inputs unchanged')
    for name, digest in receipt['input_sha256'].items():
        require(sha(name) == digest, 'actual launch bytes bound')
    for name in ('stdout', 'stderr'):
        require(sha(a.run / name) == receipt[name + '_sha256'], 'raw result bound')
    raw = (a.run / 'stderr').read_text()
    rows = parse(raw)
    checked = validate(rows)
    root = Path(__file__).resolve().parents[1]
    table_path = root / 'pipeline/fast_source_rvc_table.hpp'
    table = table_path.read_text().split('compressed_expansions={', 1)[1].split('};', 1)[0]
    expansions = [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)u', table)]
    require(len(expansions) == 49152, 'complete exact saved-source compressed expansion table')
    elf = Path(receipt['argv'][-1])
    word = elf_word_reader(elf)
    commits = [json.loads(line.split(' ', 1)[1]) for line in raw.splitlines()
               if line.startswith('WHOLE_RAS_COM_TAIL {')]
    coherent_commits = check_commits(commits, word, expansions)
    require(len(checked['independently_replayed_unwritten_reads']) ==
            len(receipt['unwritten_RAS_witnesses']), 'actual terminal witness agrees with independent reader')
    mutations = []
    if rows:
        for name in ('injected_known_mask', 'flipped_unwritten_predicate', 'duplicated_edge'):
            v = copy.deepcopy(rows)
            if name == 'injected_known_mask':
                v[0]['known_before'] ^= 1
            elif name == 'flipped_unwritten_predicate':
                v[0]['unwritten_read'] = not v[0]['unwritten_read']
            else:
                v.insert(1, copy.deepcopy(v[0]))
            try:
                validate(v)
            except ValueError as e:
                mutations.append(dict(name=name, rejected=True, reason=str(e)))
            else:
                raise ValueError('accepted corrupted RAS observation')
    if commits:
        bad = copy.deepcopy(commits)
        bad[0]['raw'] ^= 1
        try:
            check_commits(bad, word, expansions)
        except ValueError as e:
            mutations.append(dict(name='corrupted_actual_COM_instruction', rejected=True, reason=str(e)))
        else:
            raise ValueError('accepted corrupted architectural instruction')
    causal = []
    for witness in checked['independently_replayed_unwritten_reads']:
        previous = next((r for r in rows if r['hart'] == witness['hart'] and
                         r['edge'] == witness['edge'] - 1), None)
        require(previous is not None and previous['call_activity'] and
                previous['next_head'] == witness['head'] and witness['write'] and
                witness['write_index'] == witness['head'] and not witness['repair'],
                'actual prior call and simultaneous too-late source write')
        call = word(previous['pc'])
        ret = word(witness['pc'])
        expanded_return = ret if ret & 3 == 3 else expansions[(ret & 3) * 16384 + ((ret & 65535) >> 2)]
        require(call & 127 == 0x67 and call & 0x80 and
                expanded_return & 127 == 0x67 and not expanded_return & 0x80,
                'actual source-decoded false-call bytes and real return bytes')
        causal.append(dict(hart=witness['hart'], call_edge=previous['edge'],
                           call_packet_pc=previous['pc'], call_word_from_ELF=call,
                           call_head_before=previous['head'], next_head=previous['next_head'],
                           required_return_edge=witness['edge'],
                           return_packet_pc=witness['pc'], return_halfword=ret & 65535,
                           simultaneous_pending_write_index=witness['write_index'],
                           written_mask_before_return=witness['known_before']))
    bindings = {str(p.resolve()): sha(p) for p in
                (run_path, a.run / 'stdout', a.run / 'stderr', Path(__file__), table_path, elf,
                 root / 'build/fast-source-rvc-v1/stdout')}
    r = dict(schema='iris.merlin_RAS_independent_whole_CPU_observation.v1',
             status='finite_actual_whole_CPU_unwritten_read_observed' if
             checked['independently_replayed_unwritten_reads'] else
             'bounded_whole_CPU_prefix_no_unwritten_read_observed',
             input_sha256=bindings, observation=checked, corruption_controls=mutations,
             exact_ELF_RVC_coherent_actual_COM_tail_instructions=coherent_commits,
             independently_reconstructed_causal_pairs=causal,
             exact_ELF_sha256=sha(Path(receipt['argv'][-1])),
             source_FIR_sha256=receipt['source_FIR_sha256'],
             last_progress=receipt['last_progress'], host_seconds=receipt['host_seconds'],
             hardware_contacted=False, source_image_association_verified=False,
             normal_guest_exit_claimed=False, full_four_state_definedness_available=False,
             writtenness_not_full_payload_definedness=True,
             source_control_scope='actual CPU/frontend/memory target RTL ports/state; no recorded CPU input reinjection',
             equivalence_limit='source pins and ELF identities bound; memory/preload/clock harness distinct from Ethan FireSim image',
             causality_limit='a bounded prefix without the relevant read cannot disprove later whole-CPU reachability',
             timing_certified=False, full_goal_complete=False)
    (out / 'report.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(dict(status=r['status'], report_sha256=sha(out / 'report.json'),
                          actual_events=len(rows))))


if __name__ == '__main__':
    main()
