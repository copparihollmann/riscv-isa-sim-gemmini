#!/bin/bash
set -e
unset LD_LIBRARY_PATH
source /ecad/tools/xilinx/Vivado/2021.1/settings64.sh >/dev/null 2>&1
exec taskset -c 12-23 /ecad/tools/xilinx/Vivado/2021.1/bin/vivado "$@"
