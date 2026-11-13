# Iris functional and performance simulator development

Start here: [USING_IRIS.md](USING_IRIS.md). The tested local entry point is
`./iris-run compute|zephyr|profile`; `./iris-run check` verifies the frozen inputs.

Current execution/activation checkpoint: [CURRENT_STATUS.md](CURRENT_STATUS.md).
Timing work prioritizes RVV/VME on compute harts0/1. Hart2 retains functional
control, boot, timer/IPI and Zephyr behavior; detailed hart2 timing is deferred.
All three harts remain present, including when a kernel uses only one/two workers.

The newest optional source build is ready:

```sh
python3 spike/run_source_VADD35a_v1.py \
  --package build/C12-source-VADD35a-optional-package-v1 \
  --profile source_compute --elf /absolute/unstripped-program.elf \
  --output build/my-new-compute-run --timeout 600
```

Use `source_compute` for finite source VADD/FADD/VME timing on harts 0/1, or
`source_os` for the separately tested Zephyr/control profile. All three harts
remain present. [Run instructions, Merlin integration and exact scope](timing/SOURCE_COMPUTE_VADD35A.md)
explain explicit unsupported-context refusals and the distinct profile limits.
The exact native passed 32 functional cases, eight preserved compiler images
and five OS groups using their respective profiles. Defaults remain unchanged.

On the latest 1,320-region reserved FPGA batch, total-cycle error is within 2%
for 432/432 FP-add, 573/576 integer-add, 48/48 FP8 matrix and 47/48 INT8 matrix
regions. All output checks and retired-instruction counts match. Across every
region, including memory, median absolute total error is 0.155%, P90 6.522%,
maximum 150.587%; 1,110/1,320 meet 2%. **Full ±2% acceptance is not met:** memory
completion/overlap and short drain phases remain weak. Predictions were frozen
before opening the new labels; there was no refit. These are isolated harts 0/1,
not concurrent Zephyr or end-to-end workload timing.

The [JSON and Perfetto source profiler](iris_model/SOURCE_EVENT_PROFILING_V3.md)
accounts for checked VADD/FADD operations and VME MACs, source occupancy and ELF
functions. Physical memory traffic, hardware utilization and roofline remain
unavailable.

A new **same-ELF Zephyr example passes on both FPGA and the packaged model**:
INT8 VME on harts 0/1, scalar control on hart 2, all nine independent checksums,
normal exit and owned FPGA cleanup/archive. [Run it and review its finite scope](firesim/ZEPHYR_COMPUTE_HARTS.md).
The earlier six-region scalar run also passes; the original mixed hart-2-vector
workload still times out. No migration/context or multicore timing certificate
follows from the new diagnostic.

The reproducible managed FPGA recipe is in [firesim/README.md](firesim/README.md).
The earlier [same-day release guide](SAME_DAY_RELEASE.md) documents the preserved
default package and earlier measured errors.

The earlier [C12 OPU developer experiment](timing/SOURCE_OPU_DEVELOPER.md)
adds source-qualified TK1/2/4 scheduling and passes eight preserved compiled
GEMM/conv2d executions with one/two compute workers, shipped/twin and full
INT32/W8A8 checks. It has its own frozen binary/source package and explicit
limits on VRF reuse, IRQs and timing. Its calibrated provider is unavailable;
the selected empirical runtime below has not been replaced.

The managed FPGA smoke,6,750-region initial fitting batch,2,313-region CPU
layout batch, two4,050-region buffered fitting batches and the new1,008-region
compute fitting batch have passed; the primary
experimental functional package now selects the matched359/ABI4 release.

The selected [FPGA-fitted experimental package](spike/empirical-current/manifest.json)
is `hybrid7bd5`: a three-hart Spike execution model with program-visible modeled
clocks, effective costs fitted to the archived1,008-region compute experiment,
and the private-cache read-readiness correction. On the same compute ELF,
its TRAIN objective is31.6% lower than the previous28a0 selection. The192
internal development-validation regions have10.23% median absolute error;
this is **not a held-out ±2% result**. The new360-region larger-footprint
comparison exposes severe intermediate-cache errors (median84–89% at16/128KiB),
while1/4MiB medians are3.81/2.43%; all rows remain published in the
[independently checked comparison](build/memory-footprints-WFI-hybrid7bd5-comparison-v2/report.json).
Memory results also include regressions:
on the2,592-region memory experiment the median is3.15%, versus3.02% before.
All errors and family comparisons are retained in the
[fit and runtime binding](calibration/compute-fit-7bd5-hybrid-binding-v1/runtime-binding.json).

