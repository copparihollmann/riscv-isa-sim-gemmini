#!/bin/bash
set -Eeo pipefail
umask 077
ROOT=/scratch/copparihollmann/u250-vme-20261112
CY_DIR="$ROOT/chipyard-vme-u250"
export BUILD_COORDINATOR_PID=$$
exec 9>"$ROOT/setup.lock"
flock -n 9 || exit 0
phase=runtime-bootstrap
trap 'code=$?; python3 "$ROOT/scripts/status.py" "$phase" failed "$code"; exit "$code"' ERR
python3 "$ROOT/scripts/status.py" "$phase" running
export CONDA_PKGS_DIRS="$ROOT/runtime/conda-pkgs"
export PIP_CACHE_DIR="$ROOT/runtime/pip-cache"
export TMPDIR="$ROOT/runtime/tmp"
mkdir -p "$CONDA_PKGS_DIRS" "$PIP_CACHE_DIR" "$TMPDIR"
if [[ ! -x "$ROOT/runtime/miniforge/bin/conda" ]]; then
  python3 - "$ROOT" <<'PY'
from pathlib import Path
import urllib.request,hashlib,json,sys
root=Path(sys.argv[1]);url="https://github.com/conda-forge/miniforge/releases/download/26.9.4-2/Miniforge3-Linux-x86_64.sh"
expected="bbaf16b3897da24c4be50315934ba74848f617b4495982841d6a0a60e0edbbdf"
p=root/"runtime/Miniforge3-Linux-x86_64.sh"
if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
 with urllib.request.urlopen(url,timeout=90) as response,p.open("wb") as f:
  while True:
   b=response.read(1048576)
   if not b:break
   f.write(b)
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
(root/"provenance/miniforge-installer.json").write_text(json.dumps({"url":url,"sha256":expected},indent=2)+"\n")
PY
  bash "$ROOT/runtime/Miniforge3-Linux-x86_64.sh" -b -p "$ROOT/runtime/miniforge" >"$ROOT/private-logs/miniforge-install.log" 2>&1
fi
source "$ROOT/runtime/miniforge/etc/profile.d/conda.sh"
phase=locked-conda-environment
python3 "$ROOT/scripts/status.py" "$phase" running
if [[ ! -x "$CY_DIR/.conda-lock-env/bin/conda-lock" ]]; then
 conda create -y -p "$CY_DIR/.conda-lock-env" --override-channels -c conda-forge conda-lock >"$ROOT/private-logs/conda-lock-bootstrap.log" 2>&1
fi
if [[ ! -f "$ROOT/provenance/pinned-conda-environment.complete" ]]; then
 conda run --no-capture-output -p "$CY_DIR/.conda-lock-env" conda-lock install --conda "$CONDA_EXE" -p "$CY_DIR/.conda-env" "$CY_DIR/conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64.conda-lock.yml" >"$ROOT/private-logs/pinned-conda-install.log" 2>&1
 touch "$ROOT/provenance/pinned-conda-environment.complete"
fi
conda activate "$CY_DIR/.conda-env"
export RISCV="$CY_DIR/.conda-env/riscv-tools"
export MAKEFLAGS=-j12
unset SBT_OPTS
export JAVA_TOOL_OPTIONS="-Xmx32G -Xss8M -XX:ActiveProcessorCount=12"
export CMAKE_BUILD_PARALLEL_LEVEL=12
unset USE_CHISEL7
cd "$CY_DIR"
touch env.sh
source scripts/utils.sh
common_setup
replace_content env.sh build-setup-conda "source $ROOT/runtime/miniforge/etc/profile.d/conda.sh
conda activate $CY_DIR/.conda-env
source $CY_DIR/scripts/fix-open-files.sh"
phase=chipyard-setup
python3 "$ROOT/scripts/status.py" "$phase" running
phase=target-submodules
python3 "$ROOT/scripts/status.py" "$phase" running
./scripts/init-submodules-no-riscv-tools.sh --saturn >"$ROOT/private-logs/target-submodules.log" 2>&1
phase=chipyard-setup
python3 "$ROOT/scripts/status.py" "$phase" running
./build-setup.sh riscv-tools --skip-marshal --skip-conda --skip-submodules --skip-toolchain --skip-ctags >"$ROOT/private-logs/chipyard-setup.log" 2>&1
python3 "$ROOT/scripts/status.py" setup ready
