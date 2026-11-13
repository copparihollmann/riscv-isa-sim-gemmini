# Zephyr SMP acceptance app

The exact declared Zephyr fork and a source-backed out-of-tree Iris board are
now present. The scalar app has built, booted through the physical Iris ROM and
passed all seven worker placements on three Spike harts. See
[`zephyr/README.md`](../../zephyr/README.md) for build/run commands and receipts.
The derived kernel now passes explicit VME context tests; see
[`zephyr/CONTEXT.md`](../../zephyr/CONTEXT.md). RTL timing validation remains
separate.

`CONFIG_IRIS_BENCH_HART_MASK` selects any of masks 1–7. Set
`CONFIG_IRIS_BENCH_WORKERS` to its population count and enable all selected CPUs
with the board's `CONFIG_MP_MAX_NUM_CPUS`. Mask 7 / three workers selects all
three harts. Mask 4 / one worker tests hart 2 alone. Every worker checks that its
Zephyr CPU index matches `mhartid`; an unexpected board mapping fails visibly.

Scalar GEMM/conv2d work partitions rows over the selected workers, including
hart 2. The optional mixed vector case runs VME only on harts 0/1 and legal RVV
byte-copy work on hart 2. It yields with live vector/tile state and reports each
hart's actual role. It never sends a VME instruction to hart 2. The matrix and
copy checksums are independent checks, not evidence of a producer/consumer
pipeline between them.

Build against the verified board with its supported toolchain, adding
`-DSATURN_ROOT=<pinned Saturn clone>` only for `CONFIG_IRIS_BENCH_VME=y`.
Keep vector auto-generation disabled for the ordinary C code so that explicit
instruction placement is reviewable. The board must provide M-mode access to
the CSRs used here or a verified equivalent guest counter contract.

The main thread and synchronization can run outside the pinned worker set;
record that runtime interference during timing calibration. A passing run must
verify the region hart set, roles, independent checksums, timer/preemption and
completion marker. This app alone does not establish competing-task tile
save/restore: a separate same-hart context-switch stress workload is required.

Simulator acceptance enables `IRIS_BENCH_EXIT_ON_COMPLETION` explicitly. On this
board it flushes the UART and uses the source-verified HTIF completion hook,
writing `tohost=1` instead of rebooting into another run. Disable it for a
resident firmware workload. The VME option requires RVV, FPU sharing and the
derived Iris context extension. Compute workers call `iris_vme_enable()` before
the measured VME region, explicitly initializing all tiles. CMake rejects
missing context support; the kernel rejects VME ownership on hart 2. The
separate competing-task stress validates full context and compute-hart migration.
