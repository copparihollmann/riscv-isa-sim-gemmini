#!/usr/bin/env python3
"""Prepare an explicitly selected RNE correction without editing upstream sources.

The pristine functional export and its default profiles are unchanged. This
separate operator path fixes the integer-successor expression in the pinned
public receiver, records the complete source delta, and builds a new identity.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import tarfile
from pathlib import Path


def _module(name: str):
    spec = importlib.util.spec_from_file_location(
        "functional_" + name, Path(__file__).with_name(name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B, E = _module("build"), _module("export")
BEFORE = b"const long long next = x_ < 0 ? x_ - 1 : x_ + 1;"
AFTER = b"const long long next = x_ < 0 ? i - 1 : i + 1;"


def pin(path: Path) -> dict:
    return {"path": str(path.resolve(strict=True)), "sha256": B.sha(path)}


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def corrected_header(raw: bytes) -> bytes:
    import hashlib

    expected = E.CRITICAL["fire_aligned_30mhz"]["gemmini_params.h"]
    if hashlib.sha256(raw).hexdigest() != expected or raw.count(BEFORE) != 1:
        raise ValueError("RNE repair requires the exact pinned upstream header")
    return raw.replace(BEFORE, AFTER, 1)


def _baseline(root: Path) -> dict:
    deployment = json.loads((root / "deployment.json").read_text())
    if deployment["schema"] != "merlin.functional_spike_deployment.v1":
        raise ValueError("expected the original pristine functional deployment")
    for name, item in deployment["artifacts"].items():
        path = root / name
        if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
            raise ValueError("baseline runtime member escapes its root")
        if B.sha(path) != item["sha256"]:
            raise ValueError("baseline functional runtime member changed: " + name)
    return deployment


def _source_manifest(deployment: dict) -> dict:
    profile = deployment["sources"]["target_profile"]
    source = deployment["sources"]["sources"]["libgemmini"]
    if (
        profile not in E.RECEIVER_PINS
        or source["revision"] != E.RECEIVER_PINS[profile][0]
        or source["critical_files"] != E.CRITICAL[profile]
    ):
        raise ValueError("baseline receiver does not match a pinned public profile")
    return {"sources": {"libgemmini": source}}


def _adapted_manifest(manifest: dict, archive: Path) -> dict:
    import hashlib

    upstream = manifest["sources"]["libgemmini"]
    if B.sha(archive) != upstream["sha256"] or archive.stat().st_size != upstream["bytes"]:
        raise ValueError("public receiver archive changed")
    with tarfile.open(archive, "r:") as stream:
        raw = stream.extractfile("gemmini_params.h").read()
    changed = corrected_header(raw)
    digest = hashlib.sha256(changed).hexdigest()
    adapted = copy.deepcopy(manifest)
    entry = adapted["sources"]["libgemmini"]
    entry["critical_files"]["gemmini_params.h"] = digest
    entry["source_roster"]["gemmini_params.h"].update(sha256=digest, bytes=len(changed))
    return adapted


def prepare(library_repo: Path, baseline: Path, output: Path) -> dict:
    baseline = baseline.resolve(strict=True)
    deployment = _baseline(baseline)
    manifest = _source_manifest(deployment)
    source = manifest["sources"]["libgemmini"]
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "upstream-libgemmini.tar"
    with archive.open("xb") as stream:
        subprocess.run(
            ["git", "-C", str(library_repo), "archive", "--format=tar", source["revision"]],
            stdout=stream,
            check=True,
        )
    if B.sha(archive) != source["sha256"] or archive.stat().st_size != source["bytes"]:
        raise ValueError("public receiver archive differs from original deployment")
    sources = output / "sources"
    sources.mkdir()
    B.unpack(archive, sources / "libgemmini")
    B.verify_sources(sources, manifest)
    header = sources / "libgemmini/gemmini_params.h"
    before_image = output / "upstream-gemmini_params.h"
    before_image.write_bytes(header.read_bytes())
    original = pin(before_image)
    header.write_bytes(corrected_header(header.read_bytes()))
    adapted = _adapted_manifest(manifest, archive)
    B.verify_sources(sources, adapted)
    tooling = output / "tooling"
    tooling.mkdir()
    for name in ("rne_repair.py", "build.py", "export.py"):
        shutil.copyfile(Path(__file__).with_name(name), tooling / name)
    receipt = {
        "schema": "merlin.functional_rne_source_repair.v1",
        "baseline": str(baseline),
        "baseline_deployment": pin(baseline / "deployment.json"),
        "upstream_archive": pin(archive),
        "upstream_manifest": manifest,
        "adapted_manifest": adapted,
        "repair_tool": pin(tooling / "rne_repair.py"),
        "repair_tools": {name: pin(tooling / name) for name in ("rne_repair.py", "build.py", "export.py")},
        "changed_files": [{"before": original, "after": pin(header)}],
        "semantic_change": "integer successor i+/-1, never rounded floating x+/-1",
        "unchanged": ["FP32 multiplication", "ties-to-even rule", "saturation", "activation order", "guest executable", "RTL"],
        "numeric_scope": "finite FP32 products whose truncated integer and adjacent successor are representable in signed64; upstream nonfinite/out-of-range conversion behavior is not qualified",
        "functional_qualification": "not_established",
        "timing_qualification": "not_established",
    }
    write(output / "source-repair.json", receipt)
    return receipt


def _headers(root: Path) -> dict:
    files = [p for p in root.rglob("*") if p.is_file()]
    if len(files) > 4096 or sum(p.stat().st_size for p in files) > 32 * 1024 * 1024:
        raise ValueError("selected Spike header closure exceeds the bounded build scope")
    return {p.relative_to(root).as_posix(): B.sha(p) for p in sorted(files)}


def build(prepared: Path, spike_prefix: Path, cxx: str = "g++") -> dict:
    prepared = prepared.resolve(strict=True)
    source_receipt = prepared / "source-repair.json"
    receipt = json.loads(source_receipt.read_text())
    baseline = Path(receipt["baseline"])
    deployment = _baseline(baseline)
    if pin(baseline / "deployment.json") != receipt["baseline_deployment"]:
        raise ValueError("original functional deployment identity changed")
    if _source_manifest(deployment) != receipt["upstream_manifest"]:
        raise ValueError("original public source selection changed")
    adapted = _adapted_manifest(receipt["upstream_manifest"], prepared / "upstream-libgemmini.tar")
    if adapted != receipt["adapted_manifest"]:
        raise ValueError("prepared repair or implementing source identity changed")
    for name, selected in receipt["repair_tools"].items():
        if pin(Path(selected["path"])) != selected or B.sha(Path(__file__).with_name(name)) != selected["sha256"]:
            raise ValueError("prepared repair implementation changed")
    B.verify_sources(prepared / "sources", adapted)
    spike_prefix = spike_prefix.resolve(strict=True)
    include = spike_prefix / "include"
    if B.sha(include / "riscv/rocc.h") != E.CRITICAL["spike"]["riscv/rocc.h"]:
        raise ValueError("selected Spike headers do not match the original public RoCC ABI")
    headers = _headers(include)
    runtime = prepared / "runtime"
    runtime.mkdir(exist_ok=False)
    for name in deployment["artifacts"]:
        target = runtime / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name != "lib/libgemmini.so":
            shutil.copyfile(baseline / name, target)
            target.chmod((baseline / name).stat().st_mode & 0o777)
    temporary = prepared / "temporary"
    temporary.mkdir()
    compiler = Path(shutil.which(cxx)).resolve(strict=True)
    library = runtime / "lib/libgemmini.so"
    dependency_file = prepared / "extension.d"
    argv = [str(compiler), "-L" + str(spike_prefix / "lib"),
            "-Wl,-rpath," + str(spike_prefix / "lib"), "-shared", "-o", str(library),
            "-std=c++17", "-I" + str(include), "-fPIC", "-O3", "-MMD", "-MF", str(dependency_file),
            str(prepared / "sources/libgemmini/gemmini.cc")]
    result = subprocess.run(argv, cwd=prepared, env=dict(os.environ, TMPDIR=str(temporary)),
                            capture_output=True, text=True, check=True)
    if _headers(include) != headers:
        raise ValueError("selected Spike headers changed during receiver build")
    B.verify_sources(prepared / "sources", adapted)
    _baseline(baseline)
    dependencies = shlex.split(dependency_file.read_text().replace("\\\n", " ").split(":", 1)[1])
    output = {
        "schema": "merlin.functional_spike_corrected_deployment.v1",
        "status": "built_not_executed",
        "source_repair": pin(source_receipt),
        "baseline_deployment": receipt["baseline_deployment"],
        "numeric_scope": receipt["numeric_scope"],
        "functional_qualification": "not_established", "timing_qualification": "not_established",
        "command": {"argv": argv, "cwd": str(prepared), "stdout": result.stdout, "stderr": result.stderr},
        "compiler": pin(compiler), "selected_spike_include": str(include),
        "selected_spike_headers": headers,
        "dependencies": [pin(Path(p)) for p in dependencies],
        "artifacts": {name: {"sha256": B.sha(runtime / name), "bytes": (runtime / name).stat().st_size}
                      for name in deployment["artifacts"]},
        "default_profile_changed": False,
    }
    write(runtime / "deployment.json", output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libgemmini-repo", type=Path, required=True)
    parser.add_argument("--baseline-runtime", type=Path, required=True)
    parser.add_argument("--spike-prefix", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.libgemmini_repo, args.baseline_runtime, args.output)
    if args.spike_prefix is not None:
        build(args.output, args.spike_prefix)


if __name__ == "__main__":
    main()
