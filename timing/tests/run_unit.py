#!/usr/bin/env python3
"""Bounded native model regression checks, without any simulator jobs."""

import argparse
import copy
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    build = args.build_dir.absolute()
    build.mkdir(parents=True, exist_ok=True)
    flags = [
        "-std=c++20",
        "-O1",
        "-g0",
        "-I" + str(ROOT / "timing"),
        "-I" + str(ROOT / "timing/core/include"),
    ]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    spec = importlib.util.spec_from_file_location(
        "native_fixtures", ROOT / "timing/tests/run_native.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.fixture_model("0" * 64)
    model["limits"] = {"scoreboard_values": 256, "memory_entries": 32}
    model["memory"] = {
        "coherence_granule": 64,
        "caches": {
            "l1": {
                "sets": 16,
                "ways": 1,
                "line_bytes": 16,
                "policy": "write_back_write_allocate",
            }
        },
        "paths": {"cpu_data": ["l1"], "cpu_fetch": ["l1"], "device": []},
        "coherence_policy": "writeback_invalidate",
    }
    model["parameters"].update({"memory.l1.hit_cycles": 1, "memory.l1.miss_cycles": 1})
    model_file = build / "test-memory.json"
    model_file.write_text(json.dumps(model))
    cases = [
        ("engine", [ROOT / "timing/core/tests/test_engine.cpp"], []),
        ("reservations", [ROOT / "timing/core/tests/test_reservations.cpp"], []),
        ("decode", [ROOT / "timing/tests/test_cpu_decode.cpp"], []),
        ("fp-operands", [ROOT / "timing/tests/test_fp_operand_timing.cpp"], []),
        ("fp-operand-model", [ROOT / "timing/tests/test_fp_operand_model.cpp",
                              ROOT / "riscv/annotated_timing_model.cc"], [model_file, "legacy"]),
        ("scoped-resources", [ROOT / "timing/tests/test_scoped_resources.cpp"], []),
        ("counter-taint", [ROOT / "timing/tests/test_counter_taint.cpp"], []),
        (
            "memory",
            [
                ROOT / "timing/tests/test_memory.cpp",
                ROOT / "riscv/annotated_timing_memory.cc",
                ROOT / "riscv/annotated_timing_model.cc",
            ],
            [model_file],
        ),
        (
            "cache-byte-service",
            [ROOT / "timing/tests/test_cache_byte_service.cpp",
             ROOT / "riscv/annotated_timing_memory.cc", ROOT / "riscv/annotated_timing_model.cc"],
            [model_file, "legacy"],
        ),
    ]
    for name, sources, argv in cases:
        exe = build / ("test-" + name)
        subprocess.run(
            ["g++", *flags, *map(str, sources), "-lcrypto", "-o", str(exe)],
            check=True,
            timeout=120,
        )
        subprocess.run([str(exe), *map(str, argv)], check=True, timeout=30)
    # The fetch candidate is explicit and preserves the default scalar path.
    fetch = copy.deepcopy(model)
    geometry = {"sets": 8, "ways": 1, "line_bytes": 64,
                "policy": "write_back_write_allocate"}
    fetch["memory"]["caches"] = {name: copy.deepcopy(geometry) for name in ("l1i", "l1d", "l2")}
    fetch["memory"]["paths"] = {"cpu_fetch": ["l1i", "l2"], "cpu_data": ["l1d", "l2"], "device": ["l2"]}
    for name in ("l1i", "l1d", "l2"):
        fetch["parameters"].update({f"memory.{name}.hit_cycles": 1, f"memory.{name}.miss_cycles": 1})
    service = dict(schema="merlin.provisional_fetch_refill.v1",
        assumptions="demand_only_immediate_replay_no_backpressure", beat_bytes=16,
        first_response_cycles=6, beat_interval_cycles=1, line_visible_after_last_cycles=1,
        lookup_response_cycles=2, request_accept_cycles=2)
    exe = build / "test-fetch-refill"
    subprocess.run(["g++", *flags, str(ROOT / "timing/tests/test_fetch_refill.cpp"),
                    str(ROOT / "riscv/annotated_timing_memory.cc"),
                    str(ROOT / "riscv/annotated_timing_model.cc"), "-lcrypto", "-o", str(exe)],
                   check=True, timeout=120)
    for mode in ("legacy", "selected", "missing_assumption", "extra", "zero_interval", "oversized", "shared_private"):
        changed = copy.deepcopy(fetch)
        if mode != "legacy": changed["memory"]["fetch_refill_timeline"] = copy.deepcopy(service)
        selected = changed["memory"].get("fetch_refill_timeline", {})
        if mode == "missing_assumption": selected.pop("assumptions")
        if mode == "extra": selected["unknown"] = 1
        if mode == "zero_interval": selected["beat_interval_cycles"] = 0
        if mode == "oversized": selected["first_response_cycles"] = 4097
        if mode == "shared_private": changed["memory"]["paths"]["cpu_data"][0] = "l1i"
        path = build / ("test-fetch-refill-" + mode + ".json")
        path.write_text(json.dumps(changed))
        subprocess.run([str(exe), str(path), mode if mode in ("legacy", "selected") else "reject"],
                       check=True, timeout=30)
    for mode, selection in (
        ("selected", {"schema": "merlin.rocket_divsqrt_operand_timing.v1"}),
        ("reject", {}),
        ("reject", {"schema": "unknown"}),
        ("reject", {"schema": "merlin.rocket_divsqrt_operand_timing.v1", "extra": 1}),
    ):
        changed = copy.deepcopy(model)
        changed["cpu"]["fp_operand_timing"] = selection
        path = build / ("test-fp-operand-model-" + str(len(json.dumps(selection))) + ".json")
        path.write_text(json.dumps(changed))
        subprocess.run([str(build / "test-fp-operand-model"), str(path), mode], check=True, timeout=30)
    selected = copy.deepcopy(model)
    selected["resources"].append({"id": 3, "name": "memory.cache_boundary", "capacity": 1, "queue_capacity": 0})
    selected["memory"]["caches"]["l1"]["byte_service"] = {
        "schema": "merlin.cache_boundary_byte_service.v1", "resource": "memory.cache_boundary"}
    selected["parameters"]["memory.l1.per_byte_cycles"] = .5
    for mode in ("selected", "schema", "resource", "price", "zero_price"):
        changed = copy.deepcopy(selected)
        service = changed["memory"]["caches"]["l1"]["byte_service"]
        if mode == "schema": service["schema"] = "unknown"
        if mode == "resource": service["resource"] = "missing"
        if mode == "price": del changed["parameters"]["memory.l1.per_byte_cycles"]
        if mode == "zero_price": changed["parameters"]["memory.l1.per_byte_cycles"] = 0
        path = build / ("test-byte-service-" + mode + ".json")
        path.write_text(json.dumps(changed))
        subprocess.run([str(build / "test-cache-byte-service"), str(path),
                        "selected" if mode == "selected" else "reject"], check=True, timeout=30)
    lower = copy.deepcopy(selected)
    caches = lower["memory"]["caches"]
    caches["l2"] = copy.deepcopy(caches["l1"])
    caches["l2"]["line_bytes"] = 32
    del caches["l1"]["byte_service"]
    for path in ("cpu_data", "cpu_fetch"): lower["memory"]["paths"][path].append("l2")
    lower["parameters"].update({"memory.l2.hit_cycles": 1, "memory.l2.miss_cycles": 1,
                                "memory.l2.per_byte_cycles": .5})
    path = build / "test-byte-service-lower.json"
    path.write_text(json.dumps(lower))
    subprocess.run([str(build / "test-cache-byte-service"), str(path), "lower"], check=True, timeout=30)
    coherent = copy.deepcopy(lower)
    coherent["memory"]["coherence_granule"] = 16
    coherent["memory"]["caches"]["l2"]["line_bytes"] = 16
    coherent["memory"]["paths"]["device"] = ["l2"]
    exe = build / "test-coherence-transactions"
    subprocess.run(["g++", *flags, str(ROOT / "timing/tests/test_coherence_transactions.cpp"),
                    str(ROOT / "riscv/annotated_timing_memory.cc"),
                    str(ROOT / "riscv/annotated_timing_model.cc"), "-lcrypto", "-o", str(exe)],
                   check=True, timeout=120)
    for mode in ("legacy", "separate"):
        changed = copy.deepcopy(coherent)
        if mode == "separate":
            changed["memory"]["transaction_accounting"] = "coherence_request_separate_v1"
        path = build / ("test-coherence-" + mode + ".json")
        path.write_text(json.dumps(changed))
        subprocess.run([str(exe), str(path), mode], check=True, timeout=30)
    probe = copy.deepcopy(coherent)
    probe["memory"]["caches"]["l1d"] = probe["memory"]["caches"].pop("l1")
    for cache in probe["memory"]["caches"].values():
        cache["line_bytes"] = 64
        cache.pop("byte_service", None)
    probe["memory"]["coherence_granule"] = 64
    probe["memory"]["transaction_accounting"] = "coherence_request_separate_v1"
    for name in ("cpu_data", "cpu_fetch"): probe["memory"]["paths"][name] = ["l1d", "l2"]
    probe["parameters"].update({"memory.l1d.hit_cycles": 1, "memory.l1d.miss_cycles": 1})
    probe["resources"].append(dict(id=max(r["id"] for r in probe["resources"])+1,
        name="memory.l1d.probe", capacity=1, queue_capacity=0))
    exe = build / "test-private-probe-service"
    subprocess.run(["g++", *flags, str(ROOT / "timing/tests/test_private_probe_service.cpp"),
                    str(ROOT / "riscv/annotated_timing_memory.cc"),
                    str(ROOT / "riscv/annotated_timing_model.cc"), "-lcrypto", "-o", str(exe)],
                   check=True, timeout=120)
    for mode in ("legacy", "selected", "unknown", "response", "invalid-response"):
        changed = copy.deepcopy(probe)
        if mode != "legacy":
            changed["memory"]["caches"]["l1d"]["coherence_probe_service"] = dict(
                schema="merlin.private_cache_probe_service.v1", resource="memory.l1d.probe",
                beat_bytes=16, lookup_cycles=2, dirty_enter_cycles=1,
                data_pipeline_cycles=2, metadata_cycles=1)
        if mode in ("response", "invalid-response"):
            changed["memory"]["caches"]["l1d"]["coherence_probe_service"]["write_response"] = dict(
                schema="merlin.provisional_probe_write_response.v1",
                scope="offset_zero_wormhole_no_backpressure", block_bytes=64,
                pipeline_cycles=9)
            if mode == "invalid-response":
                changed["memory"]["caches"]["l1d"]["coherence_probe_service"]["write_response"]["block_bytes"] = 128
        if mode == "unknown": changed["parameters"].pop("memory.snoop_cycles")
        path = build / ("test-private-probe-" + mode + ".json")
        path.write_text(json.dumps(changed))
        subprocess.run([str(exe), str(path), mode], check=True, timeout=30)
    print("native unit regressions passed")


if __name__ == "__main__":
    main()
