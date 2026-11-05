"""Bounded native source-service checks, without simulator or hardware jobs."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
SOURCE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "g++"))
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    if build == ROOT or ROOT in build.parents:
        parser.error("build directory must be outside source checkout")
    build.mkdir(parents=True, exist_ok=True)
    flags = ["-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    includes = ["-I" + str(path) for path in (SOURCE, ROOT / "timing/core/include", ROOT)]
    # Every C++ file here is a standalone native test. Discover all of them so
    # newly added regression checks cannot be omitted from a stale name list.
    tests = sorted((SOURCE / "tests").glob("*.cpp"))
    if not tests:
        parser.error("no source-service tests found")
    for source in tests:
        binary = build / source.stem
        print("CHECK " + source.stem, flush=True)
        subprocess.run(
            [args.cxx, *flags, *includes, str(source), "-o", str(binary)],
            check=True,
            timeout=60,
        )
        command = [str(binary)]
        if source.stem == "loader_bootstrap_test":
            command.append(str(build / "loader-bootstrap-fixture.elf"))
        subprocess.run(command, check=True, timeout=10)
    subprocess.run(
        [sys.executable, "-B", str(SOURCE / "tests/test_export.py")],
        check=True,
        timeout=20,
    )
    print(f"PASS {len(tests)} native checks and source-export tests", flush=True)


if __name__ == "__main__":
    main()
