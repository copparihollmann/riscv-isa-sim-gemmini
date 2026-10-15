#!/usr/bin/env python3
"""Native correctness regressions. Synthetic prices never qualify cycle accuracy."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def fixture_model(engine_sha):
    kinds = set(
        re.findall(r'"(cpu\.[a-z_]+)"', (ROOT / "timing/cpu_decode.hpp").read_text())
    ) - {"cpu.unknown"}
    priced = kinds | {
        kind + ".f" + str(width)
        for kind in kinds
        if kind.startswith(("cpu.fp_", "cpu.int_to_fp"))
        for width in (32, 64)
    }
    priced |= {"cpu.fp_convert.f64_to_f32", "cpu.fp_convert.f32_to_f64"}
    params = {
        kind + "." + field: 1
        for kind in priced
        for field in ("latency_cycles", "occupancy_cycles")
    }
    params.update(
        {
            "memory.immutable_access_cycles": 1,
            "cpu.issue_cycles": 1,
            "cpu.branch.taken_penalty_cycles": 3,
            "cpu.branch.not_taken_penalty_cycles": 0,
            "memory.l1i.hit_cycles": 1,
            "memory.l1i.miss_cycles": 2,
            "memory.l1d.hit_cycles": 1,
            "memory.l1d.miss_cycles": 2,
            "memory.dram_latency_cycles": 10,
            "memory.dram_per_byte_cycles": 0.25,
            "memory.snoop_cycles": 2,
        }
    )
    domain = {
        k: "0" * 64
        for k in (
            "device_sha256",
            "feature_engine_sha256",
            "feature_schema_sha256",
            "label_engine_sha256",
            "memory_regime_sha256",
            "scope_sha256",
        )
    }
    domain.update(feature_engine_sha256=engine_sha, label_engine="firesim")
    cache = {
        "sets": 16,
        "ways": 2,
        "line_bytes": 64,
        "policy": "write_back_write_allocate",
    }
    return {
        "schema": "merlin.annotated_spike_model.v1",
        "profile": "phase1-public",
        "domain": domain,
        "scope": {"kind": "counter_pair", "index": 0},
        "libraries": [],
        "cpu": {"isa": "rv64imafdc_zicntr_zihpm"},
        "resources": [
            {"id": 0, "name": "cpu.issue", "capacity": 1, "queue_capacity": 0},
            {"id": 1, "name": "cpu.execution", "capacity": 1, "queue_capacity": 2},
            {"id": 2, "name": "memory.shared", "capacity": 1, "queue_capacity": 2},
        ],
        "cpu_execution_resources": {kind: "cpu.execution" for kind in kinds},
        "parameters": params,
        "memory": {
            "coherence_granule": 64,
            "coherence_policy": "writeback_invalidate",
            "caches": {"l1i": dict(cache), "l1d": dict(cache)},
            "paths": {"cpu_fetch": ["l1i"], "cpu_data": ["l1d"], "device": []},
        },
    }


def run(argv, **kw):
    return subprocess.run(
        [str(x) for x in argv],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        **kw,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build-dir", required=True, type=Path)
    ap.add_argument("--baseline", type=Path)
    args = ap.parse_args()
    build = args.build_dir.absolute()
    elf = build / "native-cpu.elf"
    profile = build / "native-test-model.json"
    output = build / "native-test-report.json"
    run(
        [
            "clang",
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            "-fuse-ld=lld",
            "-Wl,-T," + str(ROOT / "timing/tests/elf/link.ld"),
            ROOT / "timing/tests/elf/cpu.S",
            "-o",
            elf,
        ]
    )
    model = fixture_model(
        json.loads((build / "timing-source-manifest.json").read_text())["sha256"]
    )
    profile.write_text(json.dumps(model))
    base_args = ["--isa=rv64gc_zicntr_zihpm", "--priv=m", "-m64"]
    baseline = run([args.baseline or build / "spike", *base_args, elf])

    def observe(changed, executable=None):
        profile.write_text(json.dumps(changed))
        execution = run(
            [
                build / "spike",
                *base_args,
                "--timing-model=" + str(profile),
                "--timing-report=" + str(output),
                "--timing-input-sha256=" + hashlib.sha256(b"").hexdigest(),
                executable or elf,
            ]
        )
        return execution, json.loads(output.read_text())

    annotated, report = observe(model)
    assert baseline.stdout == annotated.stdout, (baseline.stdout, annotated.stdout)
    assert report["functional_status"] == "PASS"
    assert report["timing_complete"], report["unresolved"]
    assert report["estimated_cycles"] > 0
    assert report["engine_qualification"] == "not_established"
    assert report["unresolved"] == []
    assert report["aborted_instructions"] == 0
    (build / "native-complete-report.json").write_text(json.dumps(report))
    (build / "native-complete-model.json").write_text(json.dumps(model))
    limited = subprocess.run(
        [
            str(build / "spike"),
            *base_args,
            "--instructions=10",
            "--timing-model=" + str(profile),
            "--timing-report=" + str(output),
            "--timing-input-sha256=" + hashlib.sha256(b"").hexdigest(),
            str(elf),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert limited.returncode == 0
    limit_report = json.loads(output.read_text())
    assert limit_report["execution_completed"] is False
    assert (
        limit_report["functional_status"] == "FAIL"
        and not limit_report["timing_complete"]
    )
    original_cycles = report["estimated_cycles"]
    changed = json.loads(json.dumps(model))
    changed["parameters"]["cpu.branch.taken_penalty_cycles"] += 20
    _, branch = observe(changed)
    assert branch["estimated_cycles"] >= original_cycles + 40, (
        original_cycles,
        branch["estimated_cycles"],
    )
    changed = json.loads(json.dumps(model))
    changed["profile"] = "historical-private"
    _, private = observe(changed)
    assert private["estimated_cycles"] == original_cycles
    assert private["feature_counts"] == report["feature_counts"]
    for mutation, reason in (
        (
            lambda x: x["parameters"].pop("cpu.fp_add.f32.latency_cycles"),
            "event timing",
        ),
        (
            lambda x: x["domain"].update(feature_engine_sha256="f" * 64),
            "feature engine",
        ),
        (lambda x: x.update(libraries=["f" * 64]), "libraries"),
    ):
        changed = json.loads(json.dumps(model))
        mutation(changed)
        _, refusal = observe(changed)
        assert not refusal["timing_complete"] and refusal["estimated_cycles"] is None
        assert any(reason in value for value in refusal["unresolved"]), refusal
    trap_elf = build / "native-trap.elf"
    run(
        [
            "clang",
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            "-fuse-ld=lld",
            "-Wl,-T," + str(ROOT / "timing/tests/elf/link.ld"),
            ROOT / "timing/tests/elf/trap.S",
            "-o",
            trap_elf,
        ]
    )
    _, trap = observe(model, trap_elf)
    assert trap["functional_status"] == "PASS" and trap["aborted_instructions"] > 0
    assert not trap["timing_complete"] and trap["estimated_cycles"] is None
    tainted_source = build / "native-tainted.S"
    tainted_source.write_text(
        (ROOT / "timing/tests/elf/cpu.S")
        .read_text()
        .replace("  li t0, 7", "  beqz s0, clock_branch\nclock_branch:\n  li t0, 7")
    )
    tainted_elf = build / "native-tainted.elf"
    run(
        [
            "clang",
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            "-fuse-ld=lld",
            "-Wl,-T," + str(ROOT / "timing/tests/elf/link.ld"),
            tainted_source,
            "-o",
            tainted_elf,
        ]
    )
    _, tainted = observe(model, tainted_elf)
    assert tainted["functional_status"] == "PASS" and not tainted["timing_complete"]
    assert any("counter-derived" in value for value in tainted["unresolved"])
    mmio_source = build / "native-mmio.S"
    mmio_source.write_text(
        (ROOT / "timing/tests/elf/cpu.S")
        .read_text()
        .replace("  li t0, 7", "  li t0, 0x200bff8\n  ld t1, 0(t0)\n  li t0, 7")
    )
    mmio_elf = build / "native-mmio.elf"
    run(
        [
            "clang",
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            "-fuse-ld=lld",
            "-Wl,-T," + str(ROOT / "timing/tests/elf/link.ld"),
            mmio_source,
            "-o",
            mmio_elf,
        ]
    )
    _, mmio = observe(model, mmio_elf)
    assert mmio["functional_status"] == "PASS" and not mmio["timing_complete"]
    assert any("MMIO" in value for value in mmio["unresolved"])
    print(
        json.dumps(
            {
                "status": "PASS",
                "architectural_counter_stdout": annotated.stdout,
                "instructions": report["instructions"],
                "synthetic_estimated_cycles": report["estimated_cycles"],
            }
        )
    )


if __name__ == "__main__":
    main()
