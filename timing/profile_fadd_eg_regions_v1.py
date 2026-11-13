#!/usr/bin/env python3
"""Model-only FADD utilization and Perfetto tracks from committed source events.

Physical memory traffic and FPGA utilization are not observed by this journal.
Only complete, independently checked measured regions receive work credit.
"""
import argparse
import bisect
import collections
import json
from pathlib import Path

from replay_rvv_compute_heldout_asm_v1 import ROOT, need, sha, verify_bindings
from iris_model.guest_regions import Instructions
from iris_model.report import symbols


def union(intervals, lower, upper):
    merged = []
    for begin, end in sorted((max(a, lower), min(b, upper)) for a, b in intervals if a < upper and b > lower):
        if begin >= end:
            continue
        if merged and begin <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([begin, end])
    return merged


def events(path):
    committed, front, canceled = {}, {}, set()
    issues, writes = collections.defaultdict(dict), collections.defaultdict(dict)
    tail = b''
    with path.open('rb') as stream:
        for line in stream:
            if not line.endswith(b'\n'):
                tail = line
                break
            row = json.loads(line)
            kind = row.get('event', '')
            if kind not in ('fadd_EG_front_reservation', 'fadd_EG_wrongpath_cancel',
                            'fadd_EG_functional_COM', 'fadd_EG_microissue', 'fadd_EG_physical_write'):
                continue
            key = row['hart'], row['generation']
            if kind == 'fadd_EG_front_reservation':
                need(key not in front, 'Unique source command reservation')
                front[key] = row
            elif kind == 'fadd_EG_wrongpath_cancel':
                need(key not in canceled, 'Unique canceled reservation')
                canceled.add(key)
            elif kind == 'fadd_EG_functional_COM':
                need(key not in committed, 'Unique architectural COM')
                committed[key] = row
            elif kind in ('fadd_EG_microissue', 'fadd_EG_physical_write'):
                bucket = issues if kind == 'fadd_EG_microissue' else writes
                need(row['index'] not in bucket[key], 'No duplicate work/publication credit')
                bucket[key][row['index']] = row
    need(not (set(committed) & canceled) and all(key in front for key in committed),
         'Only committed uncanceled commands get work credit')
    need(set(issues) == set(writes) == set(committed), 'All source work has architectural ownership')
    return committed, front, issues, writes, tail


