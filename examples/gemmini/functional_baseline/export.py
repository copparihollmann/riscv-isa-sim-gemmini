#!/usr/bin/env python3
"""Export exact public Git objects, never local working-tree changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

SPIKE_PIN = (
    "9c190a07c6838f6392bafa4ad83acea462c7f759",
    "https://github.com/riscv-software-src/riscv-isa-sim.git",
)
RECEIVER_PINS = {
    "stock_u250": (
        "ea8f7ed7afd68e001fb06ddccad9a023c990961d",
        "https://github.com/ucb-bar/libgemmini.git",
    ),
    "fire_aligned_30mhz": (
        "5b1254a7dc72f757442280e7f28ef30542c78533",
        "https://github.com/ucb-bar/libgemmini.git",
    ),
}
CRITICAL = {
    "spike": {
        "riscv/rocc.h": "08bdaf6f3f6e846125c937f4c19d54ab11efaf3026ffab55aad609e2c6a52eea"
    },
    "stock_u250": {
        "gemmini_params.h": "3758ae967af3a179497660970201093a7fb624be00173990ce33d3f5c38da924",
        "gemmini.cc": "209c0f4f4bc7c2313655ea36f3742a5eb590988b8ef7958cd74b9f80b5e7fc9f",
        "gemmini.h": "e13cde296d0faa650fe558351021628f3e4461525fa85b86bf81d44e66625590",
    },
    "fire_aligned_30mhz": {
        "gemmini_params.h": "3758ae967af3a179497660970201093a7fb624be00173990ce33d3f5c38da924",
        "gemmini.cc": "c468a86deb68cb2e12e3fb1177821075b0eb87e27a37ff835280ee7caf61b13a",
        "gemmini.h": "506d6857dd0a02a2921535e1a5725639c0b6374e83a95935426fc9b5c6349ac3",
    },
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def export(spike: Path, library: Path, output: Path, profile: str = "stock_u250") -> None:
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": "merlin.functional_spike_sources.v1",
        "target_profile": profile,
        "sources": {},
        "package_files": {},
    }
    for name, repo in (("spike", spike), ("libgemmini", library)):
        revision, url = SPIKE_PIN if name == "spike" else RECEIVER_PINS[profile]
        critical = CRITICAL["spike" if name == "spike" else profile]
        for filename, expected in critical.items():
            raw = subprocess.check_output(
                ["git", "-C", str(repo), "show", revision + ":" + filename]
            )
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError(
                    "pinned public ABI file differs: " + name + "/" + filename
                )
        archive = output / (name + ".tar")
        with archive.open("xb") as stream:
            subprocess.run(
                ["git", "-C", str(repo), "archive", "--format=tar", revision],
                stdout=stream,
                check=True,
            )
        with tarfile.open(archive, "r:") as source:
            members, roster = [], {}
            for member in source:
                members.append(member.name)
                if member.isreg():
                    raw = source.extractfile(member).read()
                    roster[member.name] = {
                        "kind": "file",
                        "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                elif member.issym():
                    roster[member.name] = {"kind": "symlink", "target": member.linkname}
                elif not member.isdir():
                    raise ValueError("unexpected pinned Git archive member")
        if any(
            item.startswith(("timing/", "functional_baseline/"))
            or "annotated_timing" in item
            for item in members
        ):
            raise ValueError(
                "functional source export contains instrumentation or packaging code"
            )
        manifest["sources"][name] = {
            "revision": revision,
            "repository": url,
            "archive": archive.name,
            "sha256": sha(archive),
            "bytes": archive.stat().st_size,
            "critical_files": critical,
            "source_roster": roster,
        }
    for filename in ("build.py", "README.md"):
        shutil.copyfile(Path(__file__).parent / filename, output / filename)
        manifest["package_files"][filename] = sha(output / filename)
    source_profile = Path(__file__).parent / ("profile.json" if profile == "stock_u250" else "profile_fire_aligned_30mhz.json")
    shutil.copyfile(source_profile, output / "profile.json")
    manifest["package_files"]["profile.json"] = sha(output / "profile.json")
    (output / "sources.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spike-repo", type=Path, required=True)
    parser.add_argument("--libgemmini-repo", type=Path, required=True)
    parser.add_argument("--profile", choices=tuple(RECEIVER_PINS), default="stock_u250")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.spike_repo, args.libgemmini_repo, args.output, args.profile)


if __name__ == "__main__":
    main()
