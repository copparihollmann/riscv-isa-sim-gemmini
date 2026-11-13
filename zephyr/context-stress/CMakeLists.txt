cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(iris_context_stress)
# Register-preservation tests call kernel APIs with intentionally live RVV
# registers; prevent ordinary C code from generating ABI-clobbering RVV work.
zephyr_compile_options(-fno-tree-vectorize -fno-tree-slp-vectorize)
target_sources(app PRIVATE src/main.c src/registers.S)
