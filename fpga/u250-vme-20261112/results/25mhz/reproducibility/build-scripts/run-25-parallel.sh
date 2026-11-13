#!/bin/bash
set -Eeo pipefail
umask 077
ROOT=/scratch/copparihollmann/u250-vme-20261112
export BUILD_COORDINATOR_PID=$$
exec 7>"$ROOT/parallel-25mhz.lock"
flock -n 7 || exit 0
phase=starting
trap 'code=$?; if [[ "$code" != 0 ]]; then /usr/bin/python3 "$ROOT/scripts/status-parallel.py" "$phase" failed "$code"; fi' EXIT
source "$ROOT/scripts/build-environment.sh"
export FS_DIR="$ROOT/parallel-25mhz/firesim"
cd "$FS_DIR/deploy"
phase=build-25-mhz
/usr/bin/python3 "$ROOT/scripts/status-parallel.py" "$phase" running
./firesim buildbitstream -b config_build_vme_u250_25mhz.yaml -r config_build_recipes_vme_u250.yaml >"$ROOT/private-logs/u250-vme-25-mhz-build.log" 2>&1
phase=archive-25-mhz
/usr/bin/python3 "$ROOT/scripts/status-parallel.py" "$phase" running
python3 "$ROOT/scripts/archive-result.py" 25 >"$ROOT/private-logs/archive-25-mhz.log" 2>&1
/usr/bin/python3 "$ROOT/scripts/status-parallel.py" complete complete
