#!/usr/bin/env python3
"""Check the actual pinned/repaired headers and refuse changed source custody."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

SPEC = importlib.util.spec_from_file_location("rne_repair", Path(__file__).parents[1] / "rne_repair.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--spike-prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepared = args.prepared.resolve(strict=True)
    receipt = json.loads((prepared / "source-repair.json").read_text())
    with tarfile.open(prepared / "upstream-libgemmini.tar") as archive:
        original = archive.extractfile("gemmini_params.h").read()
    changed = (prepared / "sources/libgemmini/gemmini_params.h").read_bytes()
    assert changed == R.corrected_header(original)
    for bad in (original + b"\n", changed):
        try:
            R.corrected_header(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("different original header accepted")
    commands = []
    with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as temporary:
        root = Path(temporary)
        upstream = root / "upstream"
        upstream.mkdir()
        (upstream / "gemmini_params.h").write_bytes(original)
        for name, include, flags in (
            ("upstream", upstream, ["-DREPRODUCE_UPSTREAM_BUG"]),
            ("corrected", prepared / "sources/libgemmini", []),
        ):
            binary = root / (name + "-check")
            argv = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", *flags,
                    "-I" + str(include), str(Path(__file__).with_name("rne_scale_test.cpp")), "-o", str(binary)]
            subprocess.run(argv, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True)
            commands.append({"argv": argv, "result": "pass"})
        for forge_manifest in (False, True):
            clone = root / ("manifest-mutated" if forge_manifest else "source-mutated")
            shutil.copytree(prepared, clone, ignore=shutil.ignore_patterns("runtime", "temporary", "extension.d"))
            source = clone / "sources/libgemmini/gemmini.h"
            source.write_bytes(source.read_bytes() + b"\n// changed source\n")
            if forge_manifest:
                metadata = json.loads((clone / "source-repair.json").read_text())
                row = metadata["adapted_manifest"]["sources"]["libgemmini"]["source_roster"]["gemmini.h"]
                row.update(bytes=source.stat().st_size, sha256=hashlib.sha256(source.read_bytes()).hexdigest())
                R.write(clone / "source-repair.json", metadata)
            try:
                R.build(clone, args.spike_prefix)
            except ValueError:
                assert not (clone / "runtime").exists()
            else:
                raise AssertionError("modified prepared source/manifest accepted")
    R.B.verify_sources(prepared / "sources", receipt["adapted_manifest"])
    R.write(args.output, {
        "schema": "merlin.functional_rne_repair_checks.v1", "status": "pass",
        "prepared_source": R.pin(prepared / "source-repair.json"),
        "test_source": R.pin(Path(__file__).with_name("rne_scale_test.cpp")),
        "commands": commands,
        "checks": ["actual upstream positive/negative error reproduced", "actual corrected finite RNE/ties/clipping and MVIN grid", "wrong preimage refused", "changed source refused before build", "forged adapted manifest refused before build"],
        "simulations": 0, "physical_measurements": 0,
    })


if __name__ == "__main__":
    main()
