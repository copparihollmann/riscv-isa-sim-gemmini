# Memory routes and bank contention

This separate fitting suite adds504cases/864hart regions. It exercises all
seven nonempty subsets of the three physical harts, including hart2 accessing
the global TCM0/TCM1 addresses. It never changes the frozen baseline or held-outs.

```sh
python3 benchmarks/memory_routes/build.py --output build/memory-routes-fit-v1-final
python3 benchmarks/memory_routes/run.py --build build/memory-routes-fit-v1-final
python3 benchmarks/memory_routes/verify.py --build build/memory-routes-fit-v1-final
```

Use a fresh directory for each build/run; `--select-regex` builds diagnostic
subsets and `--seed` selects a recorded functional hart interleaving. The build
archives its sources/compiler/libgcc and checks that fixed target windows do
not overlap any ELF load segment, including BSS/stacks. Execution archives the
native/plugin/provenance/dtc bytes. The independent host validator rejects
missing hart2 rows, duplicate regions and forged checksums, even if the guest
prints a passing result. Nothing contacts the FPGA.

Each active hart owns a disjoint32KiB window in the selected128KiB target:
TCM0 at0x70000000, TCM1 at0x70020000, scratchpad at0x580000000, or a reserved
DRAM window at0x84000000. Sixty-four nodes use either128-byte strides (constant
source SRAM bank bit6),128-byte strides with hart1 offset64 (opposing bank),
or64-byte strides (alternating bit6). The manifest records every exact address
and sourced scalar memory route. Bit6 does not assert a DRAM device bank map.

The measured kernels are33/257dependent64-bit pointer loads (a permutation
advances13nodes),1/16passes of64 scalar reads, or1/16passes of64 scalar writes.
Inputs are initialized before a global barrier; this is a reproducible warm
protocol, not a cache-flush, hit or cold-state guarantee. Raw `mcycle` and
`minstret` intervals include calls, loops, fences and counter reads. Verification
and console output are outside each region. Kernel payload bytes exclude
stack/control accesses and cache-line/NoC transport.

Inactive harts wait with WFI and wake by MSIP. Early active finishers may spin
at a barrier outside their own interval while peers are measured; this real
runtime artifact must be retained when fitting. Concurrent windows are disjoint,
so these cases isolate shared paths/banks without intentionally sharing data
cache lines. They complement, rather than replace, cache-line sharing, vector
load/store, coherence, instruction-fetch and Zephyr cases elsewhere.

Functional checks establish placement/results and provenance only. They provide
no reference latencies or calibrated bandwidth. The new ELF must still run
through the authorized full FireSim lifecycle, or an independently identified
RTL reference, before its timing numbers can be admitted for fitting.
