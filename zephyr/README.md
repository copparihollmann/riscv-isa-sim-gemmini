# Iris Zephyr integration

The exact Chipyard-declared Zephyr fork is cloned cleanly at
`cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0` under `third_party/zephyr`.
The fork contains a QEMU-derived generic Chipyard board but no Iris board. This
directory supplies an out-of-tree Iris board derived from the frozen hardware
DTS and memory audit; it does not use the QEMU board or QEMU runtime.

The board describes three architectural harts, the real DRAM/TCM/scratchpad
addresses, 500-kHz CLINT timebase, one-source PLIC and SiFive UART at
`0x10020000` with source 1. All three harts have a source-derived local elaboration
clock of 500 MHz. These source facts are not deployed-bitstream attestation.
Only DRAM is selected for automatic kernel allocation; listing TCM/scratchpad as
disabled OS memory nodes does not remove their hardware mappings.

The selected existing RocketChip SoC family supplies RV64GC machine-mode startup,
timer/IPI/PLIC support and HTIF completion. Its internal `CONFIG_SOC` string
contains `spike_rocketchip_riscv64`; the board selects no QEMU target. Userspace
and global PMP use are disabled because hardware PMP entries differ as `0/0/8`.
FPU sharing is enabled; the scalar acceptance image leaves RVV disabled. The
board preserves the source DTS ISA advertisements as metadata, including the
known scalar-BF16 advertisement discrepancy documented in the datatype audit.

Build and run with the existing pinned Chipyard GCC/tool environment:

```sh
python3 zephyr/audit.py --verify
python3 zephyr/build.py
python3 zephyr/run.py
python3 zephyr/check_placements.py
python3 zephyr/check_protocol.py
```

The scripts take explicit compiler, simulator, plugin, build and output paths.
They verify the clean Zephyr pin, source/build/artifact digests and independent
GEMM/conv2d checksums. No external Zephyr modules were needed for this selected
minimal-libc configuration; the fork's `west.yml` records optional module pins.
Builds using other features must fetch their actual manifest dependencies.

All seven nonempty worker masks have passed on three real Spike harts through
Iris's physical ROM path: 24 per-hart scalar regions in total. The selected mask
controls application worker placement; the OS still boots all three harts and
may schedule main/idle/runtime work outside the worker set. The test includes
real kernel synchronization, yields and timer sleeps. Receipts are in
`build/zephyr-placements/results.json` and its per-placement directories.
Seven additional host-protocol negative fixtures reject wrong goldens, missing
hart 2, duplicate output, boolean hart IDs, overflowing counters, fatal messages
and missing completion. These fixtures are parser checks, not CPU execution.

A live-clock integration run is available separately:

```sh
python3 zephyr/run.py \
  --build build/zephyr-placements/build-mask7 \
  --output build/zephyr-live-example \
  --timing-fixture timing/fixtures/three-hart-slow.fixture
```

That fixture is synthetic, with deliberately different counter clock dividers.
Its graph and guest counters verify online OS/timer integration, not Iris
performance or a preferred workload placement. Functional-mode cycle values
remain instruction-based. RTL/FPGA Zephyr validation, source/image association
and the +/-2% gate remain outstanding.
Use `--seed 17` to exercise recorded scheduling variation. Two identical seed-17
live runs produced identical stdout and graph hashes. Run receipts retain an
exact runner-source snapshot as well as fixture, graph, ELF and simulator hashes.

Successful simulator acceptance prints `IRIS_BATCH_DONE` after the regions,
waits for the real UART FIFO-empty watermark and a final-frame guard, then calls
the verified RocketChip HTIF-success reboot hook. It writes `tohost=1` and parks;
it does not restart the image. `IRIS_BENCH_EXIT_ON_COMPLETION` is an explicit app
acceptance option, disabled by default in Kconfig and enabled by this app's
`prj.conf`. Fatal handler symbols are resolved from the actual ELF so a panic
terminates the host simulation instead of appearing as a timeout.

The pinned base fork saves ordinary RVV state but no VME tiles or matrix
configuration. Its input-only assembly cursor constraint is now corrected in
an explicit derived tree. The baseline GCC16 disassembly kept the original
pointer separately and passed the actual FP/RVV stress; an observed baseline
miscompile is not claimed.

The derived kernel supplies explicit VME ownership and full context handling.
Four competing tasks preserve tile/FP/RVV/configuration state through timer
preemption and migration between harts 0/1, then execute INT8 and exact FP8 MACs.
A concurrent hart-2 producer uses ordinary RVV and is refused VME ownership.
The mixed app calls the API explicitly and passes nine regions on all three
harts. See [CONTEXT.md](CONTEXT.md) for the API, commands and evidence. These are
functional source-model results; RTL/FPGA and timing certification are pending.

Real Merlin MLIR GEMM and convolution-contraction models also execute through
their actual LLVM23 descriptor ABI inside this OS, with one/two compute workers
and a concurrent hart-2 double-buffer producer. Shipped VME and scalar-twin
images match all 98,304 int32 and 98,304 W8A8 values across eight programs.
See [compiler-pipeline/README.md](compiler-pipeline/README.md) and verify the
archived native identity with `python3 zephyr/compiler_acceptance.py --verify`.
`python3 zephyr/reconcile.py --verify` checks the selected acceptance ledger.
# UART deployment profile

Ethan's inspected FireSim UART bridge has a fixed decoder (`UARTKey(div=135)`)
at500MHz. Select `--uart-profile ethan-firesim` with `build.py` or
`context_build.py`; the target-owned Merlin Zephyr workflow selects it by
default. The overlay requests3676470baud so the pinned Zephyr driver's
`500000000/current_speed-1` calculation programs DIV135. The configured source
nominal rate was3686400; requesting that number directly would program DIV134.
Actual UART bit duration is136source edges, about3676470.588baud.

The base board keeps the physical115200profile (DIV4339), also compatible with
the separately identified saved-IrisConfig RTL harness. That setting cannot be
assumed to work through Ethan's fixed decoder. No hardware, bitstream, common
bare-metal runtime DIV or bridge setting is changed by these profiles. Source
evidence is in `uart-profiles.json`; actual deployment/image association and
FPGA Zephyr execution remain unqualified. New example applications read back
the programmed DIV and print `IRIS_UART_PROFILE` before measured regions.

