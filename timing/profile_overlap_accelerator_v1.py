#!/usr/bin/env python3
"""Model-only accelerator activity from actual CSR joins and completed OPU events.

These metrics describe the finite model, not measured FPGA utilization. Clock
callback reservations are never counted as physical array utilization.
"""
import argparse
import bisect
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "timing"))
from compare_overlap_completion_v3 import native, load, need, sha
from iris_model.report import symbols


def complete_events(path):
    raw = path.read_bytes()
    end = raw.rfind(b"\n") + 1
    rows = [json.loads(line) for line in raw[:end].splitlines()]
    return rows, len(raw) - end


def operation_joins(events):
    accepts = {(r["hart"], r["instruction"]): r for r in events if r["event"] == "opu_front_accept"}
    canceled = {(r["hart"], r["instruction"]) for r in events if r["event"] == "opu_front_cancel"}
    micros = [r for r in events if r["event"] == "opu_microissue_reserved"]
    writes = [r for r in events if r["event"] == "opu_entry_publish"]
    planned, published = collections.Counter(), collections.Counter()
    for r in micros:
        owner = r["hart"], r["instruction"]
        need(owner in accepts and owner not in canceled, "No MAC credit for a canceled/unowned command")
        need(accepts[owner]["com"] <= r["seq"] < r["array"] <= r["write"], "Committed forward source operation")
        need(type(r["macs"]) is int and 0 < r["macs"] <= 256, "Finite source cell work")
        planned[r["hart"], r["instruction"], r["write"], r["macs"]] += 1
    for r in writes:
        published[r["hart"], r["instruction"], r["cycle"], r["cells"]] += 1
    need(planned == published, "Every credited source operation must have an actual matching publication")
    return micros


