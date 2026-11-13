# Iris same-day experimental release — November 6, 2026

The usable selection is **hybrid7bd5**, calibration
`iris-empirical-hybrid7bd5-compute-v1`. It executes actual baremetal/Zephyr ELFs
on all three harts and supplies program-visible modeled counters plus JSON and
Perfetto profiling. It is an experimental effective-service model; full Iris,
RTL, loaded-image, whole-Zephyr timing and ±2% certification remain incomplete.

The current pointer is [`spike/empirical-current/manifest.json`](spike/empirical-current/manifest.json).
For an immutable run, select
[`build/empirical-hybrid7bd5-reference-guard-v4/manifest.json`](build/empirical-hybrid7bd5-reference-guard-v4/manifest.json)
explicitly. Its SHA256 is
`9b3995a1f2697db991f47060cc11d89de4dcc092ced30c175c846ca69f8ce60f`.
The native SHA begins`7bd58b4f`, UART`9c6d1bcc`, and fitted fixture`70c0a5cd`;
full identities, all repository commits and source closures are in that manifest.

## First software run and profile

Run from `/scratch/copparihollmann/iris-model`, using fresh output directories:

```sh
python3 -m iris_model.empirical_run --help
python3 -m iris_model.empirical_run \
  --model build/empirical-hybrid7bd5-reference-guard-v4/manifest.json \
  --elf benchmarks/build/smoke.elf --output build/my-iris-smoke --timeout 120
python3 benchmarks/validate_console.py build/my-iris-smoke/stdout --smoke
python3 -m iris_model.empirical_profile \
  --prefix build/my-iris-smoke/features.jsonl \
  --console build/my-iris-smoke/stdout --elf benchmarks/build/smoke.elf \
  --rom board/evidence/bootrom.rv64.img \
  --fixture calibration/compute-fit-7bd5-hybrid-selected-v1/runtime.fixture \
  --run-receipt build/my-iris-smoke/run.json --output build/my-iris-profile
```

Open `build/my-iris-profile/trace.json` in Perfetto; inspect `summary.json` for
per-hart ROI, work, cache-intent and resource-occupancy fields. `run.json` retains
the exact argv, selected descriptor, raw stdout/stderr, exit/timeout and owned
local cleanup. Successful exit, independent numerical validation and timing
accuracy are separate results. The launcher expects an unstripped static RV64
little-endian ELF; fatal handlers on any hart terminate the run, while ordinary
recoverable traps continue. Unknown required state or invalid provenance refuses
execution. Keep the provider's three-hart ISA/memory/device arguments intact.

To build a fresh smoke/batch ELF without modifying the frozen copies:

```sh
python3 benchmarks/build.py --harts 3 --output build/my-iris-benchmarks
```

Use its new `smoke.elf` with the same run/profile commands. The compiler defaults
to Ethan's existing RISC-V toolchain; the build records compiler/source hashes.
The [full-graph recipe](benchmarks/profile_vme/README.md) separately builds a
compact INT8/FP8 VME guest and demonstrates six actual CSR regions, ELF function
attribution, normal HTIF exit and bounded/full counter parity. Its frozen example
uses the preserved28a0 selection: [summary](build/full-graph-VME-profile-v4/summary.json),
[Perfetto trace](build/full-graph-VME-profile-v4/trace.json),
[conditional-capacity chart](build/full-graph-VME-source-capacity-overlay-v1/overlay.svg).
Read the [capacity interpretation](timing/VME_CAPACITY_INTERPRETATION.md) before
comparing INT8 and FP8 fractions. Physical bandwidth, roofline and stall causes
are unavailable; model occupancy and requested bytes do not establish them.

The current guard V4 also has its own actual
[six-region profile](build/full-graph-VME-selected7bd5-profile-v5/summary.json),
[Perfetto trace](build/full-graph-VME-selected7bd5-profile-v5/trace.json) and
[qualification](build/full-graph-VME-selected7bd5-profile-v5/report.json).
It checks 144 active plus 48 padding words, 12 cycle-prefix endpoints,12 captured
minstret reads and 16,384 logical MACs. Bounded/full outputs and features match,
both exit normally; eight CPU tail operations remain pending at HTIF exit.
Reproduce with the existing frozen guest and fresh output directories:

