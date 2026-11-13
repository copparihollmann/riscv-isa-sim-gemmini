#!/usr/bin/env python3
"""Exercise actual guest-visible event-clock semantics; no accuracy claim."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition: raise RuntimeError(message)


def rows(text, prefix):
    return [json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]


def symbols(elf, nm):
    text = subprocess.check_output([str(nm), "-n", str(elf)], text=True)
    return {parts[2]: int(parts[0], 16) for line in text.splitlines()
            if len(parts := line.split()) == 3 and parts[1] != "U"}


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--binary", type=Path, default=ROOT / "spike/build/spike")
    p.add_argument("--compiler", type=Path, default=Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc"))
    p.add_argument("--dtc", type=Path, default=Path("/scratch/eygao/iris-cy/.conda-env/bin/dtc"))
    p.add_argument("--output", type=Path, default=ROOT / "build/timing-live")
    args = p.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    binary = out / "spike"
    if args.binary.resolve() != binary: shutil.copy2(args.binary, binary)
    subprocess.run(["strip", str(binary)], check=True)
    uart = out / "libsifive_uart.so"
    cxx = shutil.which("g++")
    subprocess.run([cxx, "-std=c++20", "-O2", "-fPIC", "-shared", "-I" + str(ROOT / "spike/include"),
                    "-I" + str(ROOT / "spike/build"), str(ROOT / "spike/devices/src/sifive_uart.cc"), "-o", str(uart)], check=True)
    compiler = args.compiler.resolve()
    base_build = [str(compiler), "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-builtin",
                  "-fno-tree-vectorize", "-mcmodel=medany", "-mabi=lp64d", "-march=rv64gcv_zicsr_zifencei",
                  "-nostdlib", "-static", "-Wl,--build-id=none,--gc-sections", "-I" + str(ROOT / "benchmarks"),
                  "-T", str(ROOT / "benchmarks/link.ld")]
    builds = []
    for name, source in [("counter", "counter_guest.c"), ("order", "order_guest.S"), ("exit", "exit_guest.S")]:
        files = [str(ROOT / "timing" / source)]
        if name == "counter": files = [str(ROOT / "benchmarks/start.S"), str(ROOT / "benchmarks/runtime.c")] + files
        command = base_build + files + ["-lgcc", "-o", str(out / (name + ".elf"))]
        result = subprocess.run(command, text=True, capture_output=True)
        (out / (name + ".build.log")).write_text(result.stdout + result.stderr)
        require(result.returncode == 0, name + " build failed")
        builds.append(command)
    nm = compiler.with_name("riscv64-unknown-elf-nm")
    env = dict(os.environ); env["PATH"] = str(args.dtc.resolve().parent) + os.pathsep + env["PATH"]
    command = [str(binary), "--iris-vme", "--isa=rv64gcv_zfh_zvfh_zicntr_zihpm_zvl256b", "-p3",
               "-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000",
               "--extlib=" + str(uart), "--device=sifive_uart,0x10020000"]
    results = []
    negative_results = []

    def run(name, guest, profile, seed=None):
        fixture = out / (name + ".fixture"); fixture.write_text(profile)
        graph_path = out / (name + ".graph.json")
        cmd = command + ["--iris-timing-fixture=" + str(fixture), "--iris-timing-trace=" + str(graph_path)]
        if seed is not None: cmd.append("--iris-schedule-seed=" + str(seed))
        cmd.append(str(out / (guest + ".elf")))
        started = time.perf_counter()
        proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=60)
        elapsed = time.perf_counter() - started
        stdout, stderr = out / (name + ".stdout"), out / (name + ".stderr")
        stdout.write_text(proc.stdout); stderr.write_text(proc.stderr)
        require(proc.returncode == 0, name + " guest failed: " + proc.stderr)
        graph = json.loads(graph_path.read_text())
        results.append({"name": name, "argv": cmd, "pass": True, "elf_sha256": sha(out / (guest + ".elf")),
                        "fixture_sha256": sha(fixture), "graph_sha256": sha(graph_path),
                        "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
                        "host_seconds": elapsed, "global_base_cycles": graph["cycles"],
                        "retired_instructions": graph["retired_instructions"],
                        "simulated_mips": sum(graph["retired_instructions"]) / elapsed / 1e6,
                        "timing_accuracy_certified": False})
        return proc.stdout, graph

    fast = (ROOT / "timing/fixtures/three-hart-fast.fixture").read_text()
    slow = (ROOT / "timing/fixtures/three-hart-slow.fixture").read_text()
    observations = {}
    fault = symbols(out / "counter.elf", nm)["iris_counter_fault"]
    time_fault = symbols(out / "counter.elf", nm)["iris_counter_time_fault"]
    for name, profile in [("counter-fast", fast), ("counter-slow", slow),
                          ("counter-idle-gated", slow.replace(" 1 1\n", " 1 0\n").replace("hart 2 2 1", "hart 2 2 0"))]:
        text, graph = run(name, "counter", profile)
        measured = rows(text, "IRIS_TIMING ")
        require({r["hart"] for r in measured} == {0, 1, 2} and len(measured) == 3, "all harts must report")
        require("PASSED timing integration" in text, "counter guest golden failed")
        for row in measured:
            require(row["frozen"] == row["ret_frozen"] == 0, "counter inhibit failed")
            require(row["ret_written"] == 100 and row["illegal"] == row["woke"] == 1, "counter/trap/wakeup semantics")
            require(row["rdtime_illegal"] == 1, "source-absent CSR time must trap")
            require(row["time_before"] <= row["clint"] <= row["time_after"], "CLINT time regressed")
        nodes = {e["id"]: e for e in graph["events"]}
        fault_nodes = [e for e in nodes.values() if e["pc"] in [fault,time_fault]]
        for pc in [fault,time_fault]:
            require({e["hart"] for e in fault_nodes if e["pc"]==pc} == {0, 1, 2}, "fault coverage missing")
        for event in fault_nodes:
            traps = [n for n in nodes.values() if n["name"] == "trap-entry" and event["id"] in n["deps"]]
            require(len(traps) == 1 and traps[0]["start"] >= event["end"] and traps[0]["end"] - traps[0]["start"] == 4,
                    "synchronous fault missing its single trap cost")
        observations[name] = {r["hart"]: r for r in measured}
    for hart in range(3):
        a, b = observations["counter-fast"][hart], observations["counter-slow"][hart]
        require(a["instructions"] == b["instructions"] and a["cycles"] < b["cycles"], "modeled cycles must vary independently of retired count")
        require(observations["counter-idle-gated"][hart]["wake_cycles"] < b["wake_cycles"], "idle clock policy ignored")
    first = run("counter-seed", "counter", slow, 42)
    second = run("counter-seed-repeat", "counter", slow, 42)
    require(first == second, "recorded seed is not reproducible")
    # These fixtures deliberately allow independently outstanding read/write
    # events. They test completion causality, not real Iris coherence latency.
    for name, load, store, expected in [("load-first", 2, 40, 0), ("store-first", 40, 2, 99)]:
        profile = slow.replace("hart 2 2 1", "hart 2 1 1")
        lines = profile.splitlines()
        rules = [f"rule {h} 0x7f 0x03 shared_memory {load} 1 load base_cycles" for h in range(3)]
        rules += [f"rule {h} 0x7f 0x23 shared_memory {store} 1 store base_cycles" for h in range(3)]
        at = next(i for i, line in enumerate(lines) if line.startswith("rule "))
        profile = "\n".join(lines[:at] + rules + lines[at:]).replace("instruction base_cycles", "instruction base_cycles") + "\n"
        text, graph = run("order-" + name, "order", profile)
        require(rows(text, "IRIS_ORDER ") == [{"observed": expected}], "shared memory became visible at the wrong event")
        syms = symbols(out / "order.elf", nm)
        stores = [e for e in graph["events"] if e["hart"] == 0 and e["pc"] == syms["iris_order_store"]]
        loads = [e for e in graph["events"] if e["hart"] == 1 and e["pc"] == syms["iris_order_load"]]
        require(len(stores) == len(loads) == 1, "order test operation missing")
        require((loads[0]["end"] < stores[0]["end"]) == (expected == 0), "test did not reverse completion order")
    text, graph = run("exit-busy-peers", "exit", slow)
    exit_pc = symbols(out / "exit.elf", nm)["iris_exit_store"]
    exit_nodes = [e for e in graph["events"] if e["hart"] == 0 and e["pc"] == exit_pc]
    require(len(exit_nodes) == 1 and exit_nodes[0]["end"] == graph["cycles"], "simulation advanced beyond exit-store completion")
    # Check what software sees in the generated device tree as well as counters.
    fixture = out / "counter-slow.fixture"
    dts_cmd = command + ["--iris-timing-fixture=" + str(fixture), "--dump-dts", str(out / "counter.elf")]
    dts = subprocess.check_output(dts_cmd, env=env, text=True, stderr=subprocess.PIPE)
    (out / "fixture.dts").write_text(dts)
    clocks = {}
    for match in re.finditer(r"cpu@(\d+)\s*\{(.*?)clock-frequency\s*=\s*<([^>]+)>", dts, re.S):
        clocks[int(match[1])] = int(match[3].strip(), 0)
    require(clocks == {0: 100000000, 1: 100000000, 2: 50000000}, "per-hart DTB frequencies disagree with modeled clocks")
    for name, profile, expected in [
            ("no-calibration-claim", slow.replace("uncalibrated-integration-fixture", "calibrated"), "only explicit uncalibrated"),
            ("missing-hart", slow.replace("hart 2 2 1\n", ""), "missing/non-integral hart clock"),
            ("negative-latency", slow.replace("scalar0 7 1", "scalar0 -7 1"), "negative/empty timing parameter")]:
        path = out / (name + ".fixture"); path.write_text(profile)
        cmd = command + ["--iris-timing-fixture=" + str(path), str(out / "counter.elf")]
        proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=10)
        (out / (name + ".stderr")).write_text(proc.stderr)
        require(proc.returncode != 0 and expected in proc.stderr, "invalid timing profile did not fail closed: " + name)
        negative_results.append({"name": name, "pass": True, "exit_status": proc.returncode,
                                 "fixture_sha256": sha(path), "stderr_sha256": sha(out / (name + ".stderr"))})
    receipt = {"schema_version": 1, "status": "passed_integration_fixtures", "binary_sha256": sha(binary),
               "uart_sha256": sha(uart), "compiler_sha256": sha(compiler), "build_commands": builds,
               "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__).resolve(),
                   ROOT / "timing/counter_guest.c", ROOT / "timing/order_guest.S", ROOT / "timing/exit_guest.S",
                   ROOT / "timing/fixtures/three-hart-fast.fixture", ROOT / "timing/fixtures/three-hart-slow.fixture",
                   ROOT / "benchmarks/start.S", ROOT / "benchmarks/runtime.c", ROOT / "benchmarks/runtime.h",
                   ROOT / "benchmarks/uart_drain.h", ROOT / "benchmarks/uart_drain.S", ROOT / "benchmarks/link.ld"]},
               "results": results, "negative_results": negative_results, "dtb_clock_hz": clocks,
               "generated_dts_sha256": sha(out / "fixture.dts"),
               "calibrated": False, "iris_accuracy_certified": False,
               "scope": "Conservative one-in-flight instruction per hart; synthetic explicit costs test live hooks, not Iris performance."}
    (out / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "checks": len(results), "receipt": str(out / "results.json")}))


if __name__ == "__main__": main()
