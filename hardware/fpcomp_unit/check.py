#!/usr/bin/env python3
"""Exercise saved Iris FPComp RTL against an independent integer-only oracle.

This is a unit proof, not a complete instruction/OS test or timing calibration.
No Spike implementation or Spike oracle is imported.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SEED = 0x495249534650434D
FORMS = [
    ("vfmin.vv", 4, 1), ("vfmin.vf", 4, 5),
    ("vfmax.vv", 6, 1), ("vfmax.vf", 6, 5),
    ("vfsgnj.vv", 8, 1), ("vfsgnj.vf", 8, 5),
    ("vfsgnjn.vv", 9, 1), ("vfsgnjn.vf", 9, 5),
    ("vfsgnjx.vv", 10, 1), ("vfsgnjx.vf", 10, 5),
    ("vmfeq.vv", 24, 1), ("vmfeq.vf", 24, 5),
    ("vmfne.vv", 28, 1), ("vmfne.vf", 28, 5),
    ("vmflt.vv", 27, 1), ("vmflt.vf", 27, 5),
    ("vmfle.vv", 25, 1), ("vmfle.vf", 25, 5),
    ("vmfgt.vf", 29, 5), ("vmfge.vf", 31, 5),
    ("vfredmin.vs", 5, 1), ("vfredmax.vs", 7, 1),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def nan(value, width):
    fraction = {16: 10, 32: 23, 64: 52}[width]
    exponent = {16: 5, 32: 8, 64: 11}[width]
    return ((value >> fraction) & ((1 << exponent) - 1)) == (1 << exponent) - 1 and bool(value & ((1 << fraction) - 1))


def compare(a, b, width):
    """IEEE numeric comparison from signs and integer magnitudes, no host float."""
    magnitude = (1 << (width - 1)) - 1
    if (not (a & magnitude) and not (b & magnitude)) or a == b:
        return 0
    sa, sb = a >> (width - 1), b >> (width - 1)
    if sa != sb:
        return -1 if sa else 1
    return (-1 if a > b else 1) if sa else (-1 if a < b else 1)


def element(a, b, width, name):
    an, bn = nan(a, width), nan(b, width)
    op = name.split(".")[0]
    if op in ("vfmin", "vfmax", "vfredmin", "vfredmax"):
        if an and bn:
            return {16: 0x7E00, 32: 0x7FC00000, 64: 0x7FF8000000000000}[width]
        if an or bn:
            return b if an else a
        order = compare(a, b, width)
        return a if (order < 0 if op in ("vfmin", "vfredmin") else order > 0) else b
    if op.startswith("vfsgnj"):
        sign_a, sign_b = a >> (width - 1), b >> (width - 1)
        sign = (sign_b ^ 1) if op == "vfsgnjn" else (sign_a ^ sign_b) if op == "vfsgnjx" else sign_b
        return (a & ((1 << (width - 1)) - 1)) | (sign << (width - 1))
    if an or bn:
        return int(op == "vmfne")
    order = compare(a, b, width)
    return int({"vmfeq": order == 0, "vmfne": order != 0, "vmflt": order < 0,
                "vmfle": order <= 0, "vmfgt": order > 0, "vmfge": order >= 0}[op])


def oracle(case, dlen):
    width, name = case["width"], case["name"]
    lane_mask = (1 << width) - 1
    values = [element((case["a"] >> offset) & lane_mask, (case["b"] >> offset) & lane_mask, width, name)
              for offset in range(0, dlen, width)]
    if name.startswith("vmf"):
        pattern = sum(value << i for i, value in enumerate(values))
        data = sum(pattern << shift for shift in range(0, dlen, len(values)))
        # Mask output rotates the compressed byte mask into the destination EG.
        eew = int(math.log2(width // 8))
        stride = width // 8
        packed = sum(((case["wmask"] >> (i * stride)) & 1) << i for i in range(dlen // width))
        offset = (case["eidx"] & (dlen - 1)) & ~((1 << (int(math.log2(dlen // 8)) - eew)) - 1)
        write_mask = (packed << offset) & ((1 << dlen) - 1)
    else:
        data = sum(value << (i * width) for i, value in enumerate(values))
        write_mask = sum(255 << (i * 8) for i in range(dlen // 8) if case["wmask"] & (1 << i))
    # Source selects H-chunk flags for H/S outputs and S-chunk flags for D.
    # It compares every physical chunk, including masked-off/tail bytes.
    flag_width = 32 if width == 64 else 16
    flag_mask = (1 << flag_width) - 1
    flags = 16 if any(nan((value >> offset) & flag_mask, flag_width)
                      for value in (case["a"], case["b"]) for offset in range(0, dlen, flag_width)) else 0
    return {"data": data, "mask": write_mask, "flags": flags, "eg": case["eg"]}


def cases(dlen):
    rng = random.Random(SEED + dlen)
    for name, funct6, funct3 in FORMS:
        for width in (16, 32, 64):
            fraction = {16: 10, 32: 23, 64: 52}[width]
            exponent = {16: 5, 32: 8, 64: 11}[width]
            sign = 1 << (width - 1)
            inf = ((1 << exponent) - 1) << fraction
            edge = [0, sign, 1, sign | 1, inf, sign | inf, inf | 1,
                    inf | (1 << (fraction - 1)), inf - 1, sign | (inf - 1), 1 << fraction, sign | (1 << fraction)]
            for index in range(64):
                a, b = rng.getrandbits(dlen), rng.getrandbits(dlen)
                if index < 32:
                    a = sum(edge[(index + lane) % len(edge)] << (lane * width) for lane in range(dlen // width))
                    b = sum(edge[(3 * index + lane + 1) % len(edge)] << (lane * width) for lane in range(dlen // width))
                if index in (0, 1):
                    a, b = ((sign, 0) if index == 0 else (0, sign))
                # Hidden NaN chunks prove the source's surprising flag selector.
                if index in (32, 33, 34, 35):
                    a, b = ((0x7FC00000 if width == 64 else 0x7E00) << (dlen - (32 if width == 64 else 16))), 0
                wmask = [0, (1 << (dlen // 8)) - 1, rng.getrandbits(dlen // 8)][index % 3]
                yield {"name": name, "f6": funct6, "f3": funct3, "width": width,
                       "a": a, "b": b, "eidx": rng.randrange(256), "eg": rng.randrange(64),
                       "wmask": wmask, "rs1": rng.randrange(32), "rs2": rng.randrange(32)}


def stimuli(dlen):
    previous = None
    retained = None
    rows, expected, admitted = [], [], []
    all_cases = list(cases(dlen))
    for index, case in enumerate(all_cases):
        if index % 7 == 2:
            admitted.append(None)  # pipeline bubbles with changing stage 0 inputs
        admitted.append(case)
    admitted.extend([None, None])
    for index, current in enumerate(admitted):
        case = current or all_cases[(index * 37) % len(all_cases)]
        metadata = previous or case
        eew = int(math.log2(case["width"] // 8))
        stage1_eew = int(math.log2(metadata["width"] // 8))
        fields = [index, int(current is not None), int(previous is not None), case["f6"], case["f3"], eew, eew, eew,
                  case["rs1"], case["rs2"], metadata["eidx"], metadata["eg"], metadata["wmask"],
                  f'{case["a"]:0{dlen//4}x}', f'{case["b"]:0{dlen//4}x}', stage1_eew, stage1_eew]
        rows.append(" ".join(map(str, fields)))
        if previous is not None:
            retained = oracle(previous, dlen)
        expected.append({"id": index, "valid": int(previous is not None), "expected": retained,
                         "form": previous["name"] if previous else None})
        previous = current
    return "\n".join(rows) + "\n", expected


def validate(output, expected):
    lines = output.splitlines()
    if len(lines) != len(expected):
        raise ValueError("RTL output row count mismatch")
    valid_count = held_checks = 0
    for line, row in zip(lines, expected):
        fields = line.split()
        if len(fields) != 7:
            raise ValueError("malformed RTL output")
        index, valid, fvalid, eg = map(int, fields[:4])
        data, mask = map(lambda value: int(value, 16), fields[4:6])
        flags = int(fields[6])
        if (index, valid, fvalid) != (row["id"], row["valid"], row["valid"]):
            raise ValueError(f'pipeline valid mismatch at {row["id"]}')
        target = row["expected"]
        if target is None:
            continue  # uninitialized state is never asserted to be zero
        if data != target["data"]:
            raise ValueError(f'data mismatch at {index} {row["form"]}: got {data:x}, expected {target["data"]:x}')
        if valid:
            if (mask, flags, eg) != (target["mask"], target["flags"], target["eg"]):
                raise ValueError(f'mask/flags/EG mismatch at {index} {row["form"]}: got {(mask,flags,eg)}, expected {(target["mask"],target["flags"],target["eg"])}')
            valid_count += 1
        else:
            held_checks += 1
    return {"valid_outputs": valid_count, "bubble_register_holds": held_checks, "cycles": len(expected)}


def closure(module, generated):
    visited = {}
    def visit(name):
        if name in visited:
            return
        path = generated / (name + ".sv")
        if not path.is_file():
            raise ValueError(f"missing generated dependency {name}")
        visited[name] = path
        for child in re.findall(r"^\s*([A-Za-z_]\w*)\s+[A-Za-z_]\w*\s*\(", path.read_text(), re.M):
            if (generated / (child + ".sv")).is_file():
                visit(child)
    visit(module)
    return list(visited.values())


def run_command(argv, output, env=None):
    started = time.monotonic()
    result = subprocess.run(list(map(str, argv)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=240)
    output.write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): see {output}")
    return time.monotonic() - started


def verify(output):
    receipt = json.loads((output / "results.json").read_text())
    for path, digest in receipt["input_sha256"].items():
        if sha(path) != digest:
            raise ValueError(f"changed source/evidence: {path}")
        if sha(output / "inputs" / digest) != digest:
            raise ValueError(f"corrupt archived input: {path}")
    for path, digest in receipt["artifact_sha256"].items():
        if sha(output / path) != digest:
            raise ValueError(f"changed artifact: {path}")
    for row in receipt["units"]:
        expected = json.loads((output / row["expected"]).read_text())
        actual = (output / row["stdout"]).read_text()
        if validate(actual, expected) != row["checks"]:
            raise ValueError("replayed result count mismatch")
    return receipt


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rtl-build", type=Path, default=ROOT / "build/rtl-verilator")
    parser.add_argument("--toolchain", type=Path, default=Path("/scratch/eygao/iris-cy/.conda-env"))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    if args.verify:
        receipt = verify(out)
        print(json.dumps({"status": receipt["status"], "verified": True, "valid_outputs": sum(r["checks"]["valid_outputs"] for r in receipt["units"])}))
        return
    out.mkdir(parents=True, exist_ok=False)
    rtl_build = args.rtl_build.resolve()
    generated = rtl_build / "gen-collateral"
    rtl_manifest = json.loads((rtl_build / "manifest.json").read_text())
    perl = args.toolchain / "bin/perl"
    verilator = args.toolchain / "bin/verilator"
    verilator_root = args.toolchain / "share/verilator"
    compiler = Path(shutil.which("g++"))
    env = dict(os.environ, VERILATOR_ROOT=str(verilator_root), CXX=str(compiler))
    inputs = {str(path): sha(path) for path in [Path(__file__), HERE / "driver.cc", rtl_build / "manifest.json", ROOT / "hardware/manifest.json", perl, verilator,
              verilator_root / "bin/verilator_bin", compiler,
              ROOT / "third_party/saturn/src/main/scala/exu/fp/FPComp.scala",
              ROOT / "third_party/saturn/src/main/scala/insns/Instructions.scala"]}
    for path in (verilator_root / "include").rglob("*"):
        if path.is_file() and path.suffix in (".h", ".cpp", ".c"):
            inputs[str(path)] = sha(path)
    for name in ("make", "ar", "ranlib"):
        path = Path(shutil.which(name)).resolve()
        inputs[str(path)] = sha(path)
    rows = []
    for dlen, module in [(128, "FPCompPipe"), (256, "FPCompPipe_2")]:
        paths = closure(module, generated)
        for path in paths:
            if sha(path) != rtl_manifest["sim_source_sha256"].get(str(path)):
                raise ValueError(f"generated RTL does not match FIR build receipt: {path}")
            inputs[str(path)] = sha(path)
        model = out / ("model-" + str(dlen))
        argv = [perl, verilator, "--cc", "--exe", "--build", "-j", "4", "--top-module", module, "--prefix", "VFPComp",
                "-Wno-fatal", "-O3", "--Mdir", model, "-CFLAGS", f"-DFP_DLEN={dlen}", "-MAKEFLAGS", f"CXX={compiler} LINK={compiler} AR=ar RANLIB=ranlib",
                *paths, HERE / "driver.cc"]
        build_seconds = run_command(argv, out / (f"build-{dlen}.log"), env)
        stimulus, expected = stimuli(dlen)
        (out / f"stimuli-{dlen}.txt").write_text(stimulus)
        save(out / f"expected-{dlen}.json", expected)
        binary = model / "VFPComp"
        started = time.monotonic()
        process = subprocess.run([binary], input=stimulus, text=True, capture_output=True, timeout=30)
        (out / f"output-{dlen}.txt").write_text(process.stdout)
        (out / f"stderr-{dlen}.txt").write_text(process.stderr)
        if process.returncode:
            raise RuntimeError("RTL driver failed")
        libraries = subprocess.run(["ldd", binary], capture_output=True, text=True, check=True).stdout
        (out / f"ldd-{dlen}.txt").write_text(libraries)
        if "not found" in libraries:
            raise RuntimeError("unresolved runtime library")
        for value in re.findall(r"(?:=>\s*)?(/[^\s]+)", libraries):
            path = Path(value)
            if path.is_file():
                inputs[str(path)] = sha(path)
        checks = validate(process.stdout, expected)
        rows.append({"dlen": dlen, "module": module, "checks": checks, "build_argv": list(map(str, argv)),
                     "build_seconds": build_seconds, "run_seconds": time.monotonic() - started,
                     "binary": str(binary.relative_to(out)), "binary_sha256": sha(binary),
                     "expected": f"expected-{dlen}.json", "stdout": f"output-{dlen}.txt"})
    # These controls exercise the actual receipt checker, not just the arithmetic.
    sample = (out / "output-128.txt").read_text()
    expect = json.loads((out / "expected-128.json").read_text())
    fields = sample.splitlines()[1].split()
    fields[4] = f'{int(fields[4],16)^1:032x}'
    bad_data = sample.splitlines(); bad_data[1] = " ".join(fields)
    for mutation in ("\n".join(bad_data) + "\n", "\n".join(sample.splitlines()[:-1]) + "\n"):
        try:
            validate(mutation, expect)
        except ValueError:
            pass
        else:
            raise RuntimeError("negative checker control was incorrectly accepted")
    # Keep exact tool/source/library bytes as well as live input identities.
    (out / "inputs").mkdir()
    for path, digest in inputs.items():
        target = out / "inputs" / digest
        if not target.exists():
            shutil.copyfile(path, target)
    artifacts = {str(path.relative_to(out)): sha(path) for path in out.rglob("*") if path.is_file()}
    hardware = json.loads((ROOT / "hardware/manifest.json").read_text())
    receipt = {"schema": "iris.fpcomp_rtl_unit.v1", "status": "passed_saved_rtl_unit", "seed": SEED,
               "forms": [name for name, _, _ in FORMS], "widths": [16, 32, 64], "cases_per_form_width_dlen": 64,
               "units": rows, "checker_negative_controls": 2, "input_sha256": inputs, "artifact_sha256": artifacts,
               "source_fir_sha256": rtl_manifest["source_fir_sha256"], "host_float_used": False,
               "audited_source_revisions": {name: value["commit"] for name, value in hardware["repositories"].items()},
               "source_policy": {"path": str(ROOT / "third_party/saturn/src/main/scala/exu/fp/FPComp.scala"),
                   "factory_widths_forms_lines": [12, 21], "minmax_compare_lines": [49, 107],
                   "sign_injection_lines": [111, 138], "output_data_mask_flags_lines": [140, 178]},
               "rtl_executed": True, "full_instruction_certified": False, "timing_calibrated": False,
               "ethan_image_association_verified": False,
               "limitations": ["Unit inputs are sequencer outputs; scalar broadcast, instruction decode, mask generation and reduction folding are outside this unit test.",
                   "No reset-value assumption: comparisons start only after a valid pipeline input.",
                   "No SEW8/FP8/BF16 semantics: this factory admits IEEE H/S/D only, ignoring vector alternate format upstream.",
                   "Raw unit flags precede any upstream architectural fflags gating.",
                   "Saved IrisConfig FIR association to the requested source checkout and deployed FireSim image remains unverified."]}
    save(out / "results.json", receipt)
    verify(out)
    print(json.dumps({"status": receipt["status"], "valid_outputs": sum(row["checks"]["valid_outputs"] for row in rows), "receipt": str(out / "results.json")}))


if __name__ == "__main__":
    main()
