#!/usr/bin/env python3
"""Independent absolute-event and physical-coordinate oracle for column history."""
import argparse
import collections
import copy
import hashlib
import json
import re
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse(text):
    cases = {}
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        k = tokens[0]
        v = list(map(int, tokens[1:]))
        if k == 'CASE':
            identity, policy, start, count = v
            require(identity not in cases, 'unique case identity')
            cases[identity] = dict(policy=policy, start=start, count=count, issues=[], writes=[], dispatches=[])
        elif k in ('ISSUE', 'WRITE', 'DISPATCH'):
            require(v[0] in cases, 'event follows case boundary')
            cases[v[0]][{'ISSUE': 'issues', 'WRITE': 'writes', 'DISPATCH': 'dispatches'}[k]].append(v[1:])
        elif k == 'END':
            require('end' not in cases[v[0]], 'unique completion')
            cases[v[0]]['end'] = v[1]
            cases[v[0]]['completed_writes'] = v[2]
        else:
            raise ValueError('Unexpected actual component output')
    return cases


def available(policy, relative_edge):
    return (True if policy == 0 else relative_edge % 2 == 0 if policy == 1 else
            relative_edge % 5 < 2 if policy == 2 else relative_edge % 7 not in (1, 2, 3))


def cell_value(control, physical_cluster_row, physical_cluster_col):
    if control is None:
        tile = subrow = subcol = scalar = iteration = 0
    else:
        cmd, group = control
        tile = cmd['tile']
        scalar = cmd['index'] // 4 % 4
        iteration = group % 4
        subrow, subcol = ((group // 4, cmd['index'] // 16) if cmd['column'] else
                         (cmd['index'] // 16, group // 4))
    row = 16 * subrow + scalar * 4 + physical_cluster_row
    col = 16 * subcol + iteration * 4 + physical_cluster_col
    return tile * 0x10000 + row * 64 + col


def expected(case, scenario):
    start, end = case['start'], case['end']
    commands = scenario['commands']
    current = None
    dispatched = 0
    ordinal = 0
    reserved_writes = set()
    issues = []
    dispatches = []
    # Source PipeScheduler reservations are expressed as absolute write edges.
    for t in range(start, end):
        fire = False
        if current is not None:
            cmd = commands[current]
            due = t + 6 - cmd['index'] % 4
            fire = available(scenario['availability_policy'], t - start) and due not in reserved_writes
            if fire:
                issues.append([t, current, ordinal, cmd['column'], cmd['tile'], cmd['index'], cmd['vd']])
                reserved_writes.add(due)
        can_dispatch = current is None or fire and ordinal == 7
        if can_dispatch and dispatched < len(commands):
            dispatches.append([t, dispatched])
            current = dispatched
            dispatched += 1
            ordinal = 0
        elif fire:
            if ordinal == 7:
                current = None
            else:
                ordinal += 1
    require(dispatched == len(commands), 'all commands causally dispatched')
    require(len(issues) == 8 * len(commands), 'eight actual groups per command')
    by_issue = {}
    captures = {}
    writes = {}
    shifts = collections.defaultdict(set)
    for t, command_index, group, column, tile, index, vd in issues:
        cmd = commands[command_index]
        require(t not in by_issue, 'single configured OPU issue port')
        by_issue[t] = cmd, group
        depth = 5 - index % 4
        require(t + depth not in captures and t + depth + 1 not in writes, 'source readout reservation excludes write collisions')
        captures[t + depth] = command_index, group
        writes[t + depth + 1] = command_index, group
        if not column:
            for cluster in range(index % 4 + 1, 4):
                shifts[t + cluster - index % 4].add(cluster)
    # Architectural tile coordinates differ from physical cell/cluster layout.
    # This oracle carries physical data down the vertical pipeline continuously;
    # it consumes no observed RTL queue, controls, state, or array outputs.
    pipe = [[cell_value(None, r, c) for c in range(4)] for r in range(4)]
    backend_readout = None
    actual_writes = []
    for t in range(start, end):
        if t in writes:
            command_index, group = writes[t]
            require(backend_readout is not None, 'source capture precedes actual VRF write')
            cmd = commands[command_index]
            actual_writes.append([t, (2 * cmd['vd'] + group) % 64, *backend_readout])
        if t in captures:
            backend_readout = pipe[3][:]
        old = pipe
        control = by_issue.get(t - 1)  # Backend unconditional control register.
        pipe = [[old[r - 1][c] if r in shifts[t - 1] else cell_value(control, r, c)
                 for c in range(4)] for r in range(4)]
    return issues, dispatches, actual_writes


def check(cases, scenarios):
    require(set(cases) == {s['id'] for s in scenarios}, 'exact scenario identity set')
    checks = 0
    per_case = []
    for scenario in scenarios:
        c = cases[scenario['id']]
        require(c['policy'] == scenario['availability_policy'] and c['count'] == len(scenario['commands']), 'actual external stimulus identity')
        issues, dispatches, writes = expected(c, scenario)
        require(c['issues'] == issues, 'continuous issue timing derives from external availability plus source reservations')
        require(c['dispatches'] == dispatches, 'source tail/dispatch replacement edges')
        require(c['writes'] == writes, 'source pipeline/readout physical data and actual VRF write edges')
        require(c['completed_writes'] == len(writes), 'bounded complete readout drain')
        checks += len(issues) + len(dispatches) + 6 * len(writes)
        per_case.append(dict(id=scenario['id'], writes=len(writes), issues=len(issues)))
    return checks, per_case


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    build = a.build.resolve()
    receipt = json.loads((build / 'build.json').read_text())
    run = json.loads((build / 'run.json').read_text())
    require(run['exit_status'] == 0, 'actual model process succeeded')
    for name, digest in receipt['input_sha256'].items():
        require(sha(name) == digest, 'exact source/model/consumer input unchanged')
    require(sha(build / 'check') == receipt['binary_sha256'], 'actual consumer binary identity')
    require(sha(build / 'stdout') == run['stdout_sha256'], 'actual raw trace identity')
    scenarios = json.loads((build / 'scenarios.json').read_text())
    cases = parse((build / 'stdout').read_text())
    checks, per_case = check(cases, scenarios)
    require('physical_words_initialized=4096 physical_words_scanned=4096' in (build / 'stderr').read_text(), 'all physical matrix words initialized and independently scanned before consuming readout')
    terminal = re.search(r'VME_COLUMN_HISTORY_DONE cases=(\d+) edges=(\d+).*backend_SV_register_checks=(\d+)',
                         (build / 'stderr').read_text())
    require(terminal is not None and int(terminal[1]) == len(cases), 'actual completed exact-Backend-register differential run')
    require(int(terminal[3]) > 1000000, 'actual control/capture source-register phase comparisons')
    known_captures = re.search(r'backend_known_readout_checks=(\d+) backend_unqualified_capture_checks=(\d+)',
                               (build / 'stderr').read_text())
    require(known_captures is not None and int(known_captures[1]) == sum(len(c['writes']) * 4 for c in cases.values()),
            'every consumed word has an actual initialized-array source capture')
    # The closed form is checked only on the isolated contiguous column subset.
    closed_form_checks = 0
    for s in scenarios:
        if len(s['commands']) != 1 or s['availability_policy'] != 0 or not s['commands'][0]['column']:
            continue
        cmd = s['commands'][0]
        for group, write in enumerate(cases[s['id']]['writes']):
            q = group + 3 - cmd['index'] % 4
            wanted = ([cmd['tile'] * 0x10000 +
                       (q // 4 * 16 + (cmd['index'] // 4 % 4) * 4 + 3) * 64 +
                       (cmd['index'] // 16) * 16 + (q % 4) * 4 + lane for lane in range(4)]
                      if q < 8 else [192 + lane for lane in range(4)])
            require(write[2:] == wanted, 'source-derived isolated contiguous special case')
            closed_form_checks += 4
    pairs = collections.defaultdict(dict)
    for s in scenarios:
        if len(s['commands']) == 1 and s['commands'][0]['column']:
            cmd = s['commands'][0]
            pairs[cmd['tile'], cmd['index']][s['availability_policy']] = cases[s['id']]['writes']
    changed = []
    for (tile, index), v in pairs.items():
        baseline = [row[2:] for row in v[0]]
        for policy in range(1, 4):
            alternative = [row[2:] for row in v[policy]]
            if alternative != baseline:
                changed.append(dict(tile=tile, index=index, availability_policy=policy,
                                    differing_words=sum(x != y for a, b in zip(baseline, alternative) for x, y in zip(a, b))))
    require(len(changed) > 0, 'actual same instruction/index data changes under external backpressure')
    mutants = []
    for name in ('corrupt_write_data', 'early_write', 'missing_issue', 'injected_issue', 'missing_case'):
        v = copy.deepcopy(cases)
        if name == 'corrupt_write_data':
            v[512]['writes'][0][2] ^= 1
        elif name == 'early_write':
            v[512]['writes'][0][0] -= 1
        elif name == 'missing_issue':
            v[512]['issues'].pop(0)
        elif name == 'injected_issue':
            v[512]['issues'][0][0] += 1
        else:
            del v[512]
        try:
            check(v, scenarios)
        except ValueError as e:
            mutants.append(dict(name=name, rejected=True, reason=str(e)))
        else:
            raise ValueError('accepted corruption')
    inputs = {str(q): sha(q) for q in (Path(__file__), build / 'build.json', build / 'run.json',
              build / 'stdout', build / 'stderr', build / 'scenarios.json')}
    result = dict(schema='iris.vme_column_history_independent_component_proof.v1', status='qualified_finite_history_dependent_column_readout',
                  input_sha256=inputs, cases=len(cases), checks=checks, actual_edges=int(terminal[2]),
                  exact_extracted_Backend_SV_register_differential_checks=int(terminal[3]),
                  known_readout_capture_word_checks=int(known_captures[1]),
                  unqualified_reset_prefix_concrete_comparisons=int(known_captures[2]),
                  inactive_control_comparisons_are_not_reset_knownness_claims=True,
                  full_four_state_definedness_available=False,
                  known_physical_matrix_words_initialized_and_scanned=4096,
                  source_special_case_formula_word_checks=closed_form_checks,
                  same_instruction_external_availability_changes=changed,
                  corruption_controls=mutants, all_target_RTL_objects_unchanged=True,
                  actual_source_generated_sequencer_and_whole_array=True,
                  backend_registers_source_transcribed=True, full_Backend_VRF_arbitration_modeled=False,
                  external_boundary='explicit fixed write-port availability fixtures; no observed waiting/free/state inputs',
                  hidden_state_initialization=False, hardware_contacted=False,
                  universal_architectural_column_semantics_claimed=False,
                  functional_Spike_column_model_changed=False, timing_fitted=False,
                  source_image_association_verified=False)
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status=result['status'], checks=checks, cases=len(cases),
                          backpressure_changes=len(changed), report_sha256=sha(out / 'report.json'))))


if __name__ == '__main__':
    main()
