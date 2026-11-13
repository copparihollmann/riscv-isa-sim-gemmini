#!/usr/bin/env python3
"""Freeze source-checked RVV-to-memory integration decisions without timing labels."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Fresh artifact directory required')
    paths = [
        'timing/rvv_memory_fabric_plan_v1.md', 'timing/rvv_memory_fabric_plan_v1.py',
        'timing/shuttle_memory_system.hpp', 'timing/shuttle_memory_system_README.md',
        'timing/shuttle_memory_system_check.cpp', 'timing/serial_memory_system_README.md',
        'timing/fased_service.hpp', 'timing/rvv_store_sequence.hpp', 'timing/rvv_store_sequence.cpp',
        'timing/rvv_store_compactor_control.hpp',
        'third_party/saturn/src/main/scala/mem/Mem.scala',
        'third_party/saturn/src/main/scala/mem/TLInterface.scala',
        'third_party/saturn/src/main/scala/common/ReorderBuffer.scala',
        'third_party/saturn/src/main/scala/shuttle/Integration.scala',
        'build/rtl-verilator/gen-collateral/TLSplitInterface.sv',
        'build/rtl-verilator/gen-collateral/TLInterface.sv',
        'build/rtl-verilator/gen-collateral/TLXbar_i2_o1_a35d128s5k4z4u.sv',
        'build/rtl-verilator/gen-collateral/TLWidthWidget16.sv',
        'build/rtl-verilator/gen-collateral/TLBuffer_a35d256s5k4z4u.sv',
        'build/rtl-verilator/gen-collateral/SaturnShuttleUnit.sv',
        'build/rtl-verilator/gen-collateral/ReorderBuffer.sv',
        'build/shuttle-memory-system-native-v6/build.json',
        'build/shuttle-memory-system-component-v1/report.json',
        'build/shuttle-memory-system-native-v6/shuttle_memory_system.generated.cpp',
        'build/saturn-timing-native-v1/compute/ports.json',
        'build/rvv-vector-store-actor-v2-frozen-05f07554-v1/manifest.json',
        'pipeline/riscv-isa-sim-vector-store-actor-v2/riscv/iris_vector_store_actor.inc',
    ]
    text = {n: (ROOT / n).read_text() for n in paths}
    expected = [
        ('build/rtl-verilator/gen-collateral/TLSplitInterface.sv', '.auto_anon_in_1_a_valid        (_writer_auto_out_a_valid)'),
        ('build/rtl-verilator/gen-collateral/TLXbar_i2_o1_a35d128s5k4z4u.sv', 'assign auto_anon_in_1_d_valid = auto_anon_out_d_valid & ~(auto_anon_out_d_bits_source[4]);'),
        ('build/rtl-verilator/gen-collateral/TLXbar_i2_o1_a35d128s5k4z4u.sv', "(muxState_1 ? {1'h0, auto_anon_in_1_a_bits_source} : 5'h0)"),
        ('third_party/saturn/src/main/scala/mem/Mem.scala', 'store_rob.io.reserve.ready := sas.io.req.fire'),
        ('third_party/saturn/src/main/scala/mem/Mem.scala', 'store_rob.io.push.valid := io.dmem.store_ack.valid'),
        ('third_party/saturn/src/main/scala/mem/Mem.scala', 'sifq.io.deq.ready := sifq.io.deq.bits.masked || store_rob.io.deq.valid'),
        ('third_party/saturn/src/main/scala/mem/Mem.scala', 'siq_deq_fire := sifq.io.deq.fire && sifq.io.deq.bits.last'),
        ('third_party/saturn/src/main/scala/common/ReorderBuffer.scala', 'val full = ptr_match && maybe_full'),
        ('third_party/saturn/src/main/scala/common/ReorderBuffer.scala', 'valids(deq_ptr.value) || (io.push.fire && io.push.bits.tag === deq_ptr.value)'),
        ('third_party/saturn/src/main/scala/shuttle/Integration.scala', 'atlNode := TLBuffer(vParams.tlBuffer) := TLWidthWidget(mLenB) := tl_if.node'),
        ('third_party/saturn/src/main/scala/shuttle/Integration.scala', 'vu.io.busy || tl_if.module.io.mem_busy || sg_if.map(_.module.io.mem_busy).getOrElse(false.B) || vmu.io.busy'),
        ('timing/shuttle_memory_system_check.cpp', 'system.commit({edge,edge,true,tick%10==0})'),
        ('timing/shuttle_memory_system_check.cpp', 'read-only test actor cannot supply an unexpected outer write'),
    ]
    citations = []
    for name, phrase in expected:
        matches = [i for i, line in enumerate(text[name].splitlines(), 1) if phrase in line]
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous source claim: ' + phrase)
        citations.append({'path': name, 'line': matches[0], 'source': phrase})
    system = json.loads(text['build/shuttle-memory-system-native-v6/build.json'])
    closure = json.loads(text['build/shuttle-memory-system-component-v1/report.json'])
    if closure['source_identity'] != system['source_identity'] or closure['source_relative_periods'] != {
        'both_shuttle_memory': 2, 'rocket': 2, 'uncore': 2, 'bringup': 1, 'serial': 10}:
        raise ValueError('Frozen System source/clock contract changed')
    # Check exact endpoint names without dumping huge generated field arrays.
    generated = text['build/shuttle-memory-system-native-v6/shuttle_memory_system.generated.cpp']
    endpoints = {}
    for h in (0, 1):
        name = 'shuttle%d_tile' % h
        entries = re.findall(r'if\(c=="' + name + r'"&&n=="(_vector_unit_auto_atl_out_[^"]+)"\)return (\d+);', generated)
        if len(entries) < 10:
            raise ValueError('Expected physical ATL endpoint mapping')
        endpoints[name] = {n: int(i) for n, i in entries}
    ports = json.loads(text['build/saturn-timing-native-v1/compute/ports.json'])
    widths = {f['name']: f['width'] for f in ports['physical_ports'] if f['name'].startswith('auto_atl_')}
    for field, width in {'auto_atl_out_a_bits_data': 256, 'auto_atl_out_a_bits_mask': 32,
                         'auto_atl_out_a_bits_source': 5, 'auto_atl_out_a_bits_address': 35}.items():
        if widths.get(field) != width:
            raise ValueError('Saturn physical width differs')
    for path, digest in ports['source_files'].items():
        if Path(path).name in {Path(n).name for n in paths if n.endswith('.sv')}:
            current = ROOT / 'build/rtl-verilator/gen-collateral' / Path(path).name
            if sha(current) != digest:
                raise ValueError('Plan SV differs from qualified Saturn cut')
    report = {
        'schema': 'iris.rvv_memory_fabric_source_plan.v1', 'pass': True,
        'implementation_status': 'Source-bound integration plan; no native integration or new fabric run claimed',
        'system_source_identity': system['source_identity'], 'source_citations': citations,
        'physical_ATL_fields': widths, 'system_ATL_indices': endpoints,
        'clock_contract': {'master_hz': 1000000000, 'native_global_hz': 500000000,
                           'native_cycle_to_master_ticks': 2, 'source_relative_periods': closure['source_relative_periods'],
                           'odd_master_events_require_half_native_cycle_stamp': True,
                           'FASED_parameters_required': True, 'FASED30_CPU_cycle_default': False,
                           'clock_origin_and_reset_waveform_must_be_explicit': True},
        'request_geometry': {'internal_compute_bytes': 16, 'ATL_slot_bytes': 32,
                             'example_payload_bytes': 256, 'TL_requests': 16, 'physical_A_beats': 16},
        'source_IDs_before_tile_remap': {'store': [0, 15], 'load': [16, 31]},
        'ordering': ['circular ROB reserve at AddrGen acceptance', 'physical A acceptance distinct',
                     'matching D completes tag', 'ordered SIFQ/ROB retirement frees tag',
                     'VRF last-read lease distinct from D', 'SIQ last dequeue and TL outstanding feed busy'],
        'next_component': 'Exact source ROB control + clock stamp and response ownership, followed by saved Saturn split/width/buffer physical System join',
        'selected_epoch_modified': False, 'new_hardware_contacted': False,
        'timing_labels_consumed_for_plan': False, 'timing_calibrated': False,
        'whole_SoC_or_image_association_claim': False,
        'input_sha256': {str(ROOT / n): sha(ROOT / n) for n in paths}}
    a.output.mkdir(parents=True)
    (a.output / 'plan.md').write_bytes((ROOT / 'timing/rvv_memory_fabric_plan_v1.md').read_bytes())
    (a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'report_sha256': sha(a.output / 'report.json'), 'source_claims': len(citations)}))


if __name__ == '__main__':
    main()