```sh
python3 -m iris_model.graph_run_buffered \
  --model build/empirical-hybrid7bd5-reference-guard-v4/manifest.json \
  --elf build/full-graph-VME-guest-buffered-v4/profile-vme.elf \
  --layout build/full-graph-VME-guest-buffered-v4/readback-layout.json \
  --history bounded --output build/my-selected-vme-bounded --timeout 120
python3 -m iris_model.graph_run_buffered \
  --model build/empirical-hybrid7bd5-reference-guard-v4/manifest.json \
  --elf build/full-graph-VME-guest-buffered-v4/profile-vme.elf \
  --layout build/full-graph-VME-guest-buffered-v4/readback-layout.json \
  --history full --output build/my-selected-vme-full --timeout 120
python3 timing/profile_vme_full_graph_v5.py \
  --build build/full-graph-VME-guest-buffered-v4 \
  --bounded build/my-selected-vme-bounded --full build/my-selected-vme-full \
  --output build/my-selected-vme-profile
```

Full history costs host RAM/disk: this trace has 759,487 events and approximately
344 MB of Perfetto JSON. The history-only change preserves every fitted cost.

## Three-core capabilities

| Capability | Harts 0/1 | Hart 2 |
|---|---|---|
| CPU and vector geometry | Shuttle; VLEN256, DLEN128 | Rocket; VLEN256, DLEN256 |
| Scalar | RV64 integer, FP16/FP32/FP64 | RV64 integer, FP16/FP32/FP64 |
| Ordinary vector integer | signed/unsigned8/16/32/64-bit, instruction-specific widening | same widths; INT8 is supported |
| Ordinary IEEE vector | FP16/FP32/FP64 | FP16/FP32/FP64 |
| Vector minifloat | BF16 and E4M3/E5M2 FP8 on configured arithmetic/conversion paths | bit transport; no configured BF16/FP8 arithmetic/conversions |
| VME | INT8→INT32 and FP8 E4M3/E5M2→FP32 accumulation | illegal instruction; no VME |

These are [source-backed configured paths](hardware/dtypes.json), not blanket
operation certification. Minifloat comparison/divide/sqrt and arbitrary conversion
pairs are not implied; query exact roles/operations below. Scalar BF16 conversions
and scalar FP8 arithmetic are not configured on any hart; the
[720-case hardware scalar-BF16 check](build/scalar-bf16-hardware-closure-v1/report.json)
confirms precise illegal conversions for that finite corpus. VME column readout
remains unsupported. DLEN is not the bus width: compute ATL is256-bit and Rocket
ATL64-bit. Hart 2 can run producers, ordinary RVV INT8 and IEEE work while harts 0/1
compute VME. The empirical memory path approximates caches/contention across all
three; it does not claim exact NoC/coherence timing.

```sh
python3 -m iris_model.capabilities --hart 0 --unit vme \
  --dtype ofp8_e4m3 --role input --operation mac
python3 -m iris_model.capabilities --hart 2 --unit vector --dtype i8 --operation add
```

The saved configuration has 4 GiB DRAM, two 128 KiB TCMs, 128 KiB scratchpad and 512 KiB
L2. CLINT MMIO provides timer time; `rdtime` and HPM hardware counters are absent.
Required register/tile state must be initialized. Exact instruction, PMP, atomics,
interrupt and context limitations are retained in the functional/source reports.

## Merlin kernel front door and model selection

```sh
export MERLIN_PYTHON=$PWD/build/merlin-venv/bin/python
export MERLIN_CHIPYARD_IRIS=/scratch/eygao/iris-cy
export MERLIN_PROVIDER_BASE_PATH=$PWD/third_party/rvv-mlir
export MERLIN_IRIS_MODEL_MANIFEST=$PWD/build/empirical-hybrid7bd5-reference-guard-v4/manifest.json
export MERLIN_IRIS_TIMING=empirical
export MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING=1
integration/iris-mlir/examples/iris/run.sh op gemm --harts 2 --model-root "$PWD" \
  --compiler /scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc \
  --output build/my-iris-gemm --timeout 600
```

Use `op conv2d` or `--harts 1` for the other checked front doors. Compute-worker
selection retains all three physical harts. This OOT C/pointer-workspace kernel
gate checks shipped and twin results; it does not compile GPT/MoE, Llama, Gemma or
TinyLlama end to end. Existing separate MLIR operator demonstrations do not imply
whole-model compiler coverage. Python3.12 is required for the upstream Merlin code.

Select another published package using `--model` for the ELF runner or
`MERLIN_IRIS_MODEL_MANIFEST` for Merlin; do not edit fixtures or swap the paired
native/UART. The previous package is
`build/empirical-28a0-guard-staging-v2/manifest.json`. Ordinary functional359 and
source-RTL component experiments are separate providers/modes.

## Accuracy, tests and guard lineage

