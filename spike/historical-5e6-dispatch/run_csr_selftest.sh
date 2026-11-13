#!/usr/bin/env bash
set -euo pipefail
spike_dir=$(cd -- "$(dirname -- "$0")" && pwd)
spike_src="$spike_dir/../third_party/riscv-isa-sim"
spike_build="$spike_dir/build"
"${CXX:-g++}" -std=c++20 -O2 -rdynamic -I"$spike_build" -iquote "$spike_src/riscv" -iquote "$spike_src/fesvr" -iquote "$spike_src/softfloat" -iquote "$spike_src" "$spike_dir/csr_handlers_test.cc" -L"$spike_build" -Wl,--start-group -lriscv -ldisasm -lsoftfloat -lfesvr -lfdt -Wl,--end-group -ldl -lpthread -o "$spike_build/csr_handlers_test"
"$spike_build/csr_handlers_test"
