#!/usr/bin/env bash
set -euo pipefail
board_dir=$(cd -- "$(dirname -- "$0")" && pwd)
model_root=$(dirname -- "$board_dir")
spike_src="$model_root/third_party/riscv-isa-sim"
spike_build="$model_root/spike/build"
mkdir -p "$board_dir/build"
"${DTC:-/scratch/eygao/iris-cy/.conda-env/bin/dtc}" -I dts -O dtb \
  -o "$board_dir/build/iris.dtb" "$board_dir/evidence/firesim-dts.dts" \
  2>"$board_dir/build/dtc.log"
"${CXX:-g++}" -std=c++20 -O2 -Wall -Wextra -Werror -fPIC -shared \
  -I"$spike_build" -I"$board_dir" -I"$model_root/spike/include" \
  -iquote "$spike_src/riscv" -iquote "$spike_src" \
  "$board_dir/plugin.cpp" -o "$board_dir/build/libiris_board_boot.so"
"${CXX:-g++}" -std=c++20 -O2 -Wall -Wextra -Werror -rdynamic \
  -I"$spike_build" -I"$board_dir" -iquote "$spike_src/riscv" \
  -iquote "$spike_src/fesvr" -iquote "$spike_src/softfloat" -iquote "$spike_src" \
  "$board_dir/tests/boot_test.cpp" -L"$spike_build" \
  -Wl,--start-group -lriscv -ldisasm -lsoftfloat -lfesvr -lfdt -Wl,--end-group \
  -ldl -lpthread -o "$board_dir/build/boot_test"
"$board_dir/build/boot_test" "$board_dir/evidence/bootrom.rv64.img" \
  "$board_dir/build/iris.dtb" "$board_dir/build/libiris_board_boot.so"
