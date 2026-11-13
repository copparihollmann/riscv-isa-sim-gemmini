#!/usr/bin/env python3
"""Bind a source-only implementation plan; do not open performance labels."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/fased-write-backing-plan-v1"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    OUT.mkdir()
    rtl = ROOT / "build/fased-service-source-v2/rtl"
    scala = Path("/scratch/eygao/iris-cy/sims/firesim/sim/midas/src/main/scala/midas/models/dram")
    facts = []
    inputs = {}

    def fact(name, value, *anchors):
        citations = []
        for path, needle in anchors:
            lines = path.read_text().splitlines()
            found = [i+1 for i,line in enumerate(lines) if needle in line]
            assert found, (path, needle)
            citations.append(dict(path=str(path), line=found[0], exact_source=needle))
            inputs[str(path)] = sha(path)
        facts.append(dict(name=name, value=value, citations=citations))

    fact("read_due_edge", "AR handshake edge + readLatency - 1; registered releaser makes R valid on the following target edge if its response slot is available",
         (rtl/"LatencyPipe.sv", "assign readPipe_io_enq_bits_releaseCycle = _readPipe_io_enq_bits_releaseCycle_T_1 - 64'h1;"),
         (rtl/"LatencyPipe.sv", "assign readPipe_io_enq_valid = nastiReqIden_io_out_ar_ready & nastiReqIden_io_out_ar_valid;"),
         (rtl/"AXI4Releaser.sv", "assign io_egressReq_r_valid = io_nextRead_ready & io_nextRead_valid;"),
         (rtl/"Queue_10.sv", "assign io_deq_valid = ~empty;"))
    fact("write_due_edge", "FIFO matched AW and complete WLAST burst pairing edge + writeLatency - 1, followed by the registered B slot",
         (rtl/"LatencyPipe.sv", "wire  newWReq = _newWReq_T_4 | _newWReq_T_5;"),
         (rtl/"LatencyPipe.sv", "assign writePipe_io_enq_bits_releaseCycle = _writePipe_io_enq_bits_releaseCycle_T_1 - 64'h1;"),
         (scala/"TimingModel.scala", "awQueue.io.deq.ready := newWReq"),
         (rtl/"Queue_11.sv", "assign io_deq_valid = ~empty;"))
    fact("releaser_replacement", "One R burst and one B response active independently; last-R/B acceptance can make room for a new same-edge egress request; no forced inter-burst bubble",
         (rtl/"Queue_10.sv", "assign io_enq_ready = io_deq_ready | empty;"),
         (rtl/"Queue_11.sv", "assign io_enq_ready = io_deq_ready | empty;"),
         (rtl/"AXI4Releaser.sv", "assign currentRead_q_io_deq_ready = _q_io_deq_ready_T & io_r_bits_last;"))
    fact("full_bridge_targetFire", "Full FASED admits a timing-model target edge only with host tokens, ingress room, both functional egress payloads and reset-idle qualification; LP SDK alone does not model these gates",
         (rtl/"FASEDMemoryTimingModel.sv", "wire  targetFire = hPort_toHost_hValid & hPort_fromHost_hReady & ingress_io_nastiInputs_hReady &"),
         (rtl/"FASEDMemoryTimingModel.sv", "writeEgress_io_resp_hValid & readEgress_io_resp_hValid & tResetReady;"))
    fact("strict_functional_ordering_context", "relax=0 source ingress prevents host R/W reorderings; first new ledger will conservatively refuse overlapping live read/write or write/write ownership instead of claiming full ingress equivalence",
         (scala/"IngressUnit.scala", "asserting io.relaxed = false"),
         (scala/"IngressUnit.scala", "youngest write for which the AW and all W beats have been"),
         (rtl/"FASEDMemoryTimingModel.sv", "assign ingress_io_relaxed = relaxFunctionalModel[0];"))
    clocks = ROOT/"zephyr/uart-profile-evidence/firesim-clocks.freq-summary"
    fact("source_clock_conversion", "Elaborated 1GHz reference/Bringup/FASED, 500MHz Iris/uncore,100MHz Serial; periods1/2/10. Source/build evidence only, not measured/attested loaded clock or whole-CPU latency",
         (clocks, "Input Reference Frequency: 1000.0 MHz"),
         (clocks, "Output clock clock_1000.0MHz, requested: 1000.0 MHz"),
         (clocks, "Output clock clock_500.0MHz, requested: 500.0 MHz"))
    fact("current_write_refusal_is_fixture_only", "Systemv6 physical source boundary already includes AW/W/B; the existing external checker refuses unexpected writes, not the SDK",
         (ROOT/"timing/shuttle_memory_system_check.cpp", 'read-only test actor cannot supply an unexpected outer write'),
         (ROOT/"timing/shuttle_memory_system_check.cpp", '{"aw_ready","tNasti_aw_ready"}'))
    fact("existing_functional_fixture", "Existing independent AW/W FIFO ownership and AR-time snapshots are useful prior work; keep its source bytes unchanged and add a new domain/visibility/phase wrapper",
         (ROOT/"pipeline/axi_functional_fixture.hpp", "void accept_aw(Request request)"),
         (ROOT/"pipeline/axi_functional_fixture.hpp", "void accept_w(uint64_t data,unsigned strobe,bool last"),
         (ROOT/"pipeline/axi_functional_fixture.hpp", "void request_write_egress(unsigned id)"))

    safe = ROOT/"build/rvv-compute-heldout2-asm-HARDWARE-sealed-receipt-v1/report.json"
    assert sha(safe) == "39f2658fb7a0b22c3aae85117790a215c2d6a5a66ed591492cc13edde8b6e5f6"
    observed = json.loads(safe.read_text())
    config = observed["postdriver_configuration_register_observations"]
    assert config == dict(writeLatency=30,readLatency=30,writeMaxReqs=16,readMaxReqs=16,relaxFunctionalModel=0)
    assert all(type(v) is int for v in config.values())
    assert observed["transaction_or_CPU_latency_measured"] is False
    system = ROOT/"build/shuttle-memory-system-component-v1/report.json"
    system_info = json.loads(system.read_text())
    assert system_info["source_identity"] == "453fad48afb9a1c9172c57969d50a9aae6a9654df30cb663d3fa0250f68e791b"
    sdk = ROOT/"build/serial-memory-context-sdk-v2/fased"
    sdk_info = json.loads((sdk/"build.json").read_text())
    assert sdk_info["source_identity"] == "1d1d497a614cda9e0076368589246bceaeb2cb5dcc20c82d951c6f2566257f85"
    extra = [Path(__file__).resolve(),safe,system,sdk/"build.json",sdk/"sdk/fased_service.hpp",sdk/"sdk/libiris_fased_service.a",
             ROOT/"build/shuttle-memory-system-native-v6/build.json",ROOT/"build/shuttle-memory-system-native-v6/sdk/shuttle_memory_system.hpp",
             ROOT/"build/fased-service-component-v1/report.json",ROOT/"build/fased-service-component-v1-verify/report.json",
             ROOT/"build/fased-service-source-v2/extraction.json",ROOT/"build/fased-service-clock-check-v1/report.json",
             ROOT/"timing/fased_service_test.cpp",ROOT/"timing/fased_service.hpp",ROOT/"timing/fased_service.cpp",
             ROOT/"build/axi-functional-fixture-v1/results.json"]
    inputs.update({str(p):sha(p) for p in extra})
    report = dict(schema="iris.FASED_write_backing_source_plan.v1",**{"pass":True},
        status="feasible_for_explicit_finite_ideal_host_service_not_full_bridge",
        facts=facts,observed_postdriver_config=config,
        observed_config_scope="Exact safe postdriver config/outcome receipt only; no protected performance rows read; not a default or CPU transaction latency",
        source_system_identity=system_info["source_identity"],source_FASED_context_SDK_identity=sdk_info["source_identity"],
        new_files_owned=["timing/fased_backing_ledger_v1.hpp","timing/fased_backing_service_v1.hpp","timing/fased_backing_ledger_v1_check.cpp","timing/fased_backing_service_v1_check.cpp","timing/shuttle_memory_system_write_v1.cpp"],
        minimum_scope=["Explicit declared 33bit AXI memory domains and initial bytes/knownness; no implicit RAM/default pattern",
            "ID4, INCR,1..8beats,initially full64bit reads/size3; explicit size/domain/4KiB/overflow guards",
            "AW and W accepted independently; W-before-AW supported by bounded complete-burst FIFO; nth AW owns nth WLAST burst",
            "Full-burst prevalidation of AWLEN/WLAST/WSTRB/strobed data knownness before any memory publication",
            "AR-time immutable read snapshot retained through actual source egress and all R beats",
            "B response ownership retained through actual B handshake; staged strobed writes visible only after qualified completion/fence",
            "Same-edge final response consumption then next source egress selection without extra LP latency",
            "Disjoint-line concurrent h0/1 operations; overlapping live R/W,W/W,atomics,unqualified narrow reads and pending reset may refuse",
            "Frozen source LP drives its own readiness; service never replays observed ready, changes parameters or predicts response timing"],
        milestone_order=["Byte-map/FIFO/knownness ledger + independent touched-byte oracle",
            "Clocked adapter around unchanged LP SDK; independent phase oracle versus actual compiled source RTL under AW-first/W-first/latency1/30/backpressure",
            "Only then new Systemv6 physical h0/1 warm-load/store/dirty-eviction fixture with source periods2/1/10 and explicit fences"],
        tests_required=["Independent full bytes and masks,partial strobes,unwritten neighbors,missing/out-of-domain bytes",
            "AW-leading,W-leading,bursts1/8,repeated IDs,16request bounds,R/B backpressure and same-edge final-beat replacement",
            "WrongID,AWLEN/WLAST early/late,duplicate/lost response,unknown strobed byte,invalid WSTRB,unmapped/overflow/4KiB-crossing request refusals",
            "No mutation on refused complete transaction; accepted payload held stable until real response acceptance",
            "One-edge registered egress and wrong-latency/ready/state-injection controls; all Model evaluate/sample/commit and caller-context guards retained",
            "System positive must use explicit actual load warmup; default Shuttle cold-RPQ store refusal stays strict"],
        open_boundaries=["Full FASED host ingress/egress/token/backpressure/clock-gate model remains outside initial adapter",
            "Observed relax0 does not certify our chosen visibility policy as the full source functional ordering",
            "No direct30CPUcycle service or postL2-cork shortcut; actual Serial/Bringup adapters remain in Systemv6",
            "No coherence/atomics/overlappingRAW/activeCPU/Zephyr timing qualification from external ledger alone"],
        large_integration_started=False,implementation_completed=False,hardware_contacted=False,network_contacted=False,
        protected_performance_labels_consumed=False,fit_performed=False,primary_or_frozen_files_changed=False,
        source_image_association_verified=False,calibration_usable=False,timing_certified=False,input_sha256=inputs)
    (OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(dict(status=report["status"],report_sha256=sha(OUT/"report.json"),source_facts=len(facts))))


if __name__ == "__main__":
    main()
