# Iris memory roofline qualification

This packet measures application-visible bandwidth and dependent-load latency
under Zephyr on the existing Iris image. H0 runs kernels, H2 initializes,
dispatches, validates every produced word, and prints after each completed
measurement; H2 blocks during the kernel. H1 is idle. No FPGA lifecycle is
invoked by build or native qualification.

The full packet has **144 configurations × 3 ordered passes = 432 observations**:

| Mapped storage | Per-stream sizes | Kernels |
|---|---|---|
| DRAM | Every power of two, 2 KiB through 8 MiB | Six below |
| H0 TCM, upper 64 KiB | 2, 4, 8, 16 KiB | Six below |
| System scratchpad | 2, 4, 8, 16, 32 KiB | Six below |

The six kernels are RVV read with an unsigned 32-bit sum, RVV constant write,
RVV copy, RVV unsigned `C=A+3*B` triad, scalar unsigned 32-bit read/sum, and
64-byte-spaced dependent pointer chasing with an address checksum. Pointer
chasing includes loop/add overhead; it is not pure load-use latency. These
are memory calibration kernels, not equivalent arithmetic benchmarks.

Twelve additional DRAM panel-read configurations use widths 32/64 bytes,
row pitches 64/2048/8192 bytes, and 128/1024 rows. They reproduce the *access
geometry* of narrow K-major matrix panels, not the complete VME load/issue
schedule. They complement contiguous STREAM-like measurements. The largest
panel address span is 8 MiB; this is not a 128 MiB weight-residency test.

RVV code uses runtime VL and LMUL4. Larger LMUL amortizes instructions but
does not widen DLEN. Small kernels transfer at least 64 KiB through repetition;
dependent chains execute at least 1024 loads and whole laps. No setup, output
validation or UART is inside the measured kernel. Completion fences and
counter instrumentation are retained. Ordinary Zephyr interrupts stay enabled.

All streams have 64-byte guards and distinct allocations. TCM uses
0x70010000..0x7001ffff and scratchpad uses 0x580000000..0x58001ffff; the linker
puts Zephyr and the DRAM buffers in DRAM. The packet must not be combined with
software reserving those private regions. Bare address support is checked by
the native run; actual hardware admission remains mandatory.

## Accounting

Report requested/semantic bytes per observed `mcycle`, not physical DRAM or
NoC bytes. A copy counts one read plus one write; a triad counts two reads
plus one write. A pointer load requests eight bytes while occupying a 64-byte
address slot. Write allocation, writeback and protocol overhead are unmeasured.
A `fence` does not evict dirty cache lines to DRAM. A memory-mapped DRAM address
does not prove an L1/L2 miss. The small reused-footprint results are *resident
candidates*, not certified L1 or L2 bandwidth.

Three ordered passes do not establish cold state, independent-run confidence
intervals, or a meaningful P90. Initialization and full validation affect
subsequent memory state. Pass 3 is reported as validation-conditioned reuse.
Destination buffers are poisoned before each write/copy/triad invocation,
outside the measured window, to detect stale correct output. This conditions
destination cache state and is explicitly not a cold/writeback measurement.
No timer frequency is assumed; GB/s requires independently established clocks.
No physical unit-busy fraction or source-to-bitstream association is certified.

For a measured bandwidth B in bytes per target cycle and an explicit arithmetic
intensity I in MACs per byte, the corresponding empirical roofline is
`min(P_compute, B*I)`. Keep contiguous and panel-access ceilings separate.
An observed bandwidth is an empirical bound for that kernel, not a proof of
the memory system's absolute maximum. Plot dependent latency separately.

## Local preparation

```
python3 benchmarks/memory_roofline_v1/build.py --output /absolute/new/packet
python3 benchmarks/memory_roofline_v1/run_native.py --packet /absolute/new/packet
```

The build creates the exact case inventory, independent expected checksums,
source hashes, toolchain/ELF receipt, Zephyr configuration and disassembly.
`--smoke` builds a smaller all-storage packet. `--negative-omit-kernel` builds
a separate failing execution control; it can never be admitted for performance.

Only a fully qualified exact packet can subsequently be prepared with the
managed FireSim runner. It must wait for the current owned hardware campaign
to terminate, then pass fresh authorization, complete inspection and shared
lock checks. Always kill → infrasetup → runworkload → owned kill, followed by
capture and independent numerical intake. No direct-driver or retained-image
path is supplied here.