The exact runtime passes32 functional programs, five Zephyr/context groups,
seven fatal/recoverable launcher tests and four Merlin `run.sh` kernel gates
(GEMM/conv2d ×one/two compute workers, shipped and twin). The kernel gates check
32,768 INT32 and32,768 W8A8 words through the OOT kernel-provider/pointer ABI;
they do not establish whole-model MLIR compilation. Separately, source-shaped
MLIR operator objects passed48 invocations on the FPGA, with three harts.
See [runtime readiness](build/hybrid7bd5-selected-release-v1/readiness.json),
[guarded-release review](build/hybrid7bd5-reference-guard-release-review-v1/report.json)
and [the selection receipt](build/hybrid7bd5-default-selection-v1/selection.json).
The provider-only hardening preserves the recorded runtime executions and
adds a fresh three-hart smoke; their original receipts are not relabeled.

Use this for functional/kernel iteration and experimental profiling. The model
still does not reproduce the recorded FPGA Zephyr stall without a watchdog;
full functional, end-to-end timing and source/loaded-image certification remain
incomplete. The previous selection remains available at
`build/empirical-28a0-guard-staging-v2/manifest.json`. Build, run and profiling
commands are in [timing/EMPIRICAL.md](timing/EMPIRICAL.md). The
[full-graph example](benchmarks/profile_vme/README.md) demonstrates actual ELF
function attribution, six CSR regions and JSON/Perfetto output, with explicit
limits on physical traffic and utilization claims.

Run an existing baremetal or Zephyr ELF without an FPGA:

```sh
python3 -m iris_model.empirical_run --elf /absolute/program.elf \
  --output build/my-first-model-run --timeout 600
```

An optional newer fitted candidate is available explicitly:

```sh
python3 -m iris_model.empirical_run \
  --model build/rvv-compute1320-fitted-optional-package-v4/manifest.json \
  --elf /absolute/unstripped-program.elf \
  --output build/my-fitted-model-run --timeout 600
```

Its [delivery receipt](build/rvv-compute1320-fitted-optional-delivery-v1/report.json)
binds the exact native, timing parameters, source capsule and validation inputs.
Eight preserved compiled-kernel executions, five Zephyr/context groups, modeled
time and fatal-handler checks pass. On the342 reserved compute-hart regions,
median absolute timing error is24.7% and p90 is36.5%; the [full phase comparison](build/rvv-compute1320-7108-fitted-reserved-root-v1/report.json)
retains every case. Use it for functional development and experimental profiling;
it does not meet the timing acceptance target. Detailed timing work now focuses
on harts0/1; hart2 retains functional control/OS support. The default remains
unchanged. [Exact run and verification instructions](build/rvv-compute1320-fitted-optional-delivery-v1/RUN.txt)
also describe the candidate's limits.