On the same 1,008-region compute ELF, the new all-TRAIN objective is 31.59% lower
than28a0. All-region median absolute error changes 13.20%→10.29%, p90
51.47%→44.13%; within2% changes 125→124. The 192 internal development-validation
rows have 10.23% median, 35.42%p90 and 62.09% maximum error. They are not a blind
acceptance set. On 2,592 memory regions, median error regresses 3.02%→3.15%; the
new worst error is 193.94%. Shared-outer/TCM/scratch values remain inherited, unqualified priors. No per-case/PC runtime lookup or ROI intercept supplies costs.
See the [fit/binding](calibration/compute-fit-7bd5-hybrid-binding-v1/runtime-binding.json),
[compute comparison](build/hybrid7bd5-vs-selected28-sameELF-compute-v1/report.json)
and [memory comparison](build/memory-routes-current-7bd5-hybrid-selected-comparison-v1/report.json).

The newer [360-region WFI-ended memory-footprint experiment](build/memory-footprints-WFI-hybrid7bd5-comparison-v2/report.json)
also exposes a substantial gap in this selected model: median absolute error
18.55%, p90 92.37%, only 5/360 regions within 2%, with no instret mismatches.
Per-footprint median absolute errors are 84.46% for 16 KiB and 88.59% for128 KiB,
versus 3.805% for1 MiB and 2.425% for4 MiB. Close aggregate cycle sums do not
establish end-to-end accuracy: these are sums of separate measured regions,
including overlapping per-hart windows. No new coefficients were used in that
comparison. A later candidate fit is separate from the immutable selection here.

The unchanged parent runtime passes 32 functional programs, five exact-cost
Zephyr/context groups, seven fatal/recoverable launcher executions and four
Merlin gates: GEMM/conv2d ×one/two compute workers, shipped and twin, checking
32,768 INT32 and 32,768 W8A8 words. The
[readiness receipt](build/hybrid7bd5-selected-release-v1/readiness.json) links each
actual execution. Guard V4 adds archived-reference provenance checks without
changing native/UART/fixture/parameters/ISAs; its
[independent review and fresh 12-region smoke](build/hybrid7bd5-reference-guard-release-review-v1/report.json)
preserve parent execution labels rather than relabeling those tests as new child
executions. [Selection receipt](build/hybrid7bd5-default-selection-v1/selection.json).

The original FPGA Zephyr hang and page-crossing vector failure remain unresolved;
successful instrumented/fenced/NOP controls are not general fixes, and the model
does not reproduce the recorded no-watchdog stall. Strict source-frontend/RAS,
scalar-FADD source pipeline, shape-work and owned-store opt-ins are OFF in this
hybrid mode. Unknown source paths are not secretly seeded or automatically
replaced. Full held-out±2%, source/loaded-image association and arbitrary workload
timing remain open. Hardware access still requires root coordination and the
full managed lifecycle under [operating rules](firesim/OPERATING_RULES.md).

The native's archived 3,920-file source closure reconstructs 2,025 native source
files from Spike commit `72958551566a30f19444bd7e354552824e4d0a98` plus its
[exact overlay](build/empirical-read-overlap-response-frozen-7bd58b4f/source-overlay.patch).
The [verification](build/empirical-read-overlap-response-frozen-7bd58b4f/verification.json)
does not claim a byte-identical full rebuild. To rebuild in this workspace while
preserving the shared checkout, use an independent clone and new build directory:

```sh
git clone --no-hardlinks third_party/riscv-isa-sim pipeline/my-iris-native
git -C pipeline/my-iris-native checkout --detach 72958551566a30f19444bd7e354552824e4d0a98
git -C pipeline/my-iris-native apply \
  "$PWD/build/empirical-read-overlap-response-frozen-7bd58b4f/source-overlay.patch"
python3 pipeline/build_native_empirical.py \
  --source pipeline/my-iris-native --build build/my-iris-native
```

This recipe needs the workspace's archived peer SDK/libraries. It is not a portable
fresh-machine bootstrap or a claim of byte-identical reproduction. A rebuilt
native is a new byte identity needing its matched UART and gates before
publication. The heavy rebuild was not repeated for this handoff; the shipped
immutable pair is sufficient to run the commands above.

The completed software-only descriptor/CLI and historical receipt checks are in
[the v1 command receipt](build/same-day-handoff-software-checks-v1/commands-and-receipts.json).
The later v2 documentation check stopped at its not-yet-written self-link; it is
incomplete and supplies no final qualification. The current selected graph/profile
has its separate completed V5 receipt linked above.
Current operational progress belongs in [CURRENT_STATUS.md](CURRENT_STATUS.md).
