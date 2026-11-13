#!/bin/bash
ROOT=/scratch/copparihollmann/u250-vme-20261112
export CY_DIR="$ROOT/chipyard-vme-u250"
source "$ROOT/runtime/miniforge/etc/profile.d/conda.sh"
source "$CY_DIR/env.sh"
export RISCV="$CY_DIR/.conda-env/riscv-tools"
export PATH="$RISCV/bin:$PATH"
cd "$CY_DIR/sims/firesim"
source sourceme-manager.sh --skip-ssh-setup
export PATH="$ROOT/bin:$PATH"
export MAKEFLAGS=-j12
unset SBT_OPTS
export JAVA_TOOL_OPTIONS="-Xmx32G -Xss8M -XX:ActiveProcessorCount=12"
unset USE_CHISEL7
