#!/usr/bin/env python3
"""Bounded standalone source build; no compiler project or model data required."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = (
    "riscv",
    "fesvr",
    "softfloat",
    "disasm",
    "fdt",
    "spike_main",
    "customext",
    "debug_rom",
    "timing",
)
SOURCE_FILES = (
    "configure",
    "configure.ac",
    "Makefile.in",
    "config.h.in",
    "aclocal.m4",
    "VERSION",
)


def source_identity():
    paths = [ROOT / name for name in SOURCE_FILES]
    for name in SOURCE_DIRS:
        paths.extend(
            p
            for p in (ROOT / name).rglob("*")
            if p.is_file()
            and p.suffix in {".h", ".hpp", ".cc", ".c", ".S", ".in", ".py", ".json"}
            and "__pycache__" not in p.parts
            and p.name != "timing_build_identity.h"
        )
    if len(paths) > 20000:
        raise ValueError("source member budget exceeded")
    members = []
    total_bytes = 0
    for path in sorted(set(paths)):
        if path.is_symlink():
            raise ValueError("source members must be ordinary files")
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("source member exceeds 16 MiB")
        data = path.read_bytes()
        total_bytes += len(data)
        if total_bytes > 64 * 1024 * 1024:
            raise ValueError("complete source roster exceeds 64 MiB")
        members.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    encoded = json.dumps(members, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": "merlin.annotated_spike_sources.v1",
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "members": members,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build-dir", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--identity-only", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.jobs <= 2:
        ap.error(
            "this builder supports one or two jobs; use the site scheduler for larger builds"
        )
    requested = args.build_dir.absolute()
    build = requested.resolve()
    if requested != build:
        ap.error("build directory and its parents must not be symlinks")
    if build == ROOT or ROOT in build.parents:
        ap.error("build directory must be outside the source tree")
    build.mkdir(parents=True, exist_ok=True)
    with (build / ".annotated-build.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            ap.error("another annotated build owns this build directory")
        build_locked(args, ap, build)


def build_locked(args, ap, build):
    makefile = build / "Makefile"
    if makefile.exists():
        configured = re.search(
            r"^src_dir\s*:?=\s*(.*?)\s*$", makefile.read_text(), re.MULTILINE
        )
        configured_root = Path(configured.group(1)) if configured else None
        if configured_root is not None and not configured_root.is_absolute():
            configured_root = build / configured_root
        if configured_root is None or configured_root.resolve() != ROOT:
            ap.error("existing build directory belongs to a different source checkout")
    identity = source_identity()
    manifest = build / "timing-source-manifest.json"
    manifest.write_text(json.dumps(identity, sort_keys=True, indent=2) + "\n")
    header = '#define SPIKE_TIMING_SOURCE_SHA256 "' + identity["sha256"] + '"\n'
    hp = build / "timing_build_identity.h"
    if not hp.exists() or hp.read_text() != header:
        hp.write_text(header)
    if args.identity_only:
        print(identity["sha256"])
        return
    env = os.environ.copy()
    env.setdefault("TMPDIR", str(build / ".tmp"))
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    if not (build / "Makefile").exists():
        subprocess.run(
            [
                str(ROOT / "configure"),
                "--prefix=" + str(build / "install"),
                "CXXFLAGS=-O2 -g0",
            ],
            cwd=build,
            env=env,
            check=True,
        )
    subprocess.run(
        ["make", "-j" + str(args.jobs), "spike"], cwd=build, env=env, check=True
    )
    if source_identity() != identity:
        # Leave no executable advertising an identity collected before edits.
        executable = build / "spike"
        if executable.exists():
            executable.replace(build / "spike.unqualified-source-change")
        raise RuntimeError("sources changed during build; repeat with stable sources")
    print(
        json.dumps(
            {"spike": str(build / "spike"), "feature_engine_sha256": identity["sha256"]}
        )
    )


if __name__ == "__main__":
    main()
