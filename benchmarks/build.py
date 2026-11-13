#!/usr/bin/env python3
"""Build the Iris batched microbenchmarks and record exact input digests."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc"))
    parser.add_argument("--saturn", type=Path, default=here.parent / "third_party/saturn")
    parser.add_argument("--output", type=Path, default=here / "build")
    parser.add_argument("--harts", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    compiler, out, saturn = args.compiler.resolve(), args.output.resolve(), args.saturn.resolve()
    from golden import verify
    verify(json.loads((here / "calibration-corpus.json").read_text()))
    out.mkdir(parents=True, exist_ok=True)
    inputs = [here / name for name in ("start.S", "runtime.h", "runtime.c", "uart_drain.h", "batch.c", "link.ld", "build.py")]
    inputs.append(saturn / "benchmarks/common/vme.h")
    inputs += [here / "golden.py", here / "calibration-corpus.json"]
    provenance = {
        "schema_version": 1, "compiler": str(compiler), "compiler_sha256": digest(compiler),
        "compiler_version": subprocess.check_output([str(compiler), "--version"]).decode().splitlines()[0],
        "saturn_commit": subprocess.check_output(["git", "-C", str(saturn), "rev-parse", "HEAD"]).decode().strip(),
        "input_sha256": {str(path): digest(path) for path in inputs},
        "harts": args.harts, "executed": False, "artifacts": [],
    }
    for name, defines in (("smoke", ["-DIRIS_SMOKE=1"]), ("batch", [])):
        elf = out / (name + ".elf")
        command = [str(compiler), "-O2", "-g", "-Wall", "-Wextra", "-Wno-unused-function", "-Werror",
                   "-ffreestanding", "-fno-builtin", "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
                   "-ffunction-sections", "-fdata-sections", "-fno-common", "-mcmodel=medany", "-mabi=lp64d",
                   "-march=rv64gcv_zicsr_zifencei", "-nostdlib", "-static", "-Wl,--build-id=none,--gc-sections",
                   "-DIRIS_HARTS=" + str(args.harts), *defines, "-I" + str(saturn / "benchmarks/common"),
                   "-T", str(here / "link.ld"), str(here / "start.S"), str(here / "runtime.c"), str(here / "batch.c"),
                   "-lgcc", "-o", str(elf)]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = out / (name + ".build.log")
        log.write_text(completed.stdout)
        if completed.returncode:
            raise SystemExit(completed.stdout)
        artifact = {"name": name, "path": str(elf), "sha256": digest(elf), "command": command,
                    "build_log_sha256": digest(log), "executed": False}
        provenance["artifacts"].append(artifact)
        print(name + ": " + str(elf) + " sha256=" + artifact["sha256"])
    (out / "build.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
