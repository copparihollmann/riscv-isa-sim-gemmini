# Identifying microbenchmarks v2

This separate corpus adds **208 cases / 432 per-hart regions** to the original
24-case baseline. It leaves v1 sources, fitting definitions, held-out definitions,
ELFs, and logs unchanged. No Miles or Zephyr held-out timing is collected or used
for fitting here.

```sh
python3 benchmarks/v2/build.py
python3 benchmarks/v2/run.py
python3 benchmarks/v2/validate.py benchmarks/v2/build/run.stdout
python3 -m unittest discover -s benchmarks/v2/tests -v
```

`build.py` records exact source, generated case-table, compiler, linked libgcc,
hardware-manifest, and dtype-audit hashes. `run.py` checks those inputs, executes
the identical ELF with three heterogeneous Spike harts and the actual UART map,
and records simulator/plugin/corpus/output digests. `build/run.json` distinguishes
host elapsed seconds from guest counter values. Functional Spike cycle counts
remain instruction-based; these runs certify checksums and protocol execution,
not timing accuracy or calibrated component parameters.

Use `--select-regex PATTERN --output PATH` to build a diagnostic subset. The
complete source corpus is overwritten only by a complete build. Pending cases
are listed separately and never counted as executed coverage.

| Family | Cases | Identifying variation |
| --- | ---: | --- |
| Scalar dependencies/issue | 20 | Eight dependent ALU operations versus eight independent register chains; 128/512/2048 iterations and all seven nonempty hart subsets |
| Frontend | 6 | Explicit 512 B / 4 KiB / 16 KiB instruction bodies, 4/16 traversals, compressed instructions disabled inside bodies |
| Branches | 4 | Always-taken versus deterministic LFSR outcomes, 256/1024 iterations |
| Memory | 54 | 4 KiB–1 MiB working sets, dependent pointer chains, warm/eviction protocols; all seven subsets for private/shared reads; scalar-reader plus hart-2 scalar/vector writer |
| Atomic sharing | 21 | Same counter, independent words in one cache line, or separate 64-byte lines; all seven nonempty hart subsets |
| Scalar IEEE FP | 6 | FP16/FP32/FP64 dependent additions, 16/64 iterations |
| Vector integer | 31 | SEW 8/16/32/64, LMUL 1/2/4, dependent versus two independent chains; placement sweep over all seven subsets |
| Vector IEEE FP | 19 | FP16/FP32/FP64, LMUL 1/2, 16/64 iterations; FP32 placement sweep includes every hart subset |
| VME integer / hazards | 13 | TK 1/4; zero-iteration drain baselines; same-tile versus four-tile updates; legal placements on hart 0, hart 1, or both |
| VME FP8 | 16 | All four E4M3/E5M2 operand combinations, 16/64 iterations, FP32 accumulation; individual and paired matrix harts |
| Tile rows / zeroing | 6 | Repeated row reads, row writes, and tile zero; no column-read assumption |
| Scalar-memory / VME overlap | 2 | Serial versus interleaved matrix operations and scalar loads with identical arithmetic/load work |
| Hart-2 scalar/vector FPU | 4 | Scalar-only, vector-only, serial, and interleaved FP32 work on the shared scalar FPU |
| Distributed pipelines | 5 | Three producer/vector-compute/consumer rotations, plus two VME pipelines with compute on hart 0 or 1 and producer on hart 2 |
| VME refusal | 1 | Hart 2 must raise illegal instruction on `sf.vtdiscard` |

The source capability IDs in each case point into the hashed hardware dtype
audit. They establish available operations, not latency or peak throughput.
Golden checksums are computed independently on the host and embedded in the
guest; the console validator checks against the host corpus as well as the guest
pass bit. IEEE and FP8 arithmetic inputs here are exact small integers/ones, so
these are performance-identification cases rather than numerical edge-case
certification. The existing directed functional corpus covers separate semantics.

## Region and cache-state protocols

Initialization and cache preparation occur before the region. Counter reads,
kernel calls, loop/control instructions, and explicit completion drains remain
inside it. Scalar checksum calculation occurs after the end counters. Vector
drains store their final result and fence; VME drains configure/read a tile row
and store it so the region cannot end while the measured result is pending.
Zero-iteration VME cases expose that drain/setup floor without silently
subtracting it from any measurement.

The warm protocol initializes private target memory and reads the complete
working set once before measurement. When that working set exceeds a cache,
“warm” does not mean all accesses hit. The eviction protocol initializes the
target and then reads **2 MiB of disjoint per-hart storage at 64-byte stride**.
It is an eviction attempt, not a guaranteed cold cache: replacement policies,
bank mapping, inclusivity and concurrent traffic still matter. No guessed flush
register or cache-control instruction is used. Barriers and preparation may
also alter cache state; the protocol is reproducible software behavior, not an
assertion of exact microarchitectural state.

Shared-read buffers are initialized by the leader before the batch and remain
read-only. Private and DMA-write cases use disjoint per-hart buffers. False
sharing uses distinct atomic words in the same aligned 64-byte line. The guest
checks shared atomic totals after all harts finish, rather than accepting each
hart's local completion count alone.

## Placement and inter-hart dependencies

All nonempty subsets are represented explicitly: `{0}`, `{1}`, `{2}`, `{0,1}`,
`{0,2}`, `{1,2}`, and `{0,1,2}`. Hart 2 is a fully participating Rocket hart with
legal scalar and vector arithmetic, even though its vector parameter preset is
named `dmaParams`. VME work is restricted to harts 0–1 except for the explicit
negative instruction test on hart 2.

Every corpus case contains a `jobs` ledger with the actual hart, core kind,
operation role, units used, and independent expected checksum. The scalar/vector
pipeline rotates producer, vector-compute, and consumer roles through all three
harts. A monotonically numbered acquire/release phase counter orders each
iteration's data production, vector addition, and result consumption. Separate
VME pipelines let hart 2 produce operand bytes while hart 0 or 1 performs tile
compute/readback and the remaining hart consumes the result. Cross-job edges and
the dependency between consecutive iterations are recorded in the manifest.

These tests validate placement legality, ordering, and results. Their current
functional Spike cycles do not predict which placement is fastest. The model
must eventually account for all participating harts, their shared resources,
and blocking dependencies before that performance comparison is certified.

All three harts participate in orchestration. Inactive harts park with WFI and
are woken through CLINT MSIP by the final completing active hart. Early-finishing
active harts may wait at a completion barrier while peers finish; that explicit
runtime artifact should appear in later timing traces. All coordination and
leader console output occur outside each hart's measured kernel interval.

## Pending coverage and interpretation

Native vector BF16/FP8 arithmetic and FP8↔BF16 conversion experiments remain
pending until their model behavior and bit-exact guest oracles are certified.
FP8 **VME** cases in this ELF are ready and distinct from those vector cases.
Column readback remains blocked by the hardware audit. Additional arbitrary
operand values, rounding-mode/exception boundaries, vector chaining patterns,
memory instruction variants, and Zephyr preemption/context-state experiments
remain necessary before claiming comprehensive calibration or ±2% accuracy.

The full functional run passed all 432 rows. Its exact evidence is in
`build/run.json`; it is not RTL ground truth or a timing feasibility result.
