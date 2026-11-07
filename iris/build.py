#!/usr/bin/env python3
"""Build Iris Spike from this repository with byte-verified component SDKs."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time

IRIS = Path(__file__).resolve().parent
ROOT = IRIS.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


M = module("iris_native_model", IRIS / "tools/native_model.py")


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True,
                        help="Cache root containing the twelve exact SDK archives in iris/sdk-inputs.json")
    parser.add_argument("--verilator-include", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True, help="Fresh output directory")
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--dtc", type=Path, help="Device tree compiler, if absent from PATH")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 256:
        parser.error("--jobs must be between 1 and 256")
    build = args.build.resolve()
    build.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    receipt = dict(schema="iris.vendored_native_build.v1", status="building", hardware_contacted=False,
                   clean_native_rebuild=True, source_changes=[], commands=[])
    receipt_path = build / "build.json"

    def save():
        receipt["host_seconds"] = time.monotonic() - start
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    def phase(name, argv, env):
        print("Building " + name + " (log: " + str(build / (name + ".log")) + ")", flush=True)
        with (build / (name + ".log")).open("w") as log:
            proc = subprocess.Popen(argv, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                code = proc.wait(timeout=1800)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        receipt["commands"].append(dict(phase=name, argv=argv, exit_status=code))
        save()
        if code:
            raise ValueError(name + " failed; see " + str(build / (name + ".log")))

    try:
        sdk = M.load(IRIS / "sdk-inputs.json")
        libs = [args.sdk_root.resolve() / name for name in sdk["libraries"]]
        sdk_inputs = {str(path): digest for path, digest in zip(libs, sdk["libraries"].values())}
        runtime = args.verilator_include.resolve()
        sdk_inputs.update({str(runtime / name): digest for name, digest in sdk["verilator_include_sha256"].items()})
        M.checked(sdk_inputs)
        paths = []
        for folder in ("riscv", "fesvr", "spike_main", "softfloat", "fdt", "disasm", "customext", "iris"):
            paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                         and not any(part in ("__pycache__", ".build") for part in p.parts)
                         and build not in p.parents and p.suffix not in (".pyc", ".md")
                         and p.name != "results.json")
        paths += [ROOT / name for name in ("configure", "Makefile.in", "config.h.in", "aclocal.m4", "VERSION")]
        paths += list((ROOT / "scripts").glob("*"))
        compiler = Path(shutil.which("g++")).resolve()
        paths += [compiler, Path(shutil.which("gcc")).resolve(), Path(sys.executable).resolve()]
        env = dict(os.environ)
        dtc = args.dtc.resolve() if args.dtc else None
        if dtc:
            if not dtc.is_file():
                raise ValueError("Missing dtc: " + str(dtc))
            env["PATH"] = str(dtc.parent) + os.pathsep + env["PATH"]
        dtc = Path(shutil.which("dtc", path=env["PATH"]) or "")
        if not dtc.is_file():
            raise ValueError("Install dtc or provide --dtc")
        paths.append(dtc.resolve())
        inputs = {str(p.resolve()): M.sha(p) for p in paths if p.is_file()}
        inputs.update(sdk_inputs)
        receipt["input_sha256"] = inputs
        receipt["source_changes"] = subprocess.check_output(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=normal"], text=True).splitlines()
        includes = [IRIS / name for name in sdk["native_include_directories"]] + [runtime, runtime / "vltstd"]
        flags = "-O2 -g0 -std=c++20 " + " ".join("-I" + shlex.quote(str(p)) for p in includes)
        libraries = "-Wl,--start-group " + " ".join(shlex.quote(str(p)) for p in libs) + " -Wl,--end-group -pthread -lstdc++ -lm"
        phase("configure", [str(ROOT / "configure"), "--with-boost=no", "--with-boost-asio=no",
              "--with-boost-regex=no", "CXX=" + str(compiler), "CXXFLAGS=" + flags, "LIBS=" + libraries], env)
        phase("native", ["make", "-j" + str(args.jobs), "spike"], env)
        for name in ("riscv", "fesvr", "fdt"):
            (build / name).symlink_to(ROOT / name, target_is_directory=True)
        phase("uart", [str(compiler), "-std=c++20", "-O2", "-I" + str(build),
              "-iquote", str(ROOT / "riscv"), "-I" + str(IRIS / "board"),
              "-I" + str(IRIS / "board/uart-device"), "-fPIC", "-shared",
              str(IRIS / "pipeline/uart-plugin-abi4.cc"), "-o", str(build / "libsifive_uart.so")], env)
        boot = M.load(IRIS / "boot/inputs.json")
        for name, filename in (("bootrom", "bootrom.img"), ("dtb", "iris.dtb")):
            value = boot["inputs"][name]
            data = bytes.fromhex((IRIS / "boot" / value["hex"]).read_text())
            target = build / filename
            target.write_bytes(data)
            if len(data) != value["bytes"] or M.sha(target) != value["sha256"]:
                raise ValueError("Board boot input differs: " + name)
        launch = module("iris_native_launcher", IRIS / "tools/empirical_launch_v2.py")
        launcher = build / "spike-launch"
        python = Path(sys.executable).resolve()
        launcher.write_text(launch.launcher_text(build / "spike", M.sha(build / "spike"), python, M.sha(python)))
        launcher.chmod(0o755)
        receipt["output_sha256"] = {name: M.sha(build / name) for name in
                                    ("spike", "spike-launch", "libsifive_uart.so", "bootrom.img", "iris.dtb")}
        M.checked(inputs)
        receipt.update(status="built", source_image_association_verified=False,
                       accuracy_2percent_certified=False, historical_validation_transferred=False)
        save()
        release = M.load(IRIS / "release.json")
        for profile in ("source_compute", "source_os"):
            output = build / profile
            output.mkdir()
            closure = {**inputs, str(receipt_path): M.sha(receipt_path),
                       **{str(build / name): digest for name, digest in receipt["output_sha256"].items()}}
            descriptor = dict(schema="iris.empirical_simulator.v1", package_kind=M.KIND, profile=profile,
                calibration_identity=release["profiles"][profile]["calibration_identity"],
                model_provider=str(IRIS / "tools/native_model.py"), build_receipt=str(receipt_path),
                native_binary=str(build / "spike"), native_binary_sha256=M.sha(build / "spike"),
                binary=str(launcher), binary_sha256=M.sha(launcher), input_sha256=closure)
            path = output / "manifest.json"
            path.write_text(json.dumps(descriptor, indent=2) + "\n")
            M.verify(path)
        print(json.dumps(dict(status="built", native_binary_sha256=M.sha(build / "spike"),
                              descriptors=[str(build / p / "manifest.json") for p in ("source_compute", "source_os")],
                              accuracy_2percent_certified=False)))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        receipt.update(status="failed", error=str(error))
        save()
        parser.exit(1, "Iris native build: " + str(error) + "\n")


if __name__ == "__main__":
    sys.exit(main())
