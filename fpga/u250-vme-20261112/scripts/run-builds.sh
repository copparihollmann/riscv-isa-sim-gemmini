#!/bin/bash
set -Eeo pipefail
umask 077
ROOT=/scratch/copparihollmann/u250-vme-20261112
export BUILD_COORDINATOR_PID=$$
exec 8>"$ROOT/build.lock"
flock -n 8 || exit 0
phase=awaiting-setup
trap 'code=$?; if [[ "$code" != 0 ]]; then python3 "$ROOT/scripts/status.py" "$phase" failed "$code"; fi' EXIT
until /usr/bin/python3 - "$ROOT/setup-complete.json" <<'PY'
from pathlib import Path
import json,sys
p=Path(sys.argv[1])
if not p.exists():raise SystemExit(1)
d=json.loads(p.read_text())
if d["status"]=="failed":raise SystemExit(2)
raise SystemExit(0 if d["phase"]=="setup" and d["status"]=="ready" else 1)
PY
do
 code=$?
 if [[ "$code" == 2 ]]; then exit 2; fi
 sleep 20
done
source "$ROOT/scripts/build-environment.sh"
phase=manager-init
python3 "$ROOT/scripts/status.py" "$phase" running
firesim managerinit --platform xilinx_alveo_u250 >"$ROOT/private-logs/managerinit.log" 2>&1
phase=configure-pinned-inputs
python3 "$ROOT/scripts/status.py" "$phase" running
python3 "$ROOT/scripts/configure-build.py" >"$ROOT/private-logs/configure-build.log" 2>&1
cd "$CY_DIR/sims/firesim/deploy"
phase=elaborating-detailed-dram
python3 "$ROOT/scripts/status.py" "$phase" running
make -C ../sim compile \
 PLATFORM=xilinx_alveo_u250 TARGET_PROJECT=firesim \
 TARGET_PROJECT_MAKEFRAG="$CY_DIR/generators/firechip/chip/src/main/makefrag/firesim" \
 DESIGN=FireSim TARGET_CONFIG=FireSimVMEV256D128DualShuttleConfig \
 PLATFORM_CONFIG=FRFCFS16GBQuadRank_BaseXilinxAlveoU250Config \
 >"$ROOT/private-logs/u250-vme-elaboration.log" 2>&1
phase=validating-elaboration
python3 "$ROOT/scripts/status.py" "$phase" running
python3 "$ROOT/scripts/validate-elaboration.py" >"$ROOT/private-logs/elaboration-validation.log" 2>&1
for mhz in 15 25; do
 phase="build-$mhz-mhz"
 python3 "$ROOT/scripts/status.py" "$phase" running
 firesim buildbitstream \
  -b "config_build_vme_u250_"$mhz"mhz.yaml" \
  -r config_build_recipes_vme_u250.yaml \
  >"$ROOT/private-logs/u250-vme-$mhz-mhz-build.log" 2>&1
 phase="archive-$mhz-mhz"
 python3 "$ROOT/scripts/status.py" "$phase" running
 python3 "$ROOT/scripts/archive-result.py" "$mhz" >"$ROOT/private-logs/archive-$mhz-mhz.log" 2>&1
done
python3 "$ROOT/scripts/status.py" all-builds complete
