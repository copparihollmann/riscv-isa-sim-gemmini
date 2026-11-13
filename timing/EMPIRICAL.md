# Experimental FPGA empirical timing

The selected experimental package is
[`spike/empirical-current/manifest.json`](../spike/empirical-current/manifest.json),
identity `iris-empirical-hybrid7bd5-compute-v1`. It combines the frozen7bd5
native, private-cache response-readiness policy, legacy approximate frontend and
new TRAIN-only effective-service fit. Source frontend/RAS, scalar-FADD source
pipeline, shape-work and owned-store-front opt-ins remain disabled in this
selection. These are source/mode choices, not hidden automatic fallbacks.

The fit uses every272 TRAIN parent/hart group from the new1,008-region compute
experiment. Its same-ELF TRAIN objective is31.59% lower than the previous28a0
selection. Across all1,008 regions, median absolute error changes13.20%→10.29%,
p90 changes51.47%→44.13%, and regions within2% change125→124: improvement is not
universal. The192 internal development-validation rows have10.23% median,
35.42%p90 and62.09% maximum absolute error. They are not blind certification.
On the2,592 memory rows, median error changes3.02%→3.15%, with some regressions.

Exact sources, coefficients, actual native replay, comparison families and
unchanged/inherited priors are preserved in the
[fit report](../calibration/compute-fit-7bd5-hybrid-selected-evaluation-v1/report.json),
[runtime binding](../calibration/compute-fit-7bd5-hybrid-binding-v1/runtime-binding.json)
and [same-ELF comparison](../build/hybrid7bd5-vs-selected28-sameELF-compute-v1/report.json).
No benchmark IDs, golden timings, region intercepts or PC-to-runtime lookup
provide the engine's clocks. Unknown physical latencies remain explicit priors.

The byte-identical parent runtime passed32 functional guests, five selected-cost
Zephyr groups, seven actual launcher executions, and four `run.sh` OOT kernel
provider gates: GEMM/conv2d ×one/two compute workers with all three physical harts,
shipped and twin. They check32,768 INT32 +32,768 W8A8 words. This C/pointer-workspace
front door is distinct from the separately demonstrated compiled MLIR operator
objects; neither is whole-model compilation. The selected V4 provider changes
only provenance validation, preserves the parent execution receipts, and adds
an actual12-region smoke through the new descriptor. Review
[runtime readiness](../build/hybrid7bd5-selected-release-v1/readiness.json),
[guard review](../build/hybrid7bd5-reference-guard-release-review-v1/report.json)
and [selection](../build/hybrid7bd5-default-selection-v1/selection.json).

Full Iris/RTL/Zephyr/±2% certification remains false. The recorded FPGA stall
without the periodic watchdog is not reproduced by this model. Private cache
replacement and NoC/coherence are approximations, not exact physical simulation.
Scalar BF16 is illegal in the tested image; column-readout behavior is not
generally emulated. Other documented source divergences remain.
The saved28a0 package and its distinct771-row development results are retained
at `build/empirical-28a0-guard-staging-v2`; different cohorts cannot establish a
comparative accuracy claim. Its full4,050 software replay timed out without
complete numerical readback. The ordinary functional package remains separate.

The hardware facts are recorded in [hardware/manifest.json](../hardware/manifest.json)
and [hardware/dtypes.json](../hardware/dtypes.json). All three harts execute:
harts0/1 are Shuttle, VLEN256/DLEN128, with VME; hart2 is Rocket,
VLEN256/DLEN256, with ordinary integer and IEEE vector arithmetic. Matrix
instructions on hart2 raise illegal-instruction. Effective cache costs and
contention are model approximations, distinct from identified physical DRAM,
NoC or cache latencies.

## Runtime selection

The explicit Merlin hook accepts the new manifest schema only with both:

```sh
export MERLIN_IRIS_MODEL_MANIFEST=$PWD/spike/empirical-current/manifest.json
export MERLIN_IRIS_TIMING=empirical
export MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING=1
```

The fitting publication command is `integration/iris-mlir/configure_empirical_compute_v2.py --help`.
The current provider-only reference hardening uses
`integration/iris-mlir/configure_empirical_reference_guard_v4.py --help`.
It requires a matching native binary/UART pair, fitted parameters, runtime
fixture and binding envelope, actual package selftest, and independently
verified archived source closure. Changed bytes make the selection unavailable.
It also verifies the exact managed reference/cleanup/archive and hashes the
actual bitstream and driver-executable archive members. Archive-bundle and
inner-executable identities are distinct.
The hook returns the launcher and native identities, exact launch arguments, heterogeneous ISA
strings and real Iris memory regions. It reports empirical timing availability
while preserving false whole-model, RTL and ±2% certification flags.
The launcher requires a static, unstripped RV64 little-endian ELF. It checks
defined executable fatal-handler symbols and refuses malformed, ambiguous or
stripped inputs. It automatically terminates on fatal handlers on any hart;
ordinary recoverable traps continue. Its Python interpreter and native bytes are
bound, and it runs with isolated Python settings. Complete Python standard-library
closure is explicitly unverified.

## Running an existing ELF

