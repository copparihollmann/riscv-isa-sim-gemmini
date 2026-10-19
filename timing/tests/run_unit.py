#!/usr/bin/env python3
"""Bounded native model regression checks, without any simulator jobs."""

import argparse
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
    ]
    for name, sources, argv in cases:
        exe = build / ("test-" + name)
        subprocess.run(
            ["g++", *flags, *map(str, sources), "-lcrypto", "-o", str(exe)],
            check=True,
            timeout=120,
        )
        subprocess.run([str(exe), *map(str, argv)], check=True, timeout=30)
    print("native unit regressions passed")


if __name__ == "__main__":
    main()
