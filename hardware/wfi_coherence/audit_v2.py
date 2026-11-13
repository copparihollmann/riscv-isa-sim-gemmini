#!/usr/bin/env python3
"""Bind the configured Saturn clock/busy leaves; never contact hardware.

This extends, rather than rewrites, the frozen v1 WFI/probe receipts.  Literal
guards and a generated hierarchy census are source audits, not a universal
forward-progress proof or an assertion that the associated bitstream is loaded.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from audit import EXPECTED, ROOT, SV, compact, sha

PARENT = ROOT / "build/WFI-coherence-source-closure-v1/report.json"
PARENT_SHA = "0f3f049c1d73b86e6578676ec3bdaa36e9e61b69d9e5ab54882d73badb697a84"
LEAVES = {
    "TLSplitInterface": ["assign io_mem_busy = reader_io_busy | writer_io_busy;"],
    "TLSplitInterface_2": ["assign io_mem_busy = reader_io_busy | writer_io_busy;"],
    "TLInterface": [
        "reg [3:0] inflights;", "assign io_busy = inflights != 4'h0;",
        "wire _T = auto_out_a_ready & io_req_valid;",
        "wire [3:0] _GEN_2 = {{3'd0}, auto_out_d_valid};",
        "wire [3:0] _inflights_T_5 = _inflights_T_2 - _GEN_2;",
    ],
    "TLInterface_4": ["reg [4:0] inflights;", "assign io_busy = inflights != 5'h0;"],
    "HellaCacheInterface": [
        "reg [5:0] inflights;", "assign io_mem_busy = inflights != 6'h0;",
        "wire [1:0] _inflights_T = load_enq + store_enq;",
        "wire [1:0] _inflights_T_3 = hella_arb_io_requestor_1_resp_valid + hella_arb_io_requestor_0_resp_valid;",
    ],
    "VectorBackend": ["assign io_busy = vdq_io_deq_valid | _io_busy_T_4 | |_io_busy_T_6;"],
    "VectorBackend_2": ["assign io_busy = vdq_io_deq_valid | _io_busy_T_2 | |vxufp_int_io_busy;"],
    "Rocket": [
        "wire id_vec_busy = io_vector_backend_busy | io_vector_trap_check_busy;",
        "wire id_do_fence = id_vec_busy & id_ctrl_fence | _id_do_fence_T_9;",
        "wire id_ctrl_fence = v_decode_io_legal ? 1'h0 : id_ctrl_decoder_24;",
    ],
    "ShuttleCore": [
        "wire vec_bsy = io_vector_backend_busy | io_vector_trap_check_busy;",
        "wire _rrd_fence_stall_T_14 = ex_bsy | mem_bsy | com_bsy | isboard_bsy | fsboard_bsy | ~io_dmem_ordered | vec_bsy;",
    ],
}
for name in ("VectorMemUnit", "VectorMemUnit_2"):
    LEAVES[name] = [
        "assign sifq_io_deq_ready = sifq_io_deq_bits_masked | store_rob_io_deq_valid;",
        "assign store_rob_io_push_valid = io_dmem_store_ack_valid;",
        "wire siq_deq_fire = _siq_deq_fire_T & sifq_io_deq_bits_last;",
        "assign store_rob_clock = clock;",
    ]


def require_literals(name, source):
    source = compact(source)
    for expr in LEAVES[name]:
        if expr not in source:
            raise ValueError(f"Changed associated source expression: {name}: {expr}")


def clock_census(modules, root):
    todo, seen = [root], {}
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        children = sorted(set(re.findall(r"^\s*(\w+)\s+\w+\s*\(", modules[name], re.M)) & modules.keys())
        source = compact(modules[name])
        assignments = re.findall(r"\bassign\s+(\w+_clock)\s*=\s*([^;]+);", source)
        posedges = sorted(set(re.findall(r"\bposedge\s+([^\)]+)\)", source)))
        bad = [(lhs, rhs) for lhs, rhs in assignments if rhs.strip() != "clock"]
        if bad:
            raise ValueError(f"Non-direct descendant clock: {name}: {bad}")
        if any(not re.fullmatch(r"(?:clock|io_ungated_clock)", edge.strip()) for edge in posedges):
            raise ValueError(f"Non-direct sequential clock: {name}: {posedges}")
        if re.search(r"clock_?gate|eicg", name, re.I):
            raise ValueError(f"Clock gate descendant: {name}")
        seen[name] = {"children": children, "clock_assignments": assignments,
                      "sequential_clock_expressions": posedges,
                      "source_module_sha256": hashlib.sha256(modules[name].encode()).hexdigest()}
        todo.extend(children)
    return {"unique_modules": len(seen),
            "direct_clock_assignments": sum(len(v["clock_assignments"]) for v in seen.values()),
            "non_direct_clock_assignments": 0, "clock_gate_modules": [], "modules": seen}


def main(output):
    if sha(PARENT) != PARENT_SHA or sha(SV) != EXPECTED:
        raise ValueError("Frozen parent / associated generated source changed")
    parent = json.loads(PARENT.read_text())
    for path, expected in parent["input_sha256"].items():
        if sha(path) != expected:
            raise ValueError(f"Frozen v1 input changed: {path}")
    modules = {m.group(1): m.group() + "\n" for m in re.finditer(
        r"^module\s+(\w+)[\s\S]*?^endmodule", SV.read_text(), re.M)}
    output.mkdir(parents=True, exist_ok=False)
    (output / "source").mkdir()
    for name in LEAVES:
        require_literals(name, modules[name])
        (output / "source" / (name + ".sv")).write_text(modules[name])
    roots = {name: clock_census(modules, name) for name in
             ("SaturnShuttleUnit", "SaturnRocketUnit", "Rocket", "FPU")}
    (output / "clock-census.json").write_text(json.dumps(roots, indent=2) + "\n")
    decode = Path("/scratch/eygao/iris-cy/generators/rocket-chip/src/main/scala/rocket/IDecode.scala")
    scala = decode.read_text()
    fields = [x.strip() for x in re.search(r"val sigs = Seq\((.*?)\)", scala, re.S)[1].split(",")]
    wfi = [x.strip() for x in re.search(r"WFI\s*->\s*List\((.*?)\)", scala)[1].split(",")]
    decoded = dict(zip(fields, wfi))
    if decoded.get("fence") != "N" or decoded.get("csr") != "CSR.I":
        raise ValueError("WFI decode assumptions changed")
    mutations = []
    for name, old, new in [
        ("TLSplitInterface_2", "reader_io_busy | writer_io_busy", "reader_io_busy"),
        ("VectorMemUnit_2", "store_rob_io_push_valid = io_dmem_store_ack_valid", "store_rob_io_push_valid = 1'h1"),
        ("VectorMemUnit", "sifq_io_deq_bits_masked | store_rob_io_deq_valid", "1'h1"),
        ("HellaCacheInterface", "inflights != 6'h0", "1'h0"),
        ("Rocket", "id_vec_busy & id_ctrl_fence", "id_vec_busy"),
    ]:
        if old not in compact(modules[name]):
            raise ValueError("Mutation precondition missing")
        try:
            require_literals(name, compact(modules[name]).replace(old, new, 1))
        except ValueError:
            mutations.append({"module": name, "expression": old, "rejected": True})
        else:
            raise ValueError("Meaningful source mutation admitted")
    bad_clock = dict(modules)
    bad_clock["SaturnRocketUnit"] = bad_clock["SaturnRocketUnit"].replace(
        "assign vmu_clock = clock;", "assign vmu_clock = clock & core_active;", 1)
    try:
        clock_census(bad_clock, "SaturnRocketUnit")
    except ValueError:
        mutations.append({"module": "SaturnRocketUnit", "expression": "VMU clock gate", "rejected": True})
    else:
        raise ValueError("Inner clock gate mutation admitted")
    report = {
        "schema": "iris.WFI_vector_clock_memory_busy_source_audit.v2", "pass": True,
        "parent_receipt_sha256": PARENT_SHA, "associated_generated_SV_sha256": EXPECTED,
        "clock_roots": {name: {k: v for k, v in value.items() if k != "modules"} for name, value in roots.items()},
        "source_expressions": LEAVES, "source_mutations_rejected": mutations,
        "Rocket_WFI_decode": decoded,
        "findings": [
            "Configured Rocket core, FPU and Saturn units use direct tile clocks. No inner gate appears in the enumerated actual generated hierarchy.",
            "Saturn is attached through Rocket's vector interface, not a separately gated RoCC command-clock wrapper.",
            "TL busy includes accepted request / actual response accounting. Hella busy includes enqueued load/store / actual response accounting.",
            "VMU busy retains load/store issue queues. Store issue tail cannot dequeue until masked or its store-ROB acknowledgement becomes valid.",
            "Shuttle system/WFI issue waits the source vector busy / memory-ordered gate. Rocket WFI is CSR.I with fence=false, so its id_vec_busy fence term does not itself force vector drain before WFI.",
            "CPU WFI does not stop the direct-clock vector/VMU/OPU or Dcache paths, even if a Rocket vector memory tail remains outstanding.",
        ],
        "limits": [
            "Source-only clock/decode/busy audit; no new joint CPU+Saturn WFI dynamic experiment.",
            "Finite-width TL inflights alone is not a universal outstanding-work certificate; other VMU/VU terms and protocol bounds matter.",
            "Backend busy is not proved equivalent to complete physical FP8/MRF/readout quiescence; this audit grants no clock skipping.",
            "No universal MSHR/NoC/AXI/host-token fairness proof or explanation of the observed FPGA stall.",
            "Associated build source is bound; full source-to-loaded-image attestation remains false.",
        ],
        "hardware_contacted": False, "native_or_counter_policy_changed": False,
        "protected_timing_labels_consumed": False, "watch_causality_established": False,
        "observed_hardware_stall_cause_identified": False,
        "input_sha256": {str(p): sha(p) for p in [Path(__file__).resolve(), Path(__file__).with_name("audit.py"), PARENT, SV, decode]},
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(sha(output / "report.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output.resolve())
