"""Bounded source/export and standalone C++ checks; launches no simulator."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-include", type=Path, required=True)
    parser.add_argument("--spike-root", type=Path, required=True)
    parser.add_argument("--public-library", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    args.build_dir.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "TMPDIR": str(args.build_dir.absolute()), "PYTHONDONTWRITEBYTECODE": "1",
           "ASAN_OPTIONS": "detect_leaks=1:halt_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1"}
    flags = [args.cxx, "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
             "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
             "-I", str(root), "-I", str(args.engine_include), "-I", str(args.spike_root)]
    queried_prices = set()
    for name, sources in (("provider_test", [root / "tests/provider_test.cpp"]),
                          ("staged_test", [root / "tests/staged_test.cpp"]),
                          ("execute_service_test", [root / "tests/execute_service_test.cpp"]),
                          ("bridge_test", [root / "bridge.cpp", root / "tests/bridge_test.cpp"])):
        output = args.build_dir / name
        subprocess.run([*flags, *(str(source) for source in sources), "-o", str(output)],
                       check=True, timeout=90, env=env)
        executed = subprocess.run([str(output)], check=True, timeout=15, env=env, text=True, capture_output=True)
        for line in executed.stdout.splitlines():
            if line.startswith("price-query:"):
                queried_prices.add(line.removeprefix("price-query:"))
            else:
                print(line, flush=True)
        print(f"{name}: sanitizer checks passed", flush=True)
    spec = importlib.util.spec_from_file_location("target_export", root / "export_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed = module.export(args.public_library, args.spike_root / "riscv/rocc.h")
    assert observed == json.loads((root / "stock_u250.json").read_bytes())
    expected_prices = {f"target.prices.{kind}.{field}" for kind, fields in observed["target"]["prices"].items()
                       for field in fields}
    assert queried_prices == expected_prices, "exported price schema differs from actual bridge queries"
    assert all(value is None for resource in observed["resources"].values() for value in resource.values())
    assert all(value is None for price in observed["target"]["prices"].values() for value in price.values())
    altered = args.build_dir / "altered-public-source"
    altered.mkdir()
    for name in ("gemmini_params.h", "gemmini.h", "gemmini.cc"):
        shutil.copyfile(args.public_library / name, altered / name)
    header = altered / "gemmini_params.h"
    header.write_bytes(header.read_bytes() + b"\n// altered source\n")
    try:
        module.export(altered, args.spike_root / "riscv/rocc.h")
    except ValueError as error:
        assert "identity differs" in str(error)
    else:
        raise AssertionError("changed public parameter source was accepted")
    print("export: reproducible; changed pin refused; no invented prices/queues", flush=True)
    subprocess.run([sys.executable, str(root / "tests/test_bundle.py")], check=True, timeout=15, env=env)
    subprocess.run([sys.executable, str(root / "tests/test_execute_service_bundle.py")], check=True, timeout=15, env=env)


if __name__ == "__main__":
    main()
