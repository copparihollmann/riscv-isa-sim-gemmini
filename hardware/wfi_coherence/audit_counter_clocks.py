#!/usr/bin/env python3
"""Associated all-three-hart CSR clock/WFI relations, with strict scope."""
import argparse
import json
import re
from pathlib import Path

from audit import EXPECTED, ROOT, SV, compact, sha

PARENT = ROOT / 'build/WFI-vector-clock-source-closure-v2/report.json'
PARENT_SHA = '05ded65debbe9e5a3207f0b7be8cf4b5433e7bf9be178803c49a1b46fc85b96a'
COUNTER_EXPRESSIONS = [
    'wire x10 = ~io_csr_stall;',
    "wire [5:0] _GEN_6 = {{5'd0}, x10};",
    'wire [6:0] nextSmall_1 = small_1 + _GEN_6;',
    "wire [6:0] _GEN_2 = ~reg_mcountinhibit[0] ? nextSmall_1 : {{1'd0}, small_1};",
    'always @(posedge io_ungated_clock) begin',
    'assign io_time = {large_1,small_1};',
    'assign io_csr_stall = reg_wfi | io_status_cease;',
    'wire [63:0] pending_interrupts = _GEN_7 & reg_mie;',
    "end else if (|pending_interrupts | exception) begin reg_wfi <= 1'h0;",
]


def check(text):
    text = compact(text)
    for expr in COUNTER_EXPRESSIONS:
        if expr not in text:
            raise ValueError('Changed counter/wakeup source: ' + expr)


def main(output):
    if sha(PARENT) != PARENT_SHA or sha(SV) != EXPECTED:
        raise ValueError('Associated source or parent receipt changed')
    modules = {m.group(1): m.group() + '\n' for m in re.finditer(
        r'^module\s+(\w+)[\s\S]*?^endmodule', SV.read_text(), re.M)}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'source').mkdir()
    bindings = {}
    for core, csr, harts in [('ShuttleCore', 'CSRFile', [0, 1]), ('Rocket', 'CSRFile_2', [2])]:
        text = compact(modules[core])
        if f'{csr} csr (' not in text or 'assign csr_io_ungated_clock = clock;' not in text:
            raise ValueError('Actual core/CSR clock binding changed')
        check(modules[csr])
        (output / 'source' / (csr + '.sv')).write_text(modules[csr])
        bindings[core] = {'hart_ids': harts, 'actual_CSR_module': csr,
                          'ungated_clock_binding': 'clock',
                          'module_sha256': sha(output / 'source' / (csr + '.sv'))}
    mutations = []
    for expr, replacement in [
        ('wire x10 = ~io_csr_stall;', "wire x10 = 1'h1;"),
        ('reg_wfi | io_status_cease', 'io_status_cease'),
        ('|pending_interrupts | exception', '|pending_interrupts | vector_busy | exception'),
    ]:
        for name in ('CSRFile', 'CSRFile_2'):
            text = compact(modules[name])
            if expr not in text:
                raise ValueError('Mutation precondition missing')
            try:
                check(text.replace(expr, replacement, 1))
            except ValueError:
                mutations.append({'module': name, 'source_expression': expr, 'rejected': True})
            else:
                raise ValueError('Counter source mutation admitted')
    dynamic = ROOT / 'build/Shuttle-WFI-source-component-v3/run.json'
    if json.loads(dynamic.read_text())['exit_status'] != 0:
        raise ValueError('Saved standalone Core dynamic proof failed')
    report = {
        'schema': 'iris.associated_CSR_WFI_clock_relations.v1', 'pass': True,
        'associated_generated_SV_sha256': EXPECTED,
        'bindings': bindings, 'exact_counter_expressions': COUNTER_EXPRESSIONS,
        'source_mutations_rejected': mutations,
        'facts': [
            'Both configured CSR modules count on the direct ungated clock, with increment enabled only when !csr_stall and not inhibited.',
            'WFI asserts csr_stall. An otherwise uninhibited mcycle therefore stops during WFI even while tile, Dcache and Saturn clocks continue.',
            'Local pending interrupt bits use reg_mie; reg_wfi clear does not require global MSTATUS.MIE in this configured source.',
            'Store acknowledgements and vector busy are not direct reg_wfi clear inputs. Vector/cache progress does not require CPU wake.',
            'CLINT time is a separate global timebase; per-hart mcycle origins diverge across WFI intervals.',
        ],
        'dynamic_scope': {
            'saved_standalone_Shuttle_Core_harts': [0, 1], 'seeds': [1, 17],
            'idle_external_edges': 96, 'observed_idle_mcycle_delta': 0,
            'actual_CSRS_and_WFI_executed': True,
            'Rocket_dynamic_WFI_test_performed': False,
            'joint_CPU_Saturn_cache_dynamic_test_performed': False,
            'standalone_and_associated_modules_byte_identical': False,
        },
        'hardware_contacted': False, 'native_or_counter_callbacks_changed': False,
        'protected_timing_labels_consumed': False,
        'hardware_stall_cause_identified': False, 'full_loaded_image_attestation': False,
        'input_sha256': {str(p): sha(p) for p in [Path(__file__).resolve(), Path(__file__).with_name('audit.py'),
            PARENT, SV, ROOT / 'build/shuttle-lsu-phase-source-v1/build.json', dynamic,
            ROOT / 'build/Shuttle-WFI-source-component-v3/check.stdout']},
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(sha(output / 'report.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output.resolve())
