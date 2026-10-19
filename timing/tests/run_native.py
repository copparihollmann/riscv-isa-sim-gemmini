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
    kinds = {"cpu." + name for name in re.findall(
        r"X\(([a-z_]+)\)", (ROOT / "timing/cpu_decode.hpp").read_text())} - {"cpu.unknown"}
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
    ap.add_argument("--clang", default="clang")
    ap.add_argument("--linker", default="lld", help="linker name or absolute executable path")
    args = ap.parse_args()
    compiler = args.clang
    linker = "--ld-path=" + args.linker if Path(args.linker).is_absolute() else "-fuse-ld=" + args.linker
    build = args.build_dir.absolute()
    elf = build / "native-cpu.elf"
    profile = build / "native-test-model.json"
    output = build / "native-test-report.json"
    run(
        [
            compiler,
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            linker,
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

    def observe(changed, executable=None, scope_binding=None):
        profile.write_text(json.dumps(changed))
        binding_args = []
        if scope_binding is not None:
            binding_path = build / "native-scope-binding.json"
            binding_path.write_text(json.dumps(scope_binding))
            binding_args = ["--timing-scope-binding=" + str(binding_path)]
        execution = run(
            [
                build / "spike",
                "--isa=" + changed["cpu"]["isa"],
                *base_args[1:],
                "--timing-model=" + str(profile),
                "--timing-report=" + str(output),
                "--timing-input-sha256=" + hashlib.sha256(b"").hexdigest(),
                *binding_args,
                executable or elf,
            ]
        )
        return execution, json.loads(output.read_text())

    annotated, report = observe(model)
    assert baseline.stdout == annotated.stdout, (baseline.stdout, annotated.stdout)
    assert report["functional_status"] == "PASS"
    assert report["schema"] == "merlin.annotated_spike_report.v2"
    assert report["feature_observation"]["complete"] is True
    assert report["feature_observation"]["counted_cpu_instructions"] == report["counter_windows"][0]["instructions"]
    assert report["timing_complete"], report["unresolved"]
    assert report["estimated_cycles"] > 0
    assert report["engine_qualification"] == "not_established"
    assert report["unresolved"] == []
    assert report["feature_counts"]["cpu.fp_sqrt"] == 0
    assert report["feature_counts"]["device.requested_read_bytes"] == 0
    assert report["feature_counts"]["cpu_fetch.requested_write_bytes"] == 0
    assert "cpu.fetch.requested_write_bytes" not in report["feature_counts"]
    assert "arbitrary.unsupported_feature" not in report["feature_counts"]
    assert report["aborted_instructions"] == 0
    (build / "native-complete-report.json").write_text(json.dumps(report))
    (build / "native-complete-model.json").write_text(json.dumps(model))
    bit_source, bit_elf = build / "native-bitmanip.S", build / "native-bitmanip.elf"
    bit_source.write_text((ROOT / "timing/tests/elf/cpu.S").read_text().replace(
        "  li t0, 7",
        "  li t0, 3\n  li t1, 5\n  sh2add t2, t0, t1\n  li t3, 17\n  bne t2, t3, fail\n"
        "  cpop t2, t2\n  li t3, 2\n  bne t2, t3, fail\n  bseti t2, t2, 4\n"
        "  li t3, 18\n  bne t2, t3, fail\n  li t0, 7", 1).replace(
            "rdcycle s0", "csrr s0, mcycle").replace("rdcycle s1", "csrr s1, mcycle"))
    run([compiler, "--target=riscv64-unknown-elf", "-march=rv64gc_zba_zbb_zbs", "-mabi=lp64d",
         "-nostdlib", linker, "-Wl,-T," + str(ROOT / "timing/tests/elf/link.ld"), bit_source, "-o", bit_elf])
    bit_model = json.loads(json.dumps(model))
    bit_model["cpu"]["isa"] = "rv64imafdcb_zicsr_zifencei_zihpm_zfh_zba_zbb_zbs"
    plain = run([args.baseline or build / "spike", "--isa=" + bit_model["cpu"]["isa"], *base_args[1:], bit_elf])
    execution, observed_bits = observe(bit_model, bit_elf)
    assert execution.stdout == plain.stdout
    assert observed_bits["feature_observation"]["complete"] is True, observed_bits["feature_observation"]
    assert observed_bits["timing_complete"] is True, observed_bits["unresolved"]
    assert observed_bits["feature_counts"]["cpu.bitmanip"] == 3
    bit_model["parameters"].pop("cpu.bitmanip.latency_cycles")
    _, unpriced_bits = observe(bit_model, bit_elf)
    assert unpriced_bits["feature_observation"]["complete"] is True
    assert unpriced_bits["timing_complete"] is False
    # Kernels can read counters internally; selected call boundaries must not
    # silently become consecutive internal reads. No guest counter is replaced.
    inner_source = build / "native-inner-counters.S"
    inner_source.write_text((ROOT / "timing/tests/elf/cpu.S").read_text().replace(
        "  li t0, 7", "  rdcycle zero\n  rdcycle zero\n  li t0, 7", 1))
    inner_elf = build / "native-inner-counters.elf"
    run([compiler, "--target=riscv64-unknown-elf", "-march=rv64gc", "-mabi=lp64d",
         "-nostdlib", linker, "-Wl,-T," + str(ROOT / "timing/tests/elf/link.ld"),
         inner_source, "-o", inner_elf])
    _, adjacent = observe(model, inner_elf)
    binding = {
        "schema": "merlin.spike_scope_binding.v1",
        "elf_sha256": hashlib.sha256(inner_elf.read_bytes()).hexdigest(),
        "input_sha256": hashlib.sha256(b"").hexdigest(),
        "scope_sha256": model["domain"]["scope_sha256"],
        "begin_pc": adjacent["counter_windows"][0]["begin_pc"],
        "end_pc": adjacent["counter_windows"][-1]["end_pc"],
        "occurrence": 0, "evidence_sha256": hashlib.sha256(inner_source.read_bytes()).hexdigest(),
    }
    pc_model = json.loads(json.dumps(model))
    pc_model["scope"] = {"kind": "counter_pc_pair"}
    _, pinned = observe(pc_model, inner_elf, binding)
    assert pinned["timing_complete"] and len(pinned["counter_windows"]) == 1
    assert pinned["scope_binding"] == binding
    assert pinned["counter_windows"][0]["instructions"] == report["counter_windows"][0]["instructions"] + 2
    assert pinned["estimated_cycles"] > adjacent["estimated_cycles"]
    wrong_boundary = dict(binding, end_pc=binding["end_pc"] + 2)
    _, unclosed = observe(pc_model, inner_elf, wrong_boundary)
    assert not unclosed["timing_complete"] and unclosed["estimated_cycles"] is None
    # One pricing file is shared by every ELF; scope bindings are per execution.
    assert pinned["model_sha256"] == unclosed["model_sha256"]
    profile.write_text(json.dumps(model))
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
        assert refusal["feature_observation"]["complete"] is (reason == "event timing")

    # A cycle-value spill is safe for count portability until data reaches a
    # timing-sensitive control/address/device use. Exercise actual store/load
    # aliasing and overwrites, not just register-to-register propagation.
    for name, injected, complete in (
        ("spill", "sd s0, -8(sp)\n  ld t6, -8(sp)", True),
        ("spill-branch", "sd s0, -8(sp)\n  ld t6, -8(sp)\n  beqz t6, spill_target\nspill_target:", False),
        ("spill-overwritten", "sd s0, -8(sp)\n  sd zero, -8(sp)\n  ld t6, -8(sp)\n  beqz t6, spill_target\nspill_target:", True),
        ("spill-partial", "sd s0, -8(sp)\n  sw zero, -8(sp)\n  ld t6, -8(sp)\n  beqz t6, spill_target\nspill_target:", False),
    ):
        source, executable = build / (name + ".S"), build / (name + ".elf")
        source.write_text((ROOT / "timing/tests/elf/cpu.S").read_text().replace("  li t0, 7", "  " + injected + "\n  li t0, 7", 1))
        run([compiler, "--target=riscv64-unknown-elf", "-march=rv64gc", "-mabi=lp64d",
             "-nostdlib", linker, "-Wl,-T," + str(ROOT / "timing/tests/elf/link.ld"), source, "-o", executable])
        plain = run([args.baseline or build / "spike", *base_args, executable])
        execution, observation = observe(model, executable)
        assert plain.stdout == execution.stdout
        assert observation["feature_observation"]["complete"] is complete, observation
        assert observation["timing_complete"] is complete, observation["unresolved"]
    trap_elf = build / "native-trap.elf"
    run(
        [
            compiler,
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            linker,
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
            compiler,
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            linker,
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
            compiler,
            "--target=riscv64-unknown-elf",
            "-march=rv64gc",
            "-mabi=lp64d",
            "-nostdlib",
            linker,
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