Use a fresh output directory. The runner retains all three heterogeneous harts,
the selected memory map/devices and timing parameters, raw stdout/stderr,
modeled-counter observations and a byte-bound `run.json`. Exit status, independent
numerical checks and timing accuracy are separate results. The documented
[12-region smoke and profiling example](timing/EMPIRICAL.md#running-an-existing-elf)
provides a short first check.

This workspace contains pinned source clones, an Iris-specific experimental
Spike fork, a FireSim batch-measurement runner, hardware evidence, and an online
timing-graph library. **It is not yet a certified Iris simulator or a replacement
for FPGA timing measurements.** The graph now controls instruction completion and
program-visible clocks in an [uncalibrated integration mode](timing/README.md).
Ordinary functional-mode counters still use instruction-based accounting.
The current frozen native package has 32 functional guests and a finite clocked
UART. The source-matched counter contract has no HPM counters and no `rdtime`
CSR; timer time comes from CLINT MMIO. Full bit-exact certification and the
held-out ±2% timing gate remain incomplete.

## Hardware and source identity

The inspected manager is `bwrc-amd6`. Ethan's existing Chipyard checkout is
`/scratch/eygao/iris-cy`; it has not been modified by this project. All 31 semantic
runtime fields from the supplied configuration match the installed YAML:
[comparison](firesim/runtime-comparison.json).

[Hardware manifest](hardware/manifest.json) and [hardware audit](hardware/README.md)
record full repository commits, dirty-source patches, evidence hashes, source
line references, and unresolved facts. Exact source clones are in `third_party/`;
the functional Spike uses the separately identified upstream Zvt commit, not
Chipyard's older Spike pin. [FireSim sources](firesim/source-clones.json) include
the requested libgemmini reference.

The local elaboration shows three harts: Shuttle compute harts 0/1 with
VLEN256/DLEN128 and VME, and Rocket/DMA hart 2 with VLEN256/DLEN256 and no VME.
It shows 4 GiB DRAM, two 128 KiB TCMs, 128 KiB system scratchpad, 512 KiB L2,
and a 500 kHz timer timebase. Reset enters `0x10000`; secondary startup uses
MSIP. These facts describe the saved elaboration, whose association with the
deployed image is still unverified. The FPGA's reported emulation MHz is not a
target clock frequency.

Verify evidence integrity with:

```bash
python3 -m iris_model.provenance hardware/manifest.json
```

The hardware enables FP8: both compute harts select `opuMxParams`, and the OPU
has E4M3/E5M2 inputs with FP32 accumulation. Hardware support and experimental
simulator support are separate. The [datatype audit](hardware/dtypes.md) and
`hardware/dtypes.json` distinguish conversions, arithmetic,
and accumulator formats instead of treating an ISA extension name as blanket
support. Query source-backed capabilities with:

```bash
python3 -m iris_model.capabilities --hart 0 --unit vme --dtype ofp8_e4m3 --role input --operation mac
python3 -m iris_model.capabilities --hart 2 --unit vector --dtype f64 --operation fma
```

The `dmaParams` comment saying "no arithmetic" is inconsistent with its actual
default unified backend, which instantiates integer and floating-point units.
The datatype audit follows the configured execution paths. Image association
and simulator certification remain separate gates.

## Execution and measurements

See [Spike instructions](spike/README.md), [benchmark instructions](benchmarks/README.md),
and [FireSim instructions](firesim/README.md) for build and execution commands,
supported semantics, and current blockers.

FireSim runs use `kill → infrasetup → runworkload → kill`, including cleanup on
failure, through an isolated writable manager. Cases are bundled in one ELF to
amortize flashing. Region records come from guest `mcycle` reads; host wall time
and emulation-wide cycle summaries are separate fields. Original configuration
and image hashes accompany the measurements.

The installed privileged inspector resolved the earlier process-visibility
blocker. Managed FPGA runs have passed the three-hart smoke, the 6,750-region
fitting batch, four 285-region Zephyr diagnostic batches, and a 120-region hart2
vector transfer control. Their exact receipts, cleanup results and archives are
listed in [CURRENT_STATUS.md](CURRENT_STATUS.md). The original Zephyr ELF and a
page-crossing vector store diagnostic still reproduce completion failures; those
failures are preserved and are not accepted calibration results.
Every new run must recheck actual authorization, complete all-user/device
inspection and shared-lock ownership under [the operating rules](firesim/OPERATING_RULES.md).

The actual compiler kernel and corrected scalar twin also pass a bundled
126-region FPGA corpus with all three harts active. Every one of 64,152 output
words is freshly poisoned before its invocation and compared with independent
integer goldens; an actual disabled-kernel negative detects every missing compute
write. See the [corpus and commands](benchmarks/compiler_i8_wrap/README.md) and
[archived observation](hardware/actual-compiler-i8-wrap-poisoned-observation-v1.json).
This closes these finite baremetal numerical checks, while Zephyr behavior,
whole-image/source association and calibrated timing remain separate gates.

Older prepared campaigns remain historical inputs; changes to the runner require
fresh preparation. A separate
[memory route suite](benchmarks/memory_routes/README.md) adds 504 cases / 864
regions across both TCMs, scratchpad, DRAM and every hart subset; its functional
and seeded-repeat checks pass. Its hardware job is prepared at
`runs/fpga-memory-routes-safety-v1`. Preparation never contacts hardware.

Earlier diagnostic smoke runs passed 12 regions twice and then failed with
invalid all-ones MMIO. Their logs remain historical, calibration-ineligible
artifacts in `runs/fpga-smoke-access-enabled-001/`; their direct-driver procedure
is now prohibited. The host has since rebooted, so those observations establish
no current device health or rights. Loaded-image/build association remains
unverified. The managed read-only observer has since measured startup FASED
read/write settings of 30 target-memory-clock cycles; these are not whole-SoC
memory latencies or admitted calibration. See [the observation contract](firesim/MEMORY_OBSERVATION.md).

An existing VCS `IrisConfig` executable was also tried in an isolated directory.
It exits 127 before simulation because `libvirsim.so` and ten other Synopsys
runtime libraries are absent; the expected `/tools` installation is not mounted.
The VCS design and FireSim Combined design have distinct device-tree hashes and
are not assumed equivalent. [RTL probe](hardware/rtl-probe.json) records the command,
binary identity, dependencies, and failure. The alternative standalone saved-FIR
Verilator build now boots. Selected three-hart HPM/rdtime RTL proofs and
[8,448 FP comparator unit cases](hardware/fpcomp_unit/README.md) pass; this
standalone reference is not attested as Ethan's Combined FireSim image.
An [identical-ELF scalar comparison](benchmarks/scalar_rtl/README.md) now records
263/136 RTL cycles for Shuttle dependent/independent work versus 267/140 in the
original isolated prototype. That historical +2.94% independent error remains
preserved. A later separately frozen, blinded scalar-component experiment
matches all 60 regions exactly across all three harts:
`build/scalar-component-validation-rocket-fresh-v1/report.json`. This is a narrow
source-component result; it does not qualify whole-workload accuracy on Ethan's
image. The distinct source frontends, pipelines and live cache integration are
tracked in [CURRENT_STATUS.md](CURRENT_STATUS.md).
Generate the current feasibility report with `python3 -m iris_model.feasibility`.

## Online graph and profiling

`timing/` implements a native C++ event scheduler with per-hart completion callbacks,
dependency edges, shared resource issue capacities, modeled counters, timer and
software-interrupt lines, sparse permission-checked memory, and cross-hart
reservation invalidation. Timer events can wake a parked hart without retired
instructions. Functional side effects belong in event callbacks; executing
shared-memory effects ahead of the global event clock is not supported.

The library retains history and scans active sets for scheduling. The adapter
supports integer per-hart clock dividers and deferred completion. The primary
adapter has one instruction in flight per hart. An isolated four-packet Shuttle
ALU pipeline now passes directed and independent random programs, precise traps,
source-matched compressed expansion, and actual three-hart Zephyr tests; it is
not yet published as the primary model. Full pipeline/queue models,
scalar-vector overlap, cache/NoC/DRAM timing and source-matched calibration remain
unfinished. Integration-test costs are synthetic and never installed as Iris
defaults.

The newer [Rocket source/cache path](pipeline/ROCKET_FABRIC.md) executes actual
ELFs with physical cache requests, nacks, replays and late data writeback. The
separately frozen MemorySystem now joins cache/NoC/L2, SerialTL, Bringup and FASED
peers internally. Its service parameters remain explicit fixtures. Binding those
components into the live model and adding both Shuttle cache paths are ongoing;
the primary functional package does not silently select these experimental
timing epochs.

The [scalar memory extension](timing/MEMORY.md) now routes RV64 integer/FP/C/A
accesses through address-specific shared stages. It models explicit banks, packet
widths, receiving clocks and final-response visibility. Six live runs and seven
refusals check guest-cycle sensitivity, three-hart contention, completion ordering
and repeatability. Vector memory, translated addressing and cache/coherence state
remain unsupported in this opt-in fixture. No hardware latency is guessed.

`iris_model.report` emits JSON summaries and Chrome/Perfetto timelines with
dependency flows and optional ELF-symbol attribution. Resource busy time is an
interval union, not the sum of overlapping pipeline latencies. Queue-wait sums
are operation statistics, not an additive CPU stall breakdown. Roofline output
requires sourced compute/bandwidth peaks and an explicitly chosen traffic level;
missing information stays unavailable. Unmarked graph groups use operation spans. The guest-region profiler can
match explicitly reported mcycle boundaries to completed CSR reads when its
constant-counter/WFI-clock proof succeeds. Declared memory-stage bytes and port
waits are reported separately from measured application traffic and CPU stalls.

The [Saturn source profiler](timing/SATURN_PROFILING.md) now emits JSON and
Perfetto for independently checked three-hart VME, RVV, FP-comparison and shared
FPU captures. It keeps INT8/FP8 acceptance, physical completion and pipeline-tail
activity separate, reports reset scrub and unknown coverage, and supports
explicit source-coordinate regions. These component profiles do not establish
whole-SoC timing accuracy or kernel function ownership.

```bash
make check
make profile-example
```

`make check-functional` separately rebuilds the guest corpus and reruns actual
Spike handler/ELF checks. `make build-functional` rebuilds the pinned fork first.
An optional sanitizer build was attempted but could not link because this
session lacks `/usr/lib64/libasan.so.6.0.0`; the ordinary native checks run.

The example outputs `build/timing/profile/{summary,timeline}.json` from a
**synthetic multicore test**, not Miles's measured kernel. Profile real adapter
graphs with an explicit target frequency and its source:

```bash
python3 -m iris_model.report profile graph.json \
  --clock-hz "$TARGET_HZ" --clock-source "$CLOCK_EVIDENCE" \
  --elf workload.elf --nm "$RISCV_NM" --output runs/profile
```

## Zephyr, accuracy, and remaining gates

Multicore Zephyr is a required integration target. Certification must include
actual SMP boot, per-hart ISA refusal, LR/SC and AMOs, fences, shared-memory
contention, IPIs, timer interrupts, WFI wakeup, synchronization, and VME state
across context switches. A single-hart trace replay cannot satisfy this contract.
The exact declared Zephyr source is cloned and an actual three-hart Iris board
is implemented. All seven scalar worker placements pass. Competing VME tasks
save and restore complete tile/FP/RVV/config state across timer preemption and
hart migration under an explicit ownership ABI; hart 2 runs independent vector
work. Positive and deliberately broken context images check the contract.
See [context evidence](zephyr/CONTEXT.md).

Real Merlin and Iris OOT implementation branches are integrated in
`integration/{merlin,iris-mlir}` with the pinned LLVM 23 toolchain. Actual compiled
GEMM/conv2d execute inside Zephyr at one/two compute workers, with concurrent
hart-2 production. Eight shipped/twin programs match 98,304 int32 and 98,304 W8A8
values. The explicit registered task pipeline is supported; generic whole-model
worker ownership remains unfinished. Build/run details and evidence are in
[compiler pipeline instructions](zephyr/compiler-pipeline/README.md).

```sh
cd integration/iris-mlir
examples/iris/run.sh op gemm --harts2 --zephyr-mlir
```

`--harts` selects compute workers; the simulator still boots all three physical
harts with heterogeneous ISA settings. Final compiler/context evidence retains
an immutable native binary and complete source/evidence closure, so later native
changes do not relabel historical results.

No fitted timing calibration or qualified RTL/FireSim timing dataset is shipped.
There is no ±2% claim. The implementation must first establish:

1. Bit-exact certification of supported VME semantics and actual three-hart SoC
   devices/boot, using independent reference and RTL measurements.
2. Calibrated extension of the live Spike adapter, which already controls
   execution and counters in explicit synthetic one-in-flight fixtures.
3. Isolated and mixed calibration measurements, including vector/matrix overlap,
   serial-TL saturation, and multicore interference.
4. Independent held-out Zephyr GEMM/conv2d and Miles benchmark validation, per
   region and end to end, with ±2% gates and measured simulation throughput.

`python3 -m iris_model.report validate measurements.json --output validation.json`
computes signed errors, rejects fitting/holdout overlap and stale hardware or
simulator identities, and fails measurements outside ±2%. Passing supplied rows
does not itself certify workload coverage or functional correctness. Fast-forward
is not implemented. Full-model GPT/MoE, Llama, Gemma, and TinyLlama support is not
claimed; representative operators follow after these gates.

The observed 4-GiB DRAM capacity matters for those later workloads: 7 billion
8-bit weights alone occupy about 7 GB before activations or KV state. Full-model
runs will therefore need an explicit memory strategy such as streaming,
partitioning, or a smaller weight representation; operator-level development
does not establish full-model residency.

The [memory route audit](hardware/memory-paths.md) records actual per-hart paths,
TCM aliases, cache/bank/clock facts and unknown latency fields. The
[transfer timing component](timing/MEMORY.md) controls scalar memory completion
in the opt-in fixture; it does not supply a calibrated Iris memory model.

The actual Iris Zephyr board now passes all seven scalar worker placements and
live-clock SMP runs; see [Zephyr instructions](zephyr/README.md) and
`zephyr/test-results.json`. Source-matched RTL/FPGA certification remains open.
Actual guest-region profiles are in `build/zephyr-profile-final3/`; their prices
are synthetic and do not predict Iris performance. Reproduce with:

```sh
python3 -m iris_model.guest_regions build/zephyr-live-final3/graph.json \
  --elf build/zephyr-placements/build-mask7/zephyr/zephyr.elf \
  --console build/zephyr-live-final3/stdout \
  --fixture timing/fixtures/three-hart-slow.fixture \
  --rom board/evidence/bootrom.rv64.img \
  --run-receipt build/zephyr-live-final3/results.json \
  --nm /scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm \
  --output build/zephyr-profile-final3
```

The mixed scalar/VME/RVV demonstration at `build/zephyr-mixed-profile/` similarly
matches nine actual guest regions. Verify the selected OS/compiler evidence with
`python3 zephyr/reconcile.py --verify`.
