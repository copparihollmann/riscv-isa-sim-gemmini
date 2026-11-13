# Scalar BF16 decoder observations

The source advertises `zfbfmin` in the compute-hart ISA string, but both scalar
BF16 conversion families are disjoint from every pinned scalar decode pattern.
This batch checks that finding on all three actual harts. It does not confuse
scalar BF16 with the configured compute-hart vector BF16 arithmetic paths.

One ELF bundles 720 regions: two instructions, eight rounding-mode fields, three
source bit patterns, five repetitions and three harts. Each probe initializes
both floating-point operands and `fcsr`, permits a precise recoverable illegal
instruction, and checks its exact PC against the executable ELF word. The
destination sentinel and floating-point flags must remain unchanged. Raw trap
value is recorded without assuming a particular `mtval` payload. Other harts
poll or park; the guest and host watchdogs bound failure.

Build and qualify locally:

```sh
python3 benchmarks/scalar_bf16_probe/build.py --output build/NEW-bf16
python3 benchmarks/scalar_bf16_probe/qualify.py \
  --build build/NEW-bf16 --seed 0 --output build/NEW-bf16-seed0
python3 benchmarks/scalar_bf16_probe/qualify.py \
  --build build/NEW-bf16 --seed 17 --output build/NEW-bf16-seed17
python3 benchmarks/scalar_bf16_probe/acceptance.py \
  --build build/NEW-bf16 --gate build/NEW-bf16-seed0 \
  --gate build/NEW-bf16-seed17 --output build/NEW-bf16-acceptance
```

Qualification uses the exact selected functional package, not instruction-based
timing as a cycle prediction. Sixteen adversarial transcript controls must be
rejected before hardware preparation. The build preserves compiler subtools,
preprocessed sources, assembly, object files, linked library and source hashes.
Existing successful local evidence is under `build/scalar-bf16-probe-v1*`.

Actual FPGA job `runs/fpga-scalar-bf16-probe-v2` passed all 720 regions, independent
archived-ELF/UART validation, all four managed phases, owned cleanup and capture.
The observed result matches source decoder absence on every hart. Evidence is
`build/fpga-scalar-bf16-probe-v2-archive-analysis/report.json` and
`hardware/actual-scalar-bf16-observation.json`. The earlier V1 job was refused
locally before any hardware action because its environment was not sourced;
that failed attempt and its archive remain preserved.

Prepare a fresh job using the actual current authorization receipt:

```sh
python3 firesim/prepare_bf16_probe.py \
  --build build/NEW-bf16 --gate build/NEW-bf16-seed0 \
  --gate build/NEW-bf16-seed17 \
  --acceptance-report build/NEW-bf16-acceptance/report.json \
  --authorization-receipt build/CURRENT-AUTHORIZATION/receipt.json \
  --memory-probe-build build/fased-readonly-managed-v2 \
  --output runs/NEW-bf16-job
```

Only the hardware coordinator executes it, after complete idle inspection and
under the shared group lock, using the [managed recipe](../../firesim/WORKING_RECIPE.md).
Every job retains kill → infrasetup → runworkload → kill and owned failure
cleanup. No direct-driver or retained-image path is supported. The optional
read-only memory observer remains the exact reviewed binary.

After owned cleanup and external archive capture, validate archived bytes:

```sh
python3 firesim/analyze_bf16_probe.py runs/NEW-bf16-job \
  --output build/NEW-bf16-archive-analysis
```

The analyzer verifies the complete archive inventory, source identities and
actual archived ELF, then checks every observed trap and state checksum against
independent expectations. It retains raw UART, per-region cycles/instret and
five-trial statistics. This is an observational decoder diagnostic, with trap
handler and console overhead. It is excluded from performance calibration and
does not attest the full source-to-bitstream association or other BF16/FP8
operations.
