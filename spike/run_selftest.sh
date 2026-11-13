#!/usr/bin/env bash
set -euo pipefail
spike_dir=$(cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$spike_dir/selftest.py" --kind guests "$@"
