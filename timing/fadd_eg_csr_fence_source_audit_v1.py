#!/usr/bin/env python3
"""Independent Core/VU-boundary audit. No hardware or timing labels."""
import argparse
import copy
import hashlib
import itertools
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(value, reason):
    if not value:
        raise ValueError(reason)


def check(rows):
    expected = set(itertools.product((1, 17, 31), (0, 1), range(4),
                                     (0xb00, 0xb02, 0xc00, 0xc02), (2, 3, 6, 7),
                                     (0, 0x0330000f, 0x0ff0000f)))
    seen = set()
    for row in rows:
        keys = ('seed', 'hart', 'physical_busy_mask', 'counter_CSR', 'CSR_funct3', 'barrier_raw')
        need(all(type(row[name]) is int for name in keys), 'Typed source inputs')
        key = tuple(row[name] for name in keys)
        need(key in expected and key not in seen, 'Exact unique source case')
        seen.add(key)
        need(all(type(row[name]) is int for name in ('VFADD_RRD', 'VFADD_COM', 'CSR_RRD', 'CSR_COM')),
             'Typed actual phase outputs')
        need(row['VFADD_RRD'] == 110 and row['VFADD_COM'] == 113,
             'Actual VFADD front retires without scalar-FPR response')
        if row['barrier_raw'] == 0:
            need(row['CSR_RRD'] == 111 and row['CSR_COM'] == 116,
                 'Counter CSR must retain scalar phase without backend/trap drain')
        else:
            mask = row['physical_busy_mask']
            first_clear = 170 if mask & 2 else 160 if mask & 1 else 114
            need(row['FENCE_RRD'] == first_clear and row['FENCE_COM'] == first_clear + 3,
                 'FENCE must wait full pre-edge CPU/backend/trap gates')
            need(row['CSR_RRD'] == first_clear + 1 and row['CSR_COM'] == first_clear + 6,
                 'Following counter retains source FENCE/scalar phase')
    need(seen == expected, 'Every source case retained')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run = ROOT / 'build/FADD-CSR-FENCE-source-v1'
    lines = [json.loads(line) for line in (run / 'core-check.stdout').read_text().splitlines()]
    need(lines[-1]['pass'] is True and lines[-1]['runs'] == 1152, 'Actual source checker completion')
    need((run / 'core-check.stderr').read_bytes() == b'', 'No RTL/source assertion diagnostic')
    rows = lines[:-1]
    check(rows)
    setup = struct.unpack('<7I', (run / 'setup.bin').read_bytes())
    need(setup == (0x000062b7, 0x6002829b, 0x3002a073, 0xcd00f057,
                   0x00301073, 0x02881457, 0xb0002373), 'Actual assembled source setup/operation')
    negatives = []

    def refused(name, mutant):
        try:
            check(mutant)
        except (ValueError, KeyError) as error:
            negatives.append({'name': name, 'rejected': True, 'reason': str(error)})
            return
        raise RuntimeError('Corruption accepted: ' + name)

    changed = copy.deepcopy(rows)
    changed[0]['CSR_COM'] = 170
    refused('counter_inherits_VU_busy', changed)
    changed = copy.deepcopy(rows)
    row = next(row for row in changed if row['barrier_raw'] and row['physical_busy_mask'] == 1)
    row['FENCE_RRD'] -= 1
    refused('FENCE_uses_postedge_empty_state_too_early', changed)
    changed = copy.deepcopy(rows)
    changed[0]['VFADD_COM'] = 160
    refused('vector_backend_holds_scalar_front_until_numeric_write', changed)
    changed = copy.deepcopy(rows)
    changed[0]['counter_CSR'] = 0xb03
    refused('unqualified_counter_alias', changed)
    changed = copy.deepcopy(rows)
    changed[0]['CSR_funct3'] = 1
    refused('counter_write_in_read_only_scope', changed)
    changed = copy.deepcopy(rows)
    changed[0]['physical_busy_mask'] = False
    refused('busy_mask_bool_instead_of_integer', changed)
    refused('missing_source_case', rows[:-1])

    source_refs = []
    bindings = {}

    def bind(path, expected=None):
        path = Path(path).resolve()
        actual = sha(path)
        need(expected is None or actual == expected, 'Changed source/input: ' + str(path))
        bindings[str(path)] = actual

    def ref(name, line, literal):
        path = ROOT / name
        need(literal in path.read_text().splitlines()[line - 1], 'Exact source citation: ' + name)
        bind(path)
        source_refs.append({'path': str(path), 'line': line, 'literal': literal, 'sha256': sha(path)})

    ref('third_party/shuttle/src/main/scala/common/MicroOp.scala', 68, 'def csr_en')
    ref('third_party/shuttle/src/main/scala/common/MicroOp.scala', 71, 'def system_insn')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 122, 'val mem_bsy = mem_uops_reg')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 123, 'val com_bsy = com_uops_reg')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 202, 'l.bits.ctrl.fp := vec_decoder.io.fp')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 214, 'l.bits.ctrl.wfd := vec_decoder.io.write_frd')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 444, 'val rrd_fence_stall')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 542, 'val ex_fcsr_data_hazard')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 1157, 'when (fire && com_uops(i).bits.ctrl.wfd)')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 1172, 'when (io.vector.map(_.set_fflags.valid)')
    ref('third_party/shuttle/src/main/scala/exu/Core.scala', 999, 'csr.io.retire := PopCount(com_retire)')
    ref('third_party/saturn/src/main/scala/frontend/EarlyDecode.scala', 76, 'io.write_frd := funct3 === OPFVV')
    ref('third_party/saturn/src/main/scala/frontend/EarlyDecode.scala', 77, 'io.fp := funct3 === OPFVF')
    ref('third_party/saturn/src/main/scala/exu/ExecutionUnit.scala', 141, 'when (pipe_valids.orR) { io.busy := true.B }')
    ref('third_party/saturn/src/main/scala/backend/Backend.scala', 632, 'io.busy := vdq.io.deq.valid')
    ref('third_party/saturn/src/main/scala/shuttle/Integration.scala', 62, 'io.backend_busy   := vu.io.busy')
    ref('third_party/saturn/src/main/scala/shuttle/Frontend.scala', 98, 'io.core.trap_check_busy := pfc.io.busy')
    ref('third_party/rocket-chip/src/main/scala/rocket/CSR.scala', 648, 'val reg_instret = WideCounter')
    ref('third_party/rocket-chip/src/main/scala/rocket/CSR.scala', 1280, 'when (io.fcsr_flags.valid)')
    for path in [Path(__file__).resolve(), ROOT / 'timing/fadd_eg_csr_fence_core_check_v1.cpp',
                 run / 'setup.S', run / 'setup.o', run / 'setup.bin', run / 'core-check',
                 run / 'core-check.stdout', run / 'core-check.stderr',
                 ROOT / 'build/shuttle-lsu-phase-source-v1/build.json',
                 ROOT / 'build/shuttle-lsu-phase-source-v1/ports.json',
                 ROOT / 'build/shuttle-lsu-phase-source-v1/initialize.hpp',
                 ROOT / 'build/shuttle-lsu-phase-source-v1/obj/VShuttleLSUPhase__ALL.a',
                 ROOT / 'build/shuttle-lsu-phase-source-v1/obj/verilated.o',
                 ROOT / 'build/shuttle-lsu-phase-source-v1/obj/verilated_threads.o',
                 ROOT / 'build/FADD-EG-actor-corrective-frozen-v2/manifest.json',
                 ROOT / 'pipeline/riscv-isa-sim-FADD-EG-v2/riscv/iris_fadd_eg_actor.inc',
                 ROOT / 'timing/rvv_fadd_eg_source_v1.hpp',
                 ROOT / 'build/rvv-fadd-EG-source-closure-v1/report.json',
                 ROOT / 'build/opu-fence-source-v1/report.json']:
        bind(path)
    build = json.loads((ROOT / 'build/shuttle-lsu-phase-source-v1/build.json').read_text())
    for field in ('input_sha256', 'source_sha256'):
        for name, digest in build[field].items():
            bind(name, digest)
    report = {
        'schema': 'iris.FADD_EG_CSR_FENCE_independent_source_audit.v1', 'pass': True,
        'actual_Core_runs': 1152, 'actual_hart_ids': [0, 1], 'reset_seeds': [1, 17, 31],
        'counter_CSRs': [0xb00, 0xb02, 0xc00, 0xc02], 'read_only_CSR_funct3': [2, 3, 6, 7],
        'Core_counter_not_VU_drain': {'VFADD_RRD': 110, 'VFADD_COM': 113,
                                     'counter_RRD': 111, 'counter_COM': 116,
                                     'external_backend_busy_clears': 160, 'external_trap_check_clears': 170},
        'VFADD_VV_scalar_FP_control': 'EarlyDecode fp=false for OPFVV; write_frd only wrfunary0, not funct6=fadd0. Core overrides scalar mem/fp/wfd accordingly. No scalar FPR response was supplied, yet every counter completed at116.',
        'scalar_cpu_hazards_preserved': 'Ordinary csr_en remains pipe0/youngest and EX stalls on scalar fsboard_bsy|mem_bsy|com_bsy. The older VFADD CPU-front occupies ordinary EX/MEM/COM transiently; backend work does not keep these valid after its successful COM.',
        'minstret_semantics': 'Core CSR retire is PopCount(com_retire); accepted ordinary vector front retirement counts before later VU numeric completion. No new backend-completion increment is permitted.',
        'FENCE_predicate': 'RRD system/fence/sfence/fenceI/amoaqrl waits EX|MEM|COM|integer/FPscoreboards|!dmem.ordered|RoCCbusy|backend_busy|trap_check_busy.',
        'FADD_FENCE_join_required': 'Retain all new FADD front reservations, VDQ/IQ/SEQ and live EXU pipe slots. Final source write edgeE is busy PREedge; post-step actor/queue emptiness must not admit FENCE untilE+1. Apply generic FENCE gate even without any OPU tail. Counter CSR reads must not inherit this busy gate.',
        'FENCE_source_phase': 'No external busy: FENCE RRD114/COM117; backend-held: RRD160/COM163; trap-held: RRD170/COM173. Immediate following CSR COM=FENCE RRD+6.',
        'FADD_flags_and_context_scope': 'Current actor isolates newly raised flags and rejects nonzero newflags, requires known flags/RNE/FSalreadydirty; FCSR/config/memory/VRF consumers and IRQ/context remain conservatively draining/refused. This audit does not authorize their relaxation.',
        'CPU_to_VU_COMplus1_bridge_qualified': False,
        'source_boundary_scope': 'Actual cached saved ShuttleCore56module execution with externally driven VU ready/busy/flags boundary. Source instructions define FS/VS, VL/vtype and FCSR. No VU numerical payload or internal state was injected; no wholeCPU+VU loop/FPGA numerical proof.',
        'corruption_controls': negatives, 'source_refs': source_refs, 'input_sha256': bindings,
        'hardware_contacted': False, 'protected_timing_labels_consumed': False,
        'timing_parameters_fitted': False, 'source_image_association': False, 'timing_2pct_certified': False
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'actual_runs': 1152, 'corruptions': len(negatives),
                      'report_sha256': sha(output / 'report.json')}))


if __name__ == '__main__':
    main()
