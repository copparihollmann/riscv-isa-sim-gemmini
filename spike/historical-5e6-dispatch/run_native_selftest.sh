#!/usr/bin/env bash
set -euo pipefail
spike_dir=$(cd -- "$(dirname -- "$0")" && pwd)
spike_src="$spike_dir/../third_party/riscv-isa-sim"
spike_build="$spike_dir/build"
"${CXX:-g++}" -std=c++20 -O2 -iquote "$spike_src/riscv" "$spike_dir/native_fp8_math_test.cc" -o "$spike_build/native_fp8_math_test"
"$spike_build/native_fp8_math_test"
"${CXX:-g++}" -std=c++20 -O2 -iquote "$spike_src/riscv" -iquote "$spike_src/softfloat" "$spike_dir/wide_fp8_math_test.cc" "$spike_build/libsoftfloat.a" -o "$spike_build/wide_fp8_math_test"
"$spike_build/wide_fp8_math_test"
"${CXX:-g++}" -std=c++20 -O2 -rdynamic -I"$spike_build" -iquote "$spike_src/riscv" -iquote "$spike_src/fesvr" -iquote "$spike_src/softfloat" -iquote "$spike_src" "$spike_dir/native_fp8_handlers_test.cc" -L"$spike_build" -Wl,--start-group -lriscv -ldisasm -lsoftfloat -lfesvr -lfdt -Wl,--end-group -ldl -lpthread -o "$spike_build/native_fp8_handlers_test"
"$spike_build/native_fp8_handlers_test"

"${CXX:-g++}" -std=c++20 -O2 -iquote "$spike_src/riscv" -iquote "$spike_src/softfloat" "$spike_dir/ieee_fma_math_test.cc" "$spike_build/libsoftfloat.a" -o "$spike_build/ieee_fma_math_test"
"$spike_build/ieee_fma_math_test"
"${CXX:-g++}" -std=c++20 -O2 -rdynamic -I"$spike_build" -iquote "$spike_src/riscv" -iquote "$spike_src/fesvr" -iquote "$spike_src/softfloat" -iquote "$spike_src" "$spike_dir/ieee_fma_handlers_test.cc" -L"$spike_build" -Wl,--start-group -lriscv -ldisasm -lsoftfloat -lfesvr -lfdt -Wl,--end-group -ldl -lpthread -o "$spike_build/ieee_fma_handlers_test"
"$spike_build/ieee_fma_handlers_test"

"${CXX:-g++}" -std=c++20 -O2 -iquote "$spike_src/riscv" -iquote "$spike_src/softfloat" "$spike_dir/shared_fma_math_test.cc" "$spike_build/libsoftfloat.a" -o "$spike_build/shared_fma_math_test"
"$spike_build/shared_fma_math_test"
"${CXX:-g++}" -std=c++20 -O2 -rdynamic -I"$spike_build" -iquote "$spike_src/riscv" -iquote "$spike_src/fesvr" -iquote "$spike_src/softfloat" -iquote "$spike_src" "$spike_dir/shared_fma_handlers_test.cc" -L"$spike_build" -Wl,--start-group -lriscv -ldisasm -lsoftfloat -lfesvr -lfdt -Wl,--end-group -ldl -lpthread -o "$spike_build/shared_fma_handlers_test"
"$spike_build/shared_fma_handlers_test"

"${CXX:-g++}" -std=c++20 -O2 -rdynamic -I"$spike_build" -iquote "$spike_src/riscv" -iquote "$spike_src/fesvr" -iquote "$spike_src/softfloat" -iquote "$spike_src" "$spike_dir/fpcomp_handlers_test.cc" -L"$spike_build" -Wl,--start-group -lriscv -ldisasm -lsoftfloat -lfesvr -lfdt -Wl,--end-group -ldl -lpthread -o "$spike_build/fpcomp_handlers_test"
"$spike_build/fpcomp_handlers_test"
