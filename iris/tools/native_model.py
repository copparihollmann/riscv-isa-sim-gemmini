"""Development descriptors for binaries built from the model vendored here.

Build identity is distinct from the archived 35a binary's validation. This
provider offers experimental execution and makes no inherited accuracy claim.
"""

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIMULATOR = ROOT / "iris"
KIND = "iris.vendored_native_development.v1"
MEMORY = [[0x70000000, 0x40000], [0x80000000, 0x100000000], [0x580000000, 0x20000]]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate JSON key: " + key)
            out[key] = value
        return out

    def invalid(value):
        raise ValueError("Nonfinite JSON: " + value)

    result = json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result


def checked(inputs):
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError("Nonempty build input closure required")
    for name, digest in inputs.items():
        if (not Path(name).is_absolute() or not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest) or sha(name) != digest):
            raise ValueError("Native model input changed: " + name)


def launch_args(build, profile):
    return ["--iris-vme", "--extlib=" + str(build / "libsifive_uart.so"),
            "--device=sifive_uart,0x10020000", "--iris-bootrom=" + str(build / "bootrom.img"),
            "--dtb=" + str(build / "iris.dtb"),
            "--iris-timing-fixture=" + str(SIMULATOR / "calibration" / (profile + ".fixture"))]


def verify(manifest):
    path = Path(manifest).resolve()
    record = load(path)
    if record.get("schema") != "iris.empirical_simulator.v1" or record.get("package_kind") != KIND:
        raise ValueError("Vendored development descriptor required")
    release = load(SIMULATOR / "release.json")
    profile = record.get("profile")
    if profile not in ("source_compute", "source_os"):
        raise ValueError("Explicit compute or OS profile required")
    provider = Path(__file__).resolve()
    if record.get("model_provider") != str(provider):
        raise ValueError("Provider must be this checkout's native model provider")
    inputs = record["input_sha256"]
    checked(inputs)
    if inputs.get(str(provider)) != sha(provider):
        raise ValueError("Provider missing from build closure")
    receipt_path = Path(record["build_receipt"])
    if inputs.get(str(receipt_path)) != sha(receipt_path):
        raise ValueError("Build receipt missing from execution closure")
    receipt = load(receipt_path)
    build = receipt_path.parent
    if receipt.get("status") != "built" or receipt.get("schema") != "iris.vendored_native_build.v1":
        raise ValueError("A successful native build receipt is required")
    for name, digest in receipt["input_sha256"].items():
        if inputs.get(name) != digest:
            raise ValueError("Execution closure omits a build input: " + name)
    for key, filename in (("native_binary", "spike"), ("binary", "spike-launch")):
        actual = build / filename
        if record.get(key) != str(actual) or record.get(key + "_sha256") != inputs.get(str(actual)):
            raise ValueError("Built executable identity mismatch: " + key)
    for filename in ("spike", "spike-launch", "libsifive_uart.so", "bootrom.img", "iris.dtb"):
        if inputs.get(str(build / filename)) != receipt["output_sha256"].get(filename):
            raise ValueError("Build output identity mismatch: " + filename)
    fixture = SIMULATOR / "calibration" / (profile + ".fixture")
    if inputs.get(str(fixture)) != release["profiles"][profile]["fixture_sha256"]:
        raise ValueError("Frozen calibration fixture identity differs")
    if any(os.environ.get(key) for key in ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH")):
        raise ValueError("Loader overrides refused")
    return dict(available=True, binary=record["binary"], binary_sha256=record["binary_sha256"],
                native_binary=record["native_binary"], native_binary_sha256=record["native_binary_sha256"],
                native_device_abi=4, automatic_fatal_handler_resolution=True,
                isa_extensions=["zvt32t", "zvti8i32mm", "zvtofp8fmm"],
                per_hart_isa=release["profiles"][profile]["per_hart_isa"], matrix_hart_ids=[0, 1],
                memory_regions=MEMORY, launch_args=launch_args(build, profile),
                execution_input_sha256={**inputs, str(path): sha(path)},
                timing_available=True, timing_status="vendored_development_build",
                timing_calibrated=False, accuracy_2percent_certified=False,
                whole_model_certified=False, rtl_certified=False, hart2_timing_accuracy_certified=False,
                provenance=dict(build_receipt=str(receipt_path), build_receipt_sha256=sha(receipt_path),
                                profile=profile, source_changes=receipt["source_changes"],
                                historical_frozen_binary_validation_transferred=False))


def experimental_empirical_simulator(manifest):
    try:
        return verify(manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return dict(available=False, reason=str(error), timing_available=False,
                    accuracy_2percent_certified=False, whole_model_certified=False)
