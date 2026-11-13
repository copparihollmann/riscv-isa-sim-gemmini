#!/usr/bin/env bash
set -euo pipefail
timing_dir=$(cd -- "$(dirname -- "$0")" && pwd)
model_root=$(dirname -- "$timing_dir")
mkdir -p "$model_root/build/shuttle-issue"
python3 "$timing_dir/generate_shuttle_issue.py" --verify-live
"${CXX:-g++}" -std=c++17 -O2 -Wall -Wextra -Werror \
  "$timing_dir/shuttle_issue.cpp" "$timing_dir/test_shuttle_issue.cpp" \
  -o "$model_root/build/shuttle-issue/test_shuttle_issue"
"$model_root/build/shuttle-issue/test_shuttle_issue"
