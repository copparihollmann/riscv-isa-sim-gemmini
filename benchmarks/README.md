# Iris calibration and certification guests

The default guest is one ELF containing a batch of 24 cases. It emits 54
`IRIS_REGION` rows across three harts, then `IRIS_BATCH_DONE {"failed":0}` and
HTIF success. `smoke.elf` runs only four cases and emits 12 rows. One leader prints
after collecting per-hart slots, so normal region lines cannot interleave.

Build with the available toolchain:

```sh
python3 benchmarks/build.py
python3 benchmarks/build.py --harts 1 --output benchmarks/build/harts1
python3 benchmarks/build.py --harts 2 --output benchmarks/build/harts2
python3 benchmarks/build_heldout.py
```

The root Makefile also provides `make benchmarks`, `make build-functional`, and
`make check-functional`. The last target rebuilds the guest ELFs, runs the Spike
functional selftests and guest certification workloads, and validates the batch
console. These larger checks remain separate from `make check`. Override `DTC`
when the device-tree compiler is installed elsewhere. Use
`make validate-benchmarks` to recheck existing logs without rerunning guests.

The default is three participating harts, matching the verified device tree.
Harts 0–1 execute VME; hart 2 performs scalar/memory and synchronization work and
must refuse VME. The default batch already includes single-compute-hart and
two-compute-hart cases while keeping the heterogeneous three-hart target. The
`--harts` builds are reduced-participation diagnostic guests; they do not change
the FPGA's physical hart count or certify Zephyr SMP.

`build/build.json` records ELF hashes, commands, compiler identity, and source
digests. `build/heldout-build.json` does the same for the reserved Miles sources.
Build success is distinct from execution success. Use the project's FireSim
runner with the required kill/infrasetup/runworkload/kill lifecycle and allocation
checks; do not flash once per case. Both FPGA and Spike must run the same ELF.

Validate a captured console:

```sh
python3 benchmarks/validate_console.py path/to/smoke.stdout --smoke
python3 benchmarks/validate_console.py path/to/batch.stdout
```

The validator rejects missing or duplicate case/hart pairs, fatal diagnostics,
failed checksums, and missing completion. Spike instruction-count cycles can
validate guest functionality but are not RTL timing measurements.

## Cases and measurement boundaries

The frozen [calibration corpus](calibration-corpus.json) describes scalar
dependencies and branches; DRAM stream and dependent-pointer accesses; TCM and
scratchpad accesses; shared AMOs and LR/SC; reusable barriers; cross-hart IPIs;
timer interrupts; vector arithmetic across SEW/LMUL choices; repeated int8 VME
compute; and hart-2 VME refusal. Raw regions include function setup, computation,
readback/checksum, and the counter-read overhead. Stream/chase setup occurs in the
region. They are not isolated cold-cache latency measurements.

Every region contains `case_id`, `region`, `hart`, `start_cycle`, `end_cycle`,
`instret_delta`, and `checksum`, plus its expected checksum and pass bit. End
fences order accesses before the end counters. No empty-region cost is silently
subtracted. Barrier and IPI cases intentionally include synchronization costs.
The atomic and LR/SC cases also validate the final cross-hart shared count.

Inactive harts use WFI, with CLINT MSIP wakeups from the final completing active
hart. This avoids continuously issuing DRAM reads from parked harts. Harts that
finish an active kernel early can still wait at the completion barrier while a
peer runs; that is an explicit runtime artifact to capture in traces and model.
WFI waits mask global interrupt delivery around the completion check to prevent
the check/interrupt/WFI lost-wakeup race.

The runtime uses the audited map: program at `0x80000000`, TCMs at `0x70000000`
and `0x70020000`, scratchpad at `0x580000000`, CLINT at `0x2000000`, and SiFive
UART at `0x10020000`. Unexpected traps emit `IRIS_FATAL` with hart/cause/PC/value
and fail through HTIF. Only the explicit unsupported-hart instruction test
recovers from an illegal instruction.

This is a baseline suite, not the entire parameter-identifying experiment set.
I-cache capacity, predictor behavior, exhaustive vector chaining, VME moves,
queue pressure, full cache-state control, and broader contention sweeps remain
to be added before any ±2% timing claim. No fitted parameters are shipped here.

## Held-out workloads

[heldout-corpus.json](heldout-corpus.json) reserves Miles's fused and int8 VME
GEMM sources at the exact Saturn pin, plus Merlin's one-/two-compute-hart Zephyr
GEMM/conv2d gates. Unknown Merlin shapes remain null; they are not invented.
Correctness-only runs of reserved workloads are allowed. Their timing must never
be used for fitting. A case used to tune after a failure must be retired and
replaced with an independent held-out case.

`build_heldout.py` builds the unchanged Miles mains with their original
CRT/syscalls and records the `MAX_TE=32` allocation override. These guests use
HTIF console and the source benchmark's CSV cycle output; only hart 0 executes
the kernel. They are separate workloads, not claimed as multicore Zephyr tests.

## Zephyr integration app

`zephyr/` contains a candidate RV64 SMP app with one-/two-/three-worker variants,
GEMM/conv2d checksums, mutex sharing, yields, and timer-driven sleeps. Per-worker
start semaphores prevent one fast worker from consuming another worker's wakeup.
The leader serializes the same region schema. An optional VME case yields with
tile state live; it requires verified board ISA and vector/tile context support.
It does not implement missing Zephyr context handling or establish that support.
Because each VME worker is pinned to a separate hart, this checks preservation
across yields without a second VME task clobbering the same hart's tiles. Full
save/restore certification still requires competing VME tasks on one hart,
preemption, and an agreed OS context-state contract. Zephyr failures call
`k_panic()`; host-side fatal-handler recognition is still required to turn a
fatal kernel spin into an immediate nonzero simulator exit.

The local Chipyard Zephyr worktree is empty. Chipyard's declared Zephyr pin is
`cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0`, but no checkout or Iris board was
available to build and run this app. No DTS overlay or guessed bindings are
provided. Once that exact source and a verified board are present:

```sh
west build -b VERIFIED_IRIS_BOARD benchmarks/zephyr
west build -b VERIFIED_IRIS_BOARD benchmarks/zephyr -- -DEXTRA_CONF_FILE=one-worker.conf
```

The [Zephyr app instructions](zephyr/README.md) explain all seven hart masks,
the `all-three.conf` and `hart-two.conf` variants, and mixed VME/vector-copy roles.
The board must map Zephyr CPU indices 0–2 to architectural harts 0–2 and enable the
correct CLINT timer/IPI and UART drivers. Existing official
[Zephyr SMP documentation](https://docs.zephyrproject.org/latest/kernel/services/smp/smp.html)
supports the CPU-affinity approach; compatibility with the pinned Iris fork
remains unverified. These app files are integration inputs, not a passed Zephyr
acceptance result.