def main(a):
    run, build, out = [p.resolve() for p in (a.run, a.build, a.output)]
    need(not out.exists(), "Fresh profile output required")
    corpus, elf = load(build / "corpus.json"), build / "overlap.elf"
    rows, scope, receipt = native(run, corpus, elf)
    event_path = run / "async.jsonl"
    need(receipt["output_sha256"].get("async.jsonl") == sha(event_path), "Bound actual asynchronous events")
    events, tail = complete_events(event_path)
    micros = operation_joins(events)
    capacity = ROOT / "build/throughput-limits-source-v3/report.json"
    caps = load(capacity)
    need(caps["pass"] is True and caps["geometry"]["opu_macs_per_accepted_array_edge"] == 256,
         "Source-bound conditional array ceiling")
    nm = Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm")
    sym = symbols(elf, nm)
    starts = [s[0] for s in sym]
    def function(pc):
        i = bisect.bisect_right(starts, pc) - 1
        return sym[i][2] if i >= 0 and pc < sym[i][1] else None
    base_hz = 500_000_000
    timestamp = lambda cycle: cycle * 1_000_000 / base_hz
    trace, profiles = [], []
    for h in range(3):
        trace.append(dict(ph="M", pid=h, tid=0, name="process_name", args=dict(name="hart " + str(h))))
    for row in rows:
        h = row["hart"]
        endpoints = row["actual_CSR_endpoints"]
        lo, hi = endpoints[0]["read_cycle"], endpoints[-1]["read_cycle"]
        span = hi - lo
        need(span > 0, "Forward shared source clock")
        active = [r for r in micros if r["hart"] == h and lo <= r["array"] < hi]
        macs = sum(r["macs"] for r in active)
        expected_macs = row["count"] * row["edge"] ** 2 if h < 2 else 0
        need(macs == expected_macs, "All and only measured kernel logical MACs")
        need(all(lo <= r["write"] < hi for r in active), "All kernel output work completed before final CSR")
        begin, end = endpoints[0]["features"], endpoints[-1]["features"]
        features = {}
        for name in set(begin) | set(end):
            features[name] = {key: end.get(name, {}).get(key, 0) - begin.get(name, {}).get(key, 0)
                              for key in ("instructions", "work", "bytes", "macs")}
            need(all(v >= 0 for v in features[name].values()), "Forward retired feature counters")
        requested = sum(v["bytes"] for k, v in features.items() if k.startswith("memory."))
        adds = row["count"] * row["edge"] if h == 2 else None
        if h == 2:
            need(features["rvv.integer"]["instructions"] == row["count"], "Measured RVV instruction count")
        units = {}
        for name in set(endpoints[0]["resource_occupancy_prefix"]) | set(endpoints[-1]["resource_occupancy_prefix"]):
            x = endpoints[0]["resource_occupancy_prefix"].get(name, {}).get("union_cycles", 0)
            y = endpoints[-1]["resource_occupancy_prefix"].get(name, {}).get("union_cycles", 0)
            need(0 <= y-x <= span, "Clipped source resource union, never additive stalls")
            units[name] = dict(union_source_cycles=y-x, fraction_of_global_CSR_span=(y-x)/span)
        logical_ops = 2 * macs if h < 2 else adds
        record = dict(case_id=row["case_id"], hart=h, fp8=row["fp8"], edge=row["edge"], count=row["count"],
                      rotate=row["rotate"], trial=row["trial"], program_mcycle_delta=row["drain_end"]-row["start"],
                      source_global_CSR_span_cycles=span, logical_MACs=macs, logical_RVV_e8_adds=adds,
                      source_array_microissues=len(active),
                      source_array_issue_slot_fraction=len({r["array"] for r in active})/span if h < 2 else None,
                      achieved_MACs_per_source_cycle=macs/span if h < 2 else None,
                      source_conditional_peak_MACs_per_cycle=256 if h < 2 else None,
                      achieved_fraction_of_conditional_MAC_peak=macs/(256*span) if h < 2 else None,
                      active_cell_fraction_per_array_issue=macs/(256*len(active)) if active else None,
                      requested_memory_operand_bytes=requested,
                      requested_byte_arithmetic_intensity_ops_per_byte=logical_ops/requested if requested else None,
                      achieved_logical_operations_per_source_cycle=logical_ops/span,
                      physical_DRAM_bytes=None, physical_DRAM_roofline=None,
                      modeled_resource_unions=units, nonadditive_stall_breakdown=None)
        profiles.append(record)
        for i, name in enumerate(("issue", "fence", "readout")):
            a0, a1 = endpoints[i]["read_cycle"], endpoints[i+1]["read_cycle"]
            trace.append(dict(ph="X", pid=h, tid=0, name=str(row["case_id"])+" "+name,
                              ts=timestamp(a0), dur=timestamp(a1-a0), args=dict(program_counter_cycles=row[FIELDS[i+1]]-row[FIELDS[i]])))
        for r in active:
            trace.append(dict(ph="i", s="t", pid=h, tid=1, name="OPU array issue", ts=timestamp(r["array"]),
                              args=dict(logical_MACs=r["macs"], entry=r["entry"], pc=hex(r["pc"]), function=function(r["pc"]))))
            trace.append(dict(ph="i", s="t", pid=h, tid=2, name="OPU entry write", ts=timestamp(r["write"]),
                              args=dict(logical_MACs=r["macs"], entry=r["entry"])))
    out.mkdir(parents=True)
    (out / "regions.json").write_text(json.dumps(profiles, indent=2)+"\n")
    (out / "trace.json").write_text(json.dumps(dict(traceEvents=trace, displayTimeUnit="ns"))+"\n")
    inputs = [Path(__file__).resolve(), ROOT / "timing/compare_overlap_completion_v3.py", run / "run.json",
              event_path, run / "features.jsonl", run / "stderr", build / "corpus.json", elf, capacity, nm]
    report = dict(schema="iris.finite_accelerator_activity_profile.v1", passed=True, regions=168,
                  completed_source_microissues=len(micros), source_clock_hz=base_hz,
                  scope=scope, preserved_unterminated_event_tail_bytes=tail,
                  hardware_utilization_measured=False, timing_accuracy_certified=False,
                  source_image_association_verified=False, stall_breakdown_available=False,
                  resource_scope="Source graph reservation unions; queue/callback clocks are bookkeeping and are not physical VME busy fractions.",
                  array_scope="Completed logical source array issue and entry write edges; no power/whole-pipeline busy claim.",
                  clock_scope="Program counter deltas and shared source-clock CSR spans are reported separately; throughput uses shared source clock.",
                  memory_scope="Requested architectural memory operands include stack and output, exclude unmeasured setup; no physical traffic/bandwidth roofline.",
                  input_sha256={str(p): sha(p) for p in inputs},
                  output_sha256={p.name: sha(p) for p in out.iterdir()})
    (out / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(dict(passed=True, regions=168, source_microissues=len(micros))))


FIELDS = ("start", "issue_end", "fence_end", "drain_end")
if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    for key in ("run", "build", "output"):
        p.add_argument("--"+key, type=Path, required=True)
    main(p.parse_args())
