#!/usr/bin/env python3
"""Build the pinned stock functional model without a compiler checkout or network."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import time
from pathlib import Path, PurePosixPath


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def verify_package(root: Path) -> dict:
    manifest = json.loads((root / "sources.json").read_text())
    if manifest["schema"] != "merlin.functional_spike_sources.v1":
        raise ValueError("unexpected functional source manifest")
    for name, expected in manifest["package_files"].items():
        if Path(name).name != name or sha(root / name) != expected:
            raise ValueError("packaging file hash changed: " + name)
    for entry in manifest["sources"].values():
        archive = root / entry["archive"]
        if (
            Path(entry["archive"]).name != entry["archive"]
            or sha(archive) != entry["sha256"]
            or archive.stat().st_size != entry["bytes"]
        ):
            raise ValueError("pinned source archive changed")
    return manifest


def unpack(archive: Path, destination: Path) -> None:
    destination.mkdir()
    with tarfile.open(archive, "r:") as source:
        names = set()
        for member in source:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.name in names
                or not member.name
            ):
                raise ValueError("invalid pinned source archive path")
            names.add(member.name)
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isreg():
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as content, target.open("xb") as output:
                    shutil.copyfileobj(content, output, 1024 * 1024)
                target.chmod(member.mode & 0o777)
            elif member.issym():
                # The public Spike archive has one relative internal source link.
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or not (
                    target.parent / member.linkname
                ).resolve().is_relative_to(destination.resolve()):
                    raise ValueError("source link escapes export")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname)
            else:
                raise ValueError("unsupported source archive member")


def verify_abi(source: Path, profile: dict) -> None:
    text = (source / "gemmini_params.h").read_text()

    def integer(name):
        match = re.search(r"^#define\s+" + name + r"\s+(\d+)\s*$", text, re.MULTILINE)
        if not match:
            raise ValueError("missing literal software ABI parameter: " + name)
        return int(match.group(1))

    actual = {
        key: integer(name)
        for key, name in {
            "dim": "DIM",
            "address_bits": "ADDR_LEN",
            "scratchpad_banks": "BANK_NUM",
            "scratchpad_rows_per_bank": "BANK_ROWS",
            "accumulator_rows": "ACC_ROWS",
            "maximum_software_transfer_bytes": "MAX_BYTES",
        }.items()
    }
    actual["scratchpad_rows"] = (
        actual["scratchpad_banks"] * actual["scratchpad_rows_per_bank"]
    )
    for alias, key in (("elem_t", "element_bytes"), ("acc_t", "accumulator_bytes")):
        match = re.search(r"typedef\s+int(\d+)_t\s+" + alias + r"\s*;", text)
        if not match:
            raise ValueError("unknown signed element representation")
        actual[key] = int(match.group(1)) // 8
    actual["full_width_accumulator_readout"] = bool(
        re.search(r"^#define ACC_READ_FULL_WIDTH\s*$", text, re.MULTILINE)
    )
    actual["first_layer_optimizations"] = bool(
        re.search(r"^#define HAS_FIRST_LAYER_OPTIMIZATIONS\s*$", text, re.MULTILINE)
    )
    opcode = {0: 0x0B, 1: 0x2B, 2: 0x5B, 3: 0x7B}[integer("XCUSTOM_ACC")]
    actual.update(custom_opcode=opcode, custom_opcode_mask=0x7F)
    if actual != profile["software_abi"]:
        raise ValueError("profile differs from pinned public software ABI")


def verify_sources(sources: Path, manifest: dict, *, built: bool = False) -> None:
    for name, entry in manifest["sources"].items():
        directory = sources / name
        expected = entry["source_roster"]
        observed = {}
        for parent, directories, filenames in os.walk(directory, followlinks=False):
            for item in [*directories, *filenames]:
                path = Path(parent) / item
                relative = path.relative_to(directory).as_posix()
                if path.is_symlink():
                    observed[relative] = {
                        "kind": "symlink",
                        "target": os.readlink(path),
                    }
                elif path.is_file():
                    if built and name == "libgemmini" and relative == "libgemmini.so":
                        continue
                    observed[relative] = {
                        "kind": "file",
                        "bytes": path.stat().st_size,
                        "sha256": sha(path),
                    }
                elif not path.is_dir():
                    raise ValueError("unsupported extracted source object")
        if observed != expected:
            raise ValueError(
                "full extracted source roster differs from pinned public Git objects: "
                + name
            )
        for filename, expected in entry["critical_files"].items():
            if sha(sources / name / filename) != expected:
                raise ValueError(
                    "functional ABI source changed during build: " + filename
                )


def build(
    package: Path, work: Path, jobs: int,
    *, boost_root: Path | None = None, boost_libdir: Path | None = None,
) -> dict:
    manifest = verify_package(package)
    profile = json.loads((package / "profile.json").read_text())
    if profile.get("target_profile", "stock_u250") != manifest.get("target_profile", "stock_u250"):
        raise ValueError("functional profile differs from the selected source package")
    if not 1 <= jobs <= 2:
        raise ValueError("choose one or two build jobs")
    # A fresh build directory avoids foreign configured source roots or libraries.
    work.mkdir(parents=True, exist_ok=False)
    sources, prefix, objects, temporary = (
        work / name for name in ("sources", "install", "build-spike", ".tmp")
    )
    for path in (sources, prefix, objects, temporary):
        path.mkdir()
    for name, entry in manifest["sources"].items():
        unpack(package / entry["archive"], sources / name)
    verify_sources(sources, manifest)
    verify_abi(sources / "libgemmini", profile)
    if (boost_root is None) != (boost_libdir is None):
        raise ValueError("select both Boost root and library directory")
    if boost_root is not None:
        boost_root, boost_libdir = boost_root.resolve(strict=True), boost_libdir.resolve(strict=True)
        if not (boost_root / "include/boost/version.hpp").is_file() or not boost_libdir.is_dir():
            raise ValueError("selected Boost headers or libraries are absent")
    env = dict(
        os.environ,
        TMPDIR=str(temporary),
        CC="gcc",
        CXX="g++",
        CFLAGS="-O2 -g0",
        CXXFLAGS="-O2 -g0",
        LDFLAGS=("-L" + str(boost_libdir)) if boost_libdir is not None else "",
    )
    if boost_root is not None:
        env["CPPFLAGS"] = "-I" + str(boost_root / "include")
        env["BOOST_ROOT"] = str(boost_root)
        env["LD_LIBRARY_PATH"] = str(boost_libdir) + ":" + env.get("LD_LIBRARY_PATH", "")
    configure = [str(sources / "spike/configure"), "--prefix=" + str(prefix)]
    if boost_root is not None:
        configure += ["--with-boost=" + str(boost_root), "--with-boost-libdir=" + str(boost_libdir)]
    commands = [
        (configure, objects),
        (
            ["make", "-j" + str(jobs), "spike", "install-hdrs", "install-config-hdrs"],
            objects,
        ),
        (["make", "-j" + str(jobs), "RISCV=" + str(prefix)], sources / "libgemmini"),
    ]
    started = time.monotonic()
    for argv, cwd in commands:
        subprocess.run(argv, cwd=cwd, env=env, check=True)
    (prefix / "bin").mkdir(exist_ok=True)
    (prefix / "lib").mkdir(exist_ok=True)
    shutil.copy2(objects / "spike", prefix / "bin/spike")
    shutil.copy2(sources / "libgemmini/libgemmini.so", prefix / "lib/libgemmini.so")
    runtime_members = ["bin/spike", "lib/libgemmini.so"]
    regex_library_name = None
    if boost_libdir is not None:
        regex_libraries = [
            path for path in boost_libdir.glob("libboost_regex.so.*")
            if path.is_file() and not path.is_symlink()
        ]
        if len(regex_libraries) != 1:
            raise ValueError("expected one selected Boost regex runtime library")
        regex_library = regex_libraries[0]
        regex_library_name = regex_library.name
        shutil.copy2(regex_library, prefix / "lib" / regex_library.name)
        runtime_members.append("lib/" + regex_library.name)
    verify_sources(sources, manifest, built=True)
    verify_package(package)
    receipt = {
        "schema": "merlin.functional_spike_deployment.v1",
        "status": "built_not_executed",
        "functional_qualification": "not_established",
        "timing_qualification": "not_applicable",
        "timing_model_included": False,
        "profile": profile,
        "sources": manifest,
        "package_manifest_sha256": sha(package / "sources.json"),
        "elapsed_build_seconds": time.monotonic() - started,
        "build_host": {"system": platform.system(), "machine": platform.machine()},
        "commands": [{"argv": argv, "cwd": str(cwd)} for argv, cwd in commands],
        "compiler": subprocess.check_output(
            ["g++", "--version"], text=True
        ).splitlines()[0],
        "build_flags": {
            key: env[key] for key in ("CC", "CXX", "CFLAGS", "CXXFLAGS", "LDFLAGS")
        },
        "boost_dependency": (
            {"root": str(boost_root), "libdir": str(boost_libdir),
             "runtime_library_name": regex_library_name,
             "version_header_sha256": sha(boost_root / "include/boost/version.hpp")}
            if boost_root is not None else None
        ),
        "artifacts": {
            name: {
                "sha256": sha(prefix / name),
                "bytes": (prefix / name).stat().st_size,
            }
            for name in runtime_members
        },
    }
    (prefix / "deployment.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    prepare_runtime(prefix, work / "runtime", receipt)
    return receipt


def prepare_runtime(prefix: Path, runtime: Path, receipt: dict) -> None:
    """Copy only the small runtime endpoints, never source or include roots."""
    allowed = {"bin/spike", "lib/libgemmini.so"}
    boost = receipt.get("boost_dependency")
    if boost:
        name = boost.get("runtime_library_name", "")
        if not name.startswith("libboost_regex.so.") or "/" in name:
            raise ValueError("selected Boost runtime library has an invalid name")
        allowed.add("lib/" + name)
    if set(receipt["artifacts"]) != allowed:
        raise ValueError(
            "runtime requires exactly the baseline executable and functional library"
        )
    runtime.mkdir(exist_ok=False)
    for filename, expected in receipt["artifacts"].items():
        if (
            filename not in allowed
            or sha(prefix / filename) != expected["sha256"]
        ):
            raise ValueError("runtime endpoint differs from its exact build receipt")
        output = runtime / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prefix / filename, output)
    (runtime / "deployment.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--boost-root", type=Path, help="explicit staged Boost installation root")
    parser.add_argument("--boost-libdir", type=Path, help="explicit staged Boost library directory")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if args.verify_only:
        verify_package(package)
        print("Pinned functional source package verified; no model executed.")
    elif args.work_dir is None:
        parser.error("--work-dir is required for a fresh build")
    else:
        build(
            package, args.work_dir.absolute(), args.jobs,
            boost_root=args.boost_root, boost_libdir=args.boost_libdir,
        )


if __name__ == "__main__":
    main()