def qualify(key, command, front, issues, writes, code):
    need(command.get('geometry_authority') == 'checked_architectural_COM'
         and command['new_flags'] == 0 and command['physical_VRF_restored'] is True,
         'Checked architectural geometry and actual private semantic COM')
    sew, vl, num, den = [command[name] for name in ('SEW', 'VL', 'LMUL_numerator', 'LMUL_denominator')]
    need(all(type(v) is int for v in (sew, vl, num, den)) and sew in (16, 32, 64)
         and num in (1, 2, 4, 8) and den == 1 and vl == 256 * num // sew,
         'Qualified compute128 full-VL geometry')
    word = command['raw']
    need(word == code.read(command['pc']) and word & 127 == 0x57 and word >> 26 == 0
         and (word >> 12) & 7 == 1 and (word >> 25) & 1 == 1,
         'Actual unmasked VFADD.VV instruction from this ELF')
    need((word >> 15) & 31 == command['vs1'] and (word >> 20) & 31 == command['vs2']
         and (word >> 7) & 31 == command['vd'], 'Exact ELF vector operands')
    expected = set(range(vl * sew // 128))
    need(set(issues) == set(writes) == expected, 'Every source element group actually issued and published')
    need(front['pc'] == command['pc'] and front['COM'] == command['cycle'], 'Actual command COM join')
    for index in expected:
        issue, write = issues[index], writes[index]
        need(issue['pc'] == write['pc'] == command['pc'] and issue['cycle'] >= command['cycle'] + 4
             and write['cycle'] == issue['cycle'] + 4 and write['bytes'] == 16,
             'Source four-stage write and exact16B numeric publication')
    return sew, vl


def main(args):
    run, build, out = [p.resolve() for p in (args.run, args.build, args.output)]
    need(not out.exists(), 'Fresh profile output required')
    receipt = json.loads((run / 'run.json').read_text())
    need(receipt['pass'] is True and receipt['regions'] == 1320
         and receipt['complete_per_element_goldens'] == 184128
         and receipt['actual_CSR_ELF_endpoint_joins'] == 3960, 'Complete actual model replay')
    verify_bindings(receipt['input_sha256'])
    verify_bindings(receipt['output_sha256'])
    journal = run / 'async.jsonl'
    need(receipt['output_sha256'].get(str(journal)) == sha(journal), 'Bound actual source-event bytes')
    corpus = json.loads((build / 'corpus.json').read_text())
    native = [json.loads(line) for line in (run / 'regions.jsonl').read_text().splitlines()]
    need([row['case_id'] for row in native] == [case['case_id'] for case in corpus['cases']],
         'Exact region/corpus identity order')
    elf, rom = build / 'guest.elf', ROOT / 'board/evidence/bootrom.rv64.img'
    code = Instructions(elf, rom)
    committed, front, issue, write, tail = events(journal)
    source = ROOT / 'build/rvv-fadd-EG-source-v4/report.json'
    need(sha(source) == '1ecf17755499a9c1add98af962412dd7fad61f4ee8cce09332ffeaa24d639a9d',
         'Exact source control differential witness')
    for key, command in committed.items():
        qualify(key, command, front[key], issue[key], write[key], code)
    nm = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm')
    names = symbols(elf, nm)
    starts = [row[0] for row in names]
    def function(pc):
        index = bisect.bisect_right(starts, pc) - 1
        return names[index][2] if index >= 0 and pc < names[index][1] else None
    by_hart = collections.defaultdict(list)
    for key, command in committed.items():
        by_hart[key[0]].append((command['cycle'], key))
    for rows in by_hart.values():
        rows.sort()
    times = {hart: [row[0] for row in rows] for hart, rows in by_hart.items()}
    profiles, trace, credited = [], [], set()
    base_hz = 500_000_000
    micros = lambda cycle: cycle * 1_000_000 / base_hz
    for hart in (0, 1):
        trace.append(dict(ph='M', pid=hart, tid=0, name='process_name', args=dict(name='hart ' + str(hart))))
    for case, row in zip(corpus['cases'], native):
        if case['kind'] != 'fp':
            continue
        hart = case['hart']
        lower, middle, upper = [row[name + '_global_read_cycle'] for name in ('begin', 'issue', 'drain')]
        span = upper - lower
        need(span > 0 and lower < middle <= upper, 'Actual shared-clock counter span')
        first, last = bisect.bisect_left(times[hart], lower), bisect.bisect_left(times[hart], upper)
        keys = [key for _, key in by_hart[hart][first:last]]
        need(len(keys) == case['n'] * case['streams'], 'All and only measured FADD commands')
        busy, inflight, pcs, issue_edges = [], [], set(), set()
        elements = 0
        for key in keys:
            need(key not in credited, 'No command credited to two regions')
            credited.add(key)
            command = committed[key]
            sew, vl = command['SEW'], command['VL']
            need(sew == case['sew'] and vl == case['vl'] and command['cycle'] < middle,
                 'Same actual dtype/shape and all FADD COM before issue-end CSR')
            elements += vl
            pcs.add(command['pc'])
            final = max(event['cycle'] for event in write[key].values())
            need(final < upper, 'All credited results published before final counter')
            inflight.append((command['cycle'], final + 1))
            for index, event in issue[key].items():
                tick, end = event['cycle'], write[key][index]['cycle']
                need(lower <= tick < end < upper, 'Measured source issue/write edges fully contained')
                need(tick not in issue_edges, 'At most one accepted EG per compute-hart source edge')
                issue_edges.add(tick)
                # At issue E the source four-stage valid pipeline advances;
                # its preedge valid stages cover E+1 through write E+4.
                busy.append((tick + 1, end + 1))
            trace.append(dict(ph='X', pid=hart, tid=1, name='FADD command pending',
                              ts=micros(command['cycle']), dur=micros(final + 1-command['cycle']),
                              args=dict(generation=key[1], pc=hex(command['pc']), function=function(command['pc']),
                                        SEW=sew, VL=vl)))
        pipeline = union(busy, lower, upper)
        pending = union(inflight, lower, upper)
        peak = 128 // case['sew']
        busy_cycles = sum(end - begin for begin, end in pipeline)
        need(elements == len(issue_edges) * peak and 0 <= busy_cycles <= span,
             'Exact logical work and bounded union utilization')
        record = dict(case_id=case['case_id'], hart=hart, SEW=case['sew'], LMUL=case['lmul'],
                      measured_commands=len(keys), logical_add_elements=elements,
                      source_global_CSR_span_cycles=span, program_mcycle_delta=row['end_cycle']-row['start_cycle'],
                      source_pipeline_valid_cycles=busy_cycles, source_pipeline_valid_fraction=busy_cycles/span,
                      command_pending_union_cycles=sum(b-a for a, b in pending),
                      source_EG_issue_slots=len(issue_edges), achieved_elements_per_source_cycle=elements/span,
                      conditional_peak_elements_per_source_cycle=peak,
                      fraction_of_conditional_element_peak=elements/(span*peak),
                      internal_VRF_numeric_write_bytes=len(issue_edges)*16,
                      logical_vector_source_operand_bytes=len(issue_edges)*32,
                      functions=sorted({function(pc) for pc in pcs if function(pc) is not None}),
                      physical_memory_bytes=None, physical_memory_bandwidth=None,
                      physical_memory_roofline_intensity=None, additive_CPU_stall_breakdown=None)
        profiles.append(record)
        trace.append(dict(ph='X', pid=hart, tid=0, name=case['case_id'], ts=micros(lower), dur=micros(span),
                          args=record))
        for begin, end in pipeline:
            trace.append(dict(ph='X', pid=hart, tid=2, name='FADD source pipeline valid',
                              ts=micros(begin), dur=micros(end-begin)))
    need(len(profiles) == 432, 'Every measured FADD region retained')
    out.mkdir(parents=True)
    (out / 'regions.json').write_text(json.dumps(profiles, indent=2) + '\n')
    (out / 'trace.json').write_text(json.dumps(dict(traceEvents=trace, displayTimeUnit='ns')) + '\n')
    inputs = [Path(__file__).resolve(), ROOT / 'timing/replay_rvv_compute_heldout_asm_v1.py',
              run / 'run.json', run / 'regions.jsonl', journal, build / 'corpus.json', elf, rom, source, nm]
    report = dict(schema='iris.FADD_source_EG_region_profile.v1', **{'pass': True}, regions=432,
                  measured_committed_commands=len(credited), source_clock_hz=base_hz,
                  hardware_timing_labels_opened=False, hardware_utilization_observed=False,
                  source_image_association_verified=False, timing_accuracy_certified=False,
                  source_pipeline_scope='Union of actual issued four-stage valid entries; not callback occupancy or command age',
                  trace_tail_bytes_unterminated=len(tail), global_event_stream_complete=not tail,
                  selected_FADD_regions_complete=True,
                  memory_scope='Internal16B VRF publications and logical operands; not physical memory traffic or a DRAM roofline',
                  command_scope='Only checked architectural COMs with all EG publications; wrongpath/warmup never get measured work credit',
                  CPU_COMplus1_bridge_qualified=False,
                  input_sha256={str(path): sha(path) for path in inputs},
                  output_sha256={path.name: sha(path) for path in out.iterdir()})
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(pass_=True, regions=432, commands=len(credited), trace_tail_bytes=len(tail))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    for name in ('run', 'build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
