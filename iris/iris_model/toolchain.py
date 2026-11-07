"""Resolve an explicit or installed ELF symbol reader for profiling."""

import os
from pathlib import Path
import shutil


def nm_tool():
    name = os.environ.get("IRIS_NM")
    if name:
        result = shutil.which(name)
    else:
        result = next((p for p in (shutil.which("riscv64-unknown-elf-nm"),
                                   shutil.which("llvm-nm"), shutil.which("nm")) if p), None)
    if result is None or not Path(result).is_file():
        raise ValueError("Install an ELF-capable nm tool or set IRIS_NM")
    return Path(result).resolve()
