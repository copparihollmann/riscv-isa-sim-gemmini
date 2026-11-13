# Compiler int8 wrapping corpus

This corpus compiles the actual `integration/iris-mlir` kernel emitter twice:
once for VME and once with its scalar-twin switch. A combined ELF contains both
implementations and runs seven cases, three repetitions and all three harts
through one managed FPGA lifecycle. Harts 0/1 execute concurrent kernels; hart 2
executes ordinary RVV producer arithmetic and participates in every barrier.

Cases cover positive/negative bias overflow, an int8 dot product that wraps its
matrix accumulator, four tiles, clamped tails, zero reduction and a short
reduction. Python arbitrary-precision integers independently calculate every
output before reduction modulo 2^32. The guest checks all 64,152 output words;
the host separately checks every one of 126 region checksums. Before each call,
every output is poisoned with its independent golden XOR 0xffffffff through
volatile stores outside the region. A real deliberately disabled-kernel ELF
must report all 63,984 compute words wrong while hart 2 still passes.
The C scalar twin
uses unsigned accumulation and a portable signed conversion. These functional
checks do not certify Zephyr, all supported instructions or cycle predictions.

From the repository root:

```sh
build/merlin-venv/bin/python benchmarks/compiler_i8_wrap/build.py --output build/compiler-i8-wrap-new
python3 benchmarks/compiler_i8_wrap/qualify.py --build build/compiler-i8-wrap-new \
  --variant combined --seed 0 --output build/compiler-i8-wrap-new-seed0
python3 benchmarks/compiler_i8_wrap/qualify.py --build build/compiler-i8-wrap-new \
  --variant combined --seed 17 --output build/compiler-i8-wrap-new-seed17
build/merlin-venv/bin/python benchmarks/compiler_i8_wrap/build.py \
  --deliberate-noop-negative-control --output build/compiler-i8-wrap-new-noop
# This deliberately disabled kernel must exit 1 with complete numerical failures.
python3 benchmarks/compiler_i8_wrap/qualify.py --build build/compiler-i8-wrap-new-noop \
  --variant combined --seed 0 --output build/compiler-i8-wrap-new-noop-seed0
python3 benchmarks/compiler_i8_wrap/acceptance.py --build build/compiler-i8-wrap-new \
  --gate build/compiler-i8-wrap-new-seed0 --gate build/compiler-i8-wrap-new-seed17 \
  --noop-build build/compiler-i8-wrap-new-noop --noop-gate build/compiler-i8-wrap-new-noop-seed0 \
  --output build/compiler-i8-wrap-new-admission
```

`firesim/prepare_i8_wrap.py` freezes the exact build, both actual functional
gates, 19 corrupted-transcript refusals, independent goldens, toolchain, source
pins, environment and capture checklist. Preparation is hardware-free. Launch
requires current standing authorization, complete idle inspection and the
shared lock; follow `firesim/OPERATING_RULES.md`. Its generated `launch.sh`
uses `run_prepared.py` for kill, infrasetup, runworkload and owned final kill,
then capture outside the job on either outcome. Never invoke the driver directly.

After cleanup and successful external capture:

```sh
python3 firesim/analyze_i8_wrap.py runs/your-fresh-managed-job \
  --output build/your-fresh-archive-analysis
```

The analyzer verifies the archive inventory, frozen validator/corpus, actual ELF,
all per-word guest verdicts, independent checksums, repetitions and four-phase
outcome. It preserves raw FPGA mcycle/minstret values. This corpus has its own
functional split and is not admitted as fitting or held-out timing evidence.
All calibration and whole-model certification flags remain false.