From the repository root, run an existing baremetal or Zephyr ELF:

```sh
python3 -m iris_model.empirical_run --elf /absolute/program.elf \
  --output build/my-run --timeout 600 --seed 0
```

This selects `spike/empirical-current/manifest.json`; use `--model /absolute/manifest.json`
to choose another published version. The runner keeps all three physical harts
and the descriptor's ISA, memory, boot and timing settings. It saves raw `stdout`,
`stderr`, `features.jsonl`, `native-summary.json` when available, and `run.json` on
success or failure. A wall timeout cleans up only its owned local process group.
`pass` describes a successful guest exit with unchanged inputs; numerical output
validation and FPGA timing qualification remain separate gates.

The short independently checked example uses the existing smoke ELF:

```sh
python3 -m iris_model.empirical_run --elf benchmarks/build/smoke.elf \
  --output build/my-smoke --timeout 120
python3 benchmarks/validate_console.py build/my-smoke/stdout --smoke
python3 -m iris_model.empirical_profile \
  --prefix build/my-smoke/features.jsonl --console build/my-smoke/stdout \
  --elf benchmarks/build/smoke.elf --rom board/evidence/bootrom.rv64.img \
  --fixture calibration/compute-fit-7bd5-hybrid-selected-v1/runtime.fixture \
  --run-receipt build/my-smoke/run.json --output build/my-smoke-profile
```

The fixture path above belongs to the current 28a0 selection. When choosing a
different manifest, use the fixture named by that manifest and the saved argv.
The example verifies 12 regions across three harts and produces JSON and Perfetto
outputs. It has been executed on the current wrapper; see
`build/empirical-ELF-runner-smoke28-guard-v1/run.json` and
`build/empirical-ELF-runner-smoke28-guard-profile-v1/summary.json`.

To exercise the real Merlin kernel front door with this selection:

```sh
export MERLIN_PYTHON=$PWD/build/merlin-venv/bin/python
export MERLIN_CHIPYARD_IRIS=/scratch/eygao/iris-cy
export MERLIN_PROVIDER_BASE_PATH=$PWD/third_party/rvv-mlir
export MERLIN_IRIS_MODEL_MANIFEST=$PWD/spike/empirical-current/manifest.json
export MERLIN_IRIS_TIMING=empirical
export MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING=1
integration/iris-mlir/examples/iris/run.sh op gemm --harts 2 --model-root "$PWD" \
  --compiler /scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc \
  --output build/my-merlin-gemm --timeout 600
```

Use the existing Python3.12 Merlin environment; system Python3.9 cannot parse the
upstream compiler. `--harts 1|2` chooses compute workers while retaining all three
physical harts. `op conv2d` exercises the declared convolution fixture.

The Merlin example writes separate `shipped.features.jsonl` and
`twin.features.jsonl` streams in its fresh output directory when empirical mode
is selected. Its `results.json` binds each profile to that variant's exact ELF,
fixture, output and native invocation. Pass this receipt and `--case-id` to the
profiler for an execution-bound JSON/Perfetto result.

No benchmark IDs, golden cycle counts, region intercepts or PC-to-runtime lookup
tables are used by the engine. PCs serve instruction/cache/branch semantics.
The guest reads the model's actual counters while running; region results are
not rescaled after execution.

## Package checks

Build the independent timing guest into a fresh directory:

```sh
python3 timing/build_empirical_time_guest.py --output build/time-check-new
python3 spike/check_empirical_package.py \
  --native /absolute/frozen/spike --uart /absolute/frozen/libsifive_uart.so \
  --fixture /absolute/fitted.fixture \
  --sensitivity-fixture /absolute/perturbed.fixture \
  --time-guest build/time-check-new/guest.elf --output build/package-check-new
```

The check runs12 scalar smoke regions on three harts with independently checked
checksums. A second guest executes32 RVV additions on every hart and checks all
24 output words against35. The selected and perturbed cost fixtures must retain
the same region instruction counts and correct values while changing the
program-returned cycle deltas on all three harts. Raw streams, commands,
counter values, elapsed host time and input hashes are retained. This proves
timing wiring and numerical mechanics, not FPGA accuracy.

## Bounded profiling

Set `IRIS_EMPIRICAL_FEATURES=/absolute/fresh/features.jsonl` for the native
process. Add `--iris-timing-trace=/absolute/fresh/native-summary.json` to retain
the bounded native aggregate. Use fresh output paths for each invocation.
Capture guest stdout separately, then join `IRIS_REGION` records to their
actually returned CSR values:

```sh
python3 -m iris_model.empirical_profile \
  --prefix /absolute/features.jsonl --console /absolute/guest.stdout \
  --elf /absolute/workload.elf --rom board/evidence/bootrom.rv64.img \
  --fixture /absolute/fitted.fixture --run-receipt /absolute/prediction.json \
  --output build/profile-new
```

