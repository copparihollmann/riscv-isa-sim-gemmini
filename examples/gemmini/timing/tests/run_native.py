"""Tiny selfchecking ELF integration; synthetic prices do not qualify timing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv):
    started = time.monotonic()
    result = subprocess.run([str(value) for value in argv], check=True, capture_output=True, text=True, timeout=30)
    return result, time.monotonic() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spike-root", type=Path, required=True)
    parser.add_argument("--spike-build", type=Path, required=True)
    parser.add_argument("--functional-extension", type=Path, required=True)
    parser.add_argument("--timing-provider", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--clang", default="clang")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    build = args.build_dir.absolute()
    build.mkdir(parents=True, exist_ok=False)
    elf = build / "primitive.elf"
    _, compile_seconds = run([args.clang, "--target=riscv64-unknown-elf", "-march=rv64gc", "-mabi=lp64d",
                             "-mcmodel=medany", "-O1", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
                             "-fno-builtin", "-fno-stack-protector", "-msmall-data-limit=0",
                             "-nostdlib", "-fuse-ld=lld", "-Wl,-T," + str(root / "tests/elf/link.ld"),
                             root / "tests/elf/start.S", root / "tests/elf/primitive.c", "-o", elf])
    spec = importlib.util.spec_from_file_location("spike_native_tests", args.spike_root / "timing/tests/run_native.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = json.loads((args.spike_build / "timing-source-manifest.json").read_bytes())
    model = module.fixture_model(source["sha256"])
    model["scope"] = {"kind": "counter_pair", "index": 0}
    model["domain"]["scope_sha256"] = hashlib.sha256(b"native primitive selfcheck counter_pair0 no HTIF v2").hexdigest()
    stock = json.loads((root / "stock_u250.json").read_bytes())
    assert stock["target"]["hardware"]["reset_accumulator_activation"] is None
    assert all(value is None for fields in stock["target"]["prices"].values() for value in fields.values())
    assert all(value is None for fields in stock["resources"].values() for value in fields.values())
    model["domain"]["device_sha256"] = digest(root / "stock_u250.json")
    model["target"] = stock["target"]
    # All-one artificial prices exercise plumbing, never represent hardware estimates.
    for fields in model["target"]["prices"].values():
        for name in fields:
            fields[name] = 1
    for index, name in enumerate(("config", "load", "store", "execute"), start=3):
        model["resources"].append({"id": index, "name": "accelerator." + name,
                                   "capacity": 1, "queue_capacity": 2})
    extensions = [args.functional_extension.absolute(), args.timing_provider.absolute()]
    model["libraries"] = [digest(library) for library in extensions]
    profile, report_path = build / "synthetic-model.json", build / "report.json"
    profile.write_text(json.dumps(model))
    spike = args.spike_build / "spike"
    common = [spike, "--isa=rv64gc_zicntr_zihpm", "--priv=m", "-m64", "--instructions=1000000"]
    for library in extensions:
        common.append("--extlib=" + str(library))
    common.append("--extension=gemmini")
    baseline, baseline_seconds = run([*common, elf])
    annotated, annotated_seconds = run([*common, "--timing-model=" + str(profile),
                                       "--timing-report=" + str(report_path),
                                       "--timing-input-sha256=" + hashlib.sha256(b"").hexdigest(), elf])
    assert baseline.stdout == annotated.stdout
    assert "native primitive probe PASS\n" in annotated.stdout
    report = json.loads(report_path.read_bytes())
    assert report["functional_status"] == "PASS"
    assert report["timing_complete"], report["unresolved"]
    assert not report["whole_trace_timing_complete"]  # post-window HTIF polling is external I/O
    assert report["unresolved"] == [] and report["aborted_instructions"] == 0
    assert 0 < report["instructions"] < 1000000
    assert report["estimated_cycles"] > 0 and report["engine_qualification"] == "not_established"
    assert report["loaded_library_sha256"] == model["libraries"]
    features = report["feature_counts"]
    for name, expected in {"commands": 14, "requested_read_bytes": 32, "requested_write_bytes": 80,
                           "nominal_padded_macs": 4096, "useful_shape_macs": 64,
                           "semantic_unknown_events": 0, "illegal_events": 0}.items():
        assert features.get("target." + name, 0) == expected, (name, features.get("target." + name), expected)
    assert features["target.class.compute_ws"] == 1 and features["target.class.load"] == 2
    print(json.dumps({"status": "PASS", "instructions": report["instructions"],
                      "synthetic_estimated_cycles": report["estimated_cycles"],
                      "qualification": report["engine_qualification"],
                      "scope": "counter_pair0_before_HTIF", "whole_trace_timing_complete": False,
                      "seconds": {"compile": compile_seconds, "baseline": baseline_seconds,
                                  "annotated": annotated_seconds},
                      "spike_sha256": digest(spike), "feature_engine_sha256": source["sha256"],
                      "loaded_library_sha256": model["libraries"],
                      "elf_sha256": digest(elf), "report": str(report_path)}))


if __name__ == "__main__":
    main()
