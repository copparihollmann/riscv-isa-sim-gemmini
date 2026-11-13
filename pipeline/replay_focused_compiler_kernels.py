#!/usr/bin/env python3
"""Fresh exact-native execution of preserved Merlin-generated kernel images."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(a):
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    native, uart, fixture = [p.resolve() for p in (a.binary, a.uart, a.fixture)]
    validator = ROOT / "integration/iris-mlir/examples/iris/run.py"
    spec = importlib.util.spec_from_file_location("iris_compiler_gate", validator)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ids = {str(p): sha(p) for p in (Path(__file__).resolve(), native, uart, fixture, validator)}
    report = dict(schema="iris.fresh_native_preserved_compiler_kernels.v1", passed=False,
                  hardware_contacted=False, fresh_compiler_invocation=False,
                  full_model_or_timing_certified=False, cases=[], input_sha256=ids)
    path = out / "report.json"
    def save():
        path.write_text(json.dumps(report, indent=2) + "\n")
    save()
    try:
        for op in ("gemm", "conv2d"):
            for workers in (1, 2):
                old_dir = ROOT / ("build/hybrid7bd5-selected-merlin-" + op + "-h" + str(workers) + "-v1")
                receipt = old_dir / "results.json"
                old = json.loads(receipt.read_text())
                if old["pass"] is not True:
                    raise ValueError("Preserved compiler gate failed")
                ids[str(receipt)] = sha(receipt)
                m, n, k = old["shape_mnk"]
                gold_i32, gold_w8a8 = mod.inputs_and_golden(op, m, n, k)
                for prior in old["runs"]:
                    elf = Path(prior["argv"][-1])
                    if sha(elf) != prior["elf_sha256"]:
                        raise ValueError("Compiled ELF changed")
                    ids[str(elf)] = sha(elf)
                    folder = out / (op + "-h" + str(workers) + "-" + prior["kind"])
                    folder.mkdir()
                    argv = [str(native), *prior["argv"][1:]]
                    argv = ["--extlib=" + str(uart) if x.startswith("--extlib=") else
                            "--iris-timing-fixture=" + str(fixture) if x.startswith("--iris-timing-fixture=") else x
                            for x in argv]
                    argv.insert(-1, "--iris-timing-trace=" + str(folder / "summary.json"))
                    for x in argv:
                        if x.startswith(("--iris-bootrom=", "--dtb=")):
                            p = Path(x.split("=", 1)[1])
                            ids[str(p)] = sha(p)
                    env = {k: v for k, v in os.environ.items() if not k.startswith("IRIS_EMPIRICAL_") and k != "IRIS_FATAL_PCS"}
                    env["IRIS_EMPIRICAL_FEATURES"] = str(folder / "features.jsonl")
                    started = time.monotonic()
                    with (folder / "stdout").open("wb") as so, (folder / "stderr").open("wb") as se:
                        result = subprocess.run(argv, stdout=so, stderr=se, timeout=a.timeout, env=env)
                    if result.returncode != 0:
                        raise ValueError("Native compiler-image execution failed: " + folder.name)
                    parsed = mod.parse((folder / "stdout").read_text(), m * n)
                    if parsed["ACC_I32"] != gold_i32 or parsed["OUT"] != gold_w8a8:
                        raise ValueError("Independent complete numerical golden failed")
                    regions = [list(map(int, line.split()[1:])) for line in (folder / "stdout").read_text().splitlines()
                               if line.startswith("REGION ")]
                    if sorted(r[0] for r in regions) != list(range(workers)) or any(len(r) != 4 or r[2] <= r[1] or r[3] <= 0 for r in regions):
                        raise ValueError("Every active hart actual CSR region required")
                    report["cases"].append(dict(op=op, workers=workers, kind=prior["kind"],
                        argv=argv, returncode=result.returncode, host_seconds=time.monotonic()-started,
                        accumulator_words=len(gold_i32), w8a8_words=len(gold_w8a8), regions=regions,
                        output_sha256={str(p): sha(p) for p in folder.iterdir() if p.is_file()}))
                    save()
        if any(sha(p) != digest for p, digest in ids.items()):
            raise ValueError("Inputs changed during execution")
        report["passed"] = True
    except Exception as e:
        report["error"] = str(e)
    finally:
        save()
    print(json.dumps(dict(passed=report["passed"], cases=len(report["cases"]), error=report.get("error"))))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    for key in ("binary", "uart", "fixture", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--timeout", type=int, default=180)
    raise SystemExit(main(p.parse_args()))
