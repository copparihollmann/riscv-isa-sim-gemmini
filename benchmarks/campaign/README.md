# Broad fitting campaign

This new ELF bundles the compatible baseline 24, distribution 208 and memory-route
504 parent cases with five explicit repetitions: 3,680 cases and 6,750 active-hart
regions. It amortizes a future authorized FireSim setup over all compatible
experiments. The existing 12-region smoke remains a separate first bring-up ELF.
No held-out source or timing data enters this fitting campaign.

```
python3 benchmarks/campaign/build.py --output build/my-campaign --trials 5
python3 benchmarks/campaign/run.py --build build/my-campaign --output build/my-campaign-functional
python3 benchmarks/campaign/validate.py build/my-campaign-functional/run.stdout --corpus build/my-campaign/corpus.json
```

The build derives three separate translation units, with private static state
and explicitly returning suite wrappers. It does not link the original
`benchmark_main` implementations or return from a `noreturn finish`. The common
unchanged startup, trap handler, barriers, console and UART drain provide the
single boot/runtime. The final `finish` remains a real nonreturning HTIF exit.
Numerical failure terminates at the first failing case after printing its active
hart records; fatal traps use the common fatal path.

The generator verifies that every original kernel/preparation/checksum prefix
is byte-identical after normalizing only include names. Parent source hashes,
generated source/table bytes, compiler and libgcc hashes, full ELF disassembly,
actual PT_LOAD ranges and the exact build command are recorded. It preserves all
original and held-out files. Glue/link addresses change, so the new ELF's compiled
body and timing identity are recorded separately from the parent binaries.

Each console row has a unique `case_id` ending `.trial.N`, plus `parent_case_id`,
`trial_id`, `suite`, hart, raw mcycle/minstret boundaries, checksum, independent
expected checksum and pass flag. Phase markers identify every suite/trial begin
and end, and one final completion marker names total cases/regions/trials. The
host validator checks every expected identity exactly once and rejects missing,
duplicate, mislabeled, failed, truncated and fatal runs. Five-trial summaries
retain every raw sample; no empty-region overhead is subtracted.

All three harts participate in common barriers. Inactive harts retain the parent
WFI/MSIP-wake behavior; early finishers may spin outside their measured interval.
RVV/scalar/FPU and producer/consumer placement retain all seven hart masks.
Arithmetic VME/FP8 stays on harts 0/1; explicit expected-illegal VME probes run on
hart 2. Vector state, tile initialization, LMUL/SEW, warm/eviction preparation,
memory ordering and IRQ behavior stay as in each parent suite. No automatic VME
context save or additional dtype is implied.

The suites are compatible in one address space. Their ordinary buffers/stacks
live in DRAM; the generated PT_LOAD overlap check covers every fixed memory-route
target. The current combined ELF ends at 0x80d73800, below route-test DRAM
0x84000000. TCM0/1 targets are 0x70000000/0x70020000, scratchpad 0x580000000;
each route case prepares disjoint 0x8000 per-hart windows. The parent source bank
bit 6 settings and stride patterns are preserved; bit 6 does not imply a DRAM bank
mapping. Earlier suite writes to TCM/scratchpad are overwritten by each later
case's original preparation. Preparations are outside the measured memory-route
ROI. Warm/eviction attempts do not certify a globally cold cache state.

Execution order is five baseline trials, five distribution trials, then five
memory trials. Distribution's original eviction/shared-buffer initialization
runs at the start of each trial. Case preparation/verification stays in its
original location. In particular, baseline kernels that include checksum work
inside the region retain it; the broad campaign does not silently change their
measurement definition.

## Frozen capture checklist before any FPGA setup

The coordinating operator must bind this source/build/ELF and independent
corpus to a fresh prepared job. Follow AGENTS.md, OPERATING_RULES.md and
CAMPAIGN_POLICY.md: current exclusive operator allocation, complete all-user
process/FD/maps inspection, host boot identity, shared lock, then the exact
kill → infrasetup → runworkload → kill lifecycle with owned failure cleanup.
This directory does not perform hardware actions or authorize a reservation.

Preserve guest UART/raw manager/stdout/stderr, all 6,750 ROI records and 30 phase
markers, final completion or the complete partial failure, all five raw trials
and variance, active/inactive policy, exact runtime/HWDB/plusargs, source/ELF/
toolchain/driver/image hashes and image-association unknowns. Record separate
host phase costs for kill, transfer, setup/programming, workload and cleanup.
Inspect the actual selected image's trace/autocounter support before launch;
record supported windows/filters/data-volume limits and explicitly unavailable
instrumentation. Do not infer instrumentation from unrelated source or enable
nonexistent HPM counters. Cache/stage only hash-verified artifacts; programming
and reset still occur. Archive the quiescent job with the user-owned
`firesim/capture_run.py`, including failures, outside the mutable job directory.

Local functional mcycle deltas and host duration are not RTL/FPGA timing goldens.
This campaign is preparatory fitting coverage. It does not close identifying
coverage, Zephyr held-outs or the +/-2% validation requirement.