The output contains `summary.json` and a Perfetto-compatible `trace.json`.
For the baremetal Merlin example's `REGION hart start end instret` format,
also pass `--case-id gemm` (or the actual workload name). Numerical output
validation remains a separate required gate; the profiler does not infer it.
The run receipt must bind the exact ELF, fixture, guest stdout and prefix stream.
Omitting it permits forensic observation joins with `execution_identity_verified`
false; it does not establish which complete executable produced the stream.
Its global timeline uses fixture base-clock cycles. Guest mcycle values can
have different origins, write/inhibit behavior and WFI gating, so they are
reported separately. Missing or ambiguous captured boundaries fail closed.
PC/instruction metadata is checked against the exact ELF/ROM, with symbols
attributing the two measurement boundaries. Detailed function work attribution
requires the optional full graph.

Resource busy fractions use differences of cumulative **union occupancy**,
including elapsed portions of in-flight operations at each boundary. Shared
resources include work from all harts in the region's time window; they are
not attributed exclusively to its issuing hart. `completed_service_cycles_sum`
contains completed operation durations, which overlap and can extend beyond
region boundaries; it is never treated as utilization or additive stall time.
When supplied by the engine, each region also records whether a compute actor
still owned unpublished results at its two boundaries. A retired vector/matrix
instruction can have backend work outside the mcycle window. Use a real data
dependency when the program intends to measure result completion.

Instruction/work/MAC features describe architectural retirement. Memory
features describe accepted timing intents and cache probes in the approximation.
Neither is a measured physical completion counter. Unsupported stall breakdowns,
physical per-level completed traffic, validated peaks and rooflines remain
unavailable. Do not present these experimental model occupancies as FPGA
instrumentation; Ethan's image has no TracerV/AutoCounter/SynthPrint capture.

## Fitting and held-out validation

The6750 independently checked fitting regions are in
`build/fpga-fit-observations-v1/regions.csv`, with exact archived-run provenance.
The initial `calibration/empirical-v1` regressions used region feature proxies;
their cross-validation scores are not live simulator accuracy. Current work
refits and validates using actual online features and modeled CSR results.
Internal validation is development data; final held-out timings remain separate.

`zephyr/heldout_batch_predict.py` freezes model/runtime inputs and predictions
before reference timing is opened. `firesim/prepare_heldout_batch.py` prepares
the frozen three-hart Zephyr GEMM/conv2d workload, including one/two compute
harts, shipped/twin kernels, hart2 producer/refusal, repeated full-value checks,
and separate CLINT elapsed windows. The managed run always uses
kill → infrasetup → runworkload → kill under complete occupancy/ownership checks
and the shared lock. Archive validation and signed per-region/end-to-end
comparison follow owned cleanup. Failed rows and prior hardware divergences
remain visible, even if the new workload passes.

## Faster calibration replay

`timing/cpu_layout_readback.py` runs the unchanged CPU-layout ELF using Spike's
existing debugger. After every main measurement has completed, it reads the
known numeric records and intentionally stops before bulk UART output. The823
qualification compares4,613 complete prefix records with the normal replay:
all timing, feature and resource snapshots are identical. All2,304 main
numeric/counter/actual-ELF-PC records pass in10.19hostseconds. This is a
post-measurement stop, not normal guest completion, end-to-end timing or
simulation-MIPS certification. Raw partial trailing prefix bytes are preserved
and counted; they are never silently accepted as complete observations.

The new buffered fitting workload is built with
`benchmarks/campaign_buffered/build.py`. Its736 semantic parent cases and three
repetitions produce4,050 regions across all three harts. Parent kernel source
and measured-window source are preserved, while layout, memory record stores
and console history differ. It therefore requires a **new exact-ELF FPGA
reference**; previous campaign timings cannot be reused. Two complete local
functional schedules and14 corrupted-output controls qualify the current ELF.
`benchmarks/campaign_buffered/replay_v2.py` uses a verified file-backed known
sentinel, reads the completed64-byte records and joins every cycle boundary to
its actual ELF CSR instruction. It supersedes the preserved original reader's
incorrect rejection of an initial sequence zero. Incomplete required final
prefix records still refuse qualification. The reordered priority-v2 ELF uses
its own `replay_priority_checkpoint.py` and exact FPGA reference at
`runs/fpga-buffered-priority-v2-001`; all4,050 hardware regions pass. Its first
1,989 cases provide a3,633-region partial calibration replay; an intentional
debugger stop does not establish normal guest exit or full-run accuracy.
Final Zephyr v6 remains a separate held-out reference, excluded from fitting.

Bounded profiles also report architectural instruction/MAC retirement rates and
accepted memory-intent byte rates per elapsed model cycle. They use global
modeled time, so software-written or inhibited mcycle does not distort the
denominator. These rates do not imply physical backend completion, measured
DRAM bandwidth, validated peak efficiency or a calibrated roofline. Eight
execution-bound Merlin examples are under
`build/empirical-first-release-v3-profiles-v3/report.json`; these reprocess the
same eight recorded executions and do not claim additional guest runs.

Instruction-fetch observations preserve the reported owner and its explicit
scope when present. Older prefix records omit scope, and a null owner cannot
establish that all frontend work is drained. In particular, source Shuttle
frontend901 does not project its refill owner into the legacy pending-fetch
field. Such boundaries have unknown coverage; they must not be filtered or
certified as empty carry-in based on that null alone.
