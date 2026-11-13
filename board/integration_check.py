#!/usr/bin/env python3
"""Run ordinary ELFs through Iris's physical reset ROM in the integrated fork."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.validate_console import validate
from spike.run_functional import command, symbols


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--binary", type=Path, default=ROOT / "build/timing-live/spike")
    p.add_argument("--uart", type=Path, default=ROOT / "build/timing-live/libsifive_uart.so")
    p.add_argument("--output", type=Path, default=ROOT / "build/board-integration")
    p.add_argument("--compiler", type=Path, default=Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc"))
    p.add_argument("--build-only", action="store_true")
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    rom, dtb = ROOT / "board/evidence/bootrom.rv64.img", ROOT / "board/build/iris.dtb"
    corpus = json.loads((ROOT / "benchmarks/calibration-corpus.json").read_text())
    env = dict(os.environ); env["PATH"] = "/scratch/eygao/iris-cy/.conda-env/bin:" + env["PATH"]
    base = [str(args.compiler.resolve()), "-O2", "-g", "-Wall", "-Wextra", "-Wno-unused-variable",
            "-Werror", "-ffreestanding", "-fno-builtin", "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
            "-mcmodel=medany", "-mabi=lp64d", "-march=rv64gcv_zicsr_zifencei",
            "-I" + str(ROOT / "benchmarks")]
    runtime_object = out / "pma-runtime.o"
    builds = [base + ["-Dtrap_dispatch=base_trap_dispatch", "-c", str(ROOT / "benchmarks/runtime.c"), "-o", str(runtime_object)]]
    link = ["-nostdlib", "-static", "-Wl,--build-id=none,--gc-sections", "-T", str(ROOT / "benchmarks/link.ld")]
    builds.append(base + link + [str(ROOT / "benchmarks/start.S"), str(runtime_object),
                                str(ROOT / "board/pma_guest.c"), "-lgcc", "-o", str(out / "pma.elf")])
    # This fixture must use its own current CRT/runtime. Reusing a previous
    # timing run's ELF can lose queued UART output after a device epoch change.
    builds.append(base + link + [str(ROOT / "benchmarks/start.S"), str(ROOT / "benchmarks/runtime.c"),
                                str(ROOT / "timing/counter_guest.c"), "-lgcc", "-o", str(out / "counter.elf")])
    for mode in range(6):
        builds.append(base + link + ["-DCLINT_MODE=" + str(mode), str(ROOT / "benchmarks/start.S"),
                                    str(ROOT / "benchmarks/runtime.c"), str(ROOT / "board/clint_guest.c"),
                                    "-lgcc", "-o", str(out / ("clint-" + str(mode) + ".elf"))])
    for index, build in enumerate(builds):
        built = subprocess.run(build, text=True, capture_output=True)
        (out / ("guest-build-" + str(index) + ".log")).write_text(built.stdout + built.stderr)
        if built.returncode: raise RuntimeError("board guest build failed: " + built.stderr)
    if args.build_only:
        print(json.dumps({"status": "built_only", "guests": 8})); return
    results = []
    cases = [("smoke", ROOT / "benchmarks/build/smoke.elf"),
                      ("batch", ROOT / "benchmarks/build/batch.elf"),
                      ("counter-clock", out / "counter.elf"),
                      ("pma", out / "pma.elf"), ("pma-clock", out / "pma.elf")]
    cases += [("clint-" + str(mode), out / ("clint-" + str(mode) + ".elf")) for mode in range(6)]
    for name, elf in cases:
        cmd = command(args.binary.resolve(), elf)
        cmd = [("--extlib=" + str(args.uart.resolve())) if arg.startswith("--extlib=") else arg for arg in cmd]
        if name in ("counter-clock", "pma-clock"):
            cmd = [arg + "_zicntr_zihpm" if arg.startswith(("--isa=", "--hart-isa=")) and "zicntr" not in arg else arg for arg in cmd]
        options = ["--iris-bootrom=" + str(rom), "--dtb=" + str(dtb)]
        if name in ("counter-clock", "pma-clock"):
            graph = out / (name + ".graph.json")
            entry = symbols(elf)["_start"]
            options += ["--pc=" + hex(entry), "--iris-timing-fixture=" + str(ROOT / "timing/fixtures/three-hart-slow.fixture"),
                        "--iris-timing-trace=" + str(graph)]
        cmd = cmd[:-1] + options + cmd[-1:]
        start = time.perf_counter()
        result = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=60)
        elapsed = time.perf_counter() - start
        stdout, stderr = out / (name + ".stdout"), out / (name + ".stderr")
        stdout.write_text(result.stdout); stderr.write_text(result.stderr)
        diagnostic = {"clint-0": "uninitialized mtimecmp byte", "clint-1": "IRIS_CLINT_UNKNOWN_MTIP",
                      "clint-2": "IRIS_CLINT_UNKNOWN_MTIP", "clint-3": "uninitialized mtimecmp byte"}.get(name)
        if diagnostic:
            if result.returncode == 0 or diagnostic not in result.stderr:
                raise RuntimeError(name + " unknown reset state was not rejected: " + result.stderr)
        elif result.returncode:
            raise RuntimeError(name + " physical boot failed: " + result.stderr)
        if name in ("smoke", "batch"):
            proof = validate(result.stdout, corpus, 3, name == "smoke")
        elif name == "counter-clock":
            rows = [json.loads(line[len("IRIS_TIMING "):]) for line in result.stdout.splitlines() if line.startswith("IRIS_TIMING ")]
            if len(rows) != 3 or {row["hart"] for row in rows} != {0, 1, 2} or "PASSED timing integration" not in result.stdout:
                raise RuntimeError("physical counter guest did not complete on all harts")
            trace = json.loads(graph.read_text())
            for hart in range(3):
                first = next(event for event in trace["events"] if event["hart"] == hart)
                if first["pc"] != 0x10000:
                    raise RuntimeError("explicit ELF entry bypassed physical reset on hart " + str(hart))
            proof = {"actual_reset_pc": 0x10000, "all_harts_started_in_rom": True,
                     "guest_counters_and_timer_passed": True, "timing_accuracy_certified": False,
                     "graph_sha256": sha(graph)}
        elif name in ("pma", "pma-clock"):
            rows = [json.loads(line[len("IRIS_PMA "):]) for line in result.stdout.splitlines() if line.startswith("IRIS_PMA ")]
            if (len(rows) != 3 or {row["hart"] for row in rows} != {0, 1, 2} or
                any(row["faults"] != (17 if row["hart"]==2 else 19) or
                    row["private_aliases"] != (0 if row["hart"]==2 else 4) or
                    row["pmp_regions"] != (8 if row["hart"]==2 else 0) or
                    not row["uncached_lrsc_refused"] or not row["alias_peer_atomic_storage"] or
                    not row["ram_execute"] or not row["dram_last_page"] for row in rows) or
                "PASSED physical PMA" not in result.stdout):
                raise RuntimeError("PMA guest did not verify every hart and boundary")
            proof = {"faults_per_hart": [19,19,17], "private_aliases_per_hart": [4,4,0],
                     "pmp_regions_per_hart": [0,0,8], "uncached_lrsc_refused": True,
                     "alias_peer_atomic_shared_storage": True, "all_harts": True,
                     "tcm_scratchpad_execute": True, "dram_last_page": True, "rtl_certified": False}
            if name=="pma-clock": proof["graph_sha256"]=sha(graph)
        elif diagnostic:
            proof = {"expected_model_diagnostic": diagnostic, "exit_status": result.returncode,
                     "unknown_reset_state_refused": True}
        elif name == "clint-5":
            if "PASSED unobserved pending CSR" not in result.stdout:
                raise RuntimeError("unobserved pending CSR write falsely rejected")
            proof = {"rd_zero_does_not_expose_unknown_pending_bits": True}
        else:
            if "PASSED initialized CLINT compare and MTIP" not in result.stdout:
                raise RuntimeError("initialized CLINT guest failed")
            proof = {"partial_writes_complete_compare": True, "mtip_assert_deassert": True}
        results.append({"name": name, "argv": cmd, "pass": True, "proof": proof,
                        "elf_sha256": sha(elf), "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
                        "host_seconds": elapsed})
    record = {"schema_version": 1, "status": "passed_physical_boot_integration",
              "binary_sha256": sha(args.binary), "uart_sha256": sha(args.uart),
              "rom_sha256": sha(rom), "dtb_sha256": sha(dtb), "results": results,
              "compiler_sha256": sha(args.compiler), "build_commands": builds,
              "guest_source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in
                  [ROOT / "board/pma_guest.c", ROOT / "board/clint_guest.c", ROOT / "timing/counter_guest.c", ROOT / "benchmarks/start.S",
                   ROOT / "benchmarks/runtime.c", ROOT / "benchmarks/runtime.h", ROOT / "benchmarks/uart_drain.h", ROOT / "benchmarks/link.ld"]},
              "runner_sha256": sha(Path(__file__)), "rtl_certified": False, "zephyr_smp_certified": False,
              "board_model_complete": False,
              "remaining": ["unknown-reset PLIC state in the full device path", "complete MMIO behavior and transfer sizes",
                            "PLIC and UART equivalence", "source/image association", "actual Zephyr SMP execution"]}
    (out / "results.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"status": record["status"], "tests": len(results), "receipt": str(out / "results.json")}))


if __name__ == "__main__": main()
