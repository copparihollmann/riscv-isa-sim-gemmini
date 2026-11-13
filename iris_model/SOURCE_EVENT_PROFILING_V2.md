# Source journal profiling v2

This additive consumer accounts for checked architectural COM owners and their
actual modeled source-write events. It supports the frozen 35a integer VADD
journal, the existing per-EG FADD journal and the new authoritative OPU MM
COM/entry/K journal. It changes no native, fixture, provider, default selection,
or model policy. The v1 frontend and consumer remain unchanged.

The completed demonstration is
[`build/source-profile-35a-fullASM-v7`](../build/source-profile-35a-fullASM-v7):

* `summary.json`: whole captured program, per-function and 1,320 explicit ROI
  summaries, source-capacity conditions, busy/age qualifications and digests;
* `commands.jsonl`: every checked COM owner and its completed work;
* `trace.json`: command-level Perfetto timelines, source pipe-valid unions,
  sampled OPU controller busy intervals and actual CSR region boundaries.

Open `trace.json` in Perfetto. The large raw journal stays hash-bound and retains
individual microissue/write records; the Perfetto export aggregates them by
command to keep a full-program view practical.

## Existing byte-bound journal

This reproduces the model-only full ASM demonstration into a fresh directory:

```bash
python3 -m iris_model.source_event_profile_v2 \
  --events build/rvv-compute-asm-C12-VADD-EG-ON-v1/async.jsonl \
  --features build/rvv-compute-asm-C12-VADD-EG-ON-v1/features.jsonl \
  --console build/rvv-compute-asm-C12-VADD-EG-ON-v1/stdout \
  --elf build/rvv-compute-asm-v5/guest.elf \
  --rom board/evidence/bootrom.rv64.img \
  --fixture build/C12-VADD-EG-inputs-v2/ON.fixture \
  --execution-receipt build/rvv-compute-asm-C12-VADD-EG-ON-v1/run.json \
  --region-map build/source-profile-35a-fullASM-inputs-v2/regions.json \
  --region-format none \
  --nm /scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm \
  --output build/CHOOSE_NEW_SOURCE_PROFILE_OUTPUT
```

The execution receipt must bind the exact journal, feature prefixes, console,
ELF and supplied fixture. A native summary provides model clock and end-cycle
metadata when normal execution produced one. For the deliberate postmeasurement
debugger stop above, the explicit fixture supplies the clock; the report gives
an observed journal horizon and leaves whole-program completion unknown.

This run checked 184,128 output words and 3,960 actual CSR/ELF endpoints. The
profile accounts for 78,720 VADD COM owners, 585,600 integer EG writes and
4,358,400 completed add elements; 57,600 FADD owners, 432,000 FP EG writes and
2,016,000 add elements; and 7,728 OPU MM owners, 57,792 entry/K completions,
14,794,752 logical MACs and 19,392 final per-entry MRF projections.

The source journal has a preserved 156-byte final FADD-fence metadata fragment.
It receives no credit. All present authoritative VADD/FADD/OPU owner/write joins
are complete, but the global transcript is not complete and this debugger run
does not prove normal guest termination. A partial owner/publication event, a
missing write or an unclosed front reservation is refused.

## New execution through an existing guarded model

```bash
python3 -m iris_model.source_profile_run_v2 \
  --model <explicit-existing-guarded-model-manifest.json> \
  --elf <unstripped-program.elf> \
  --output <fresh-output-directory> \
  --timeout 600
```

This delegates execution to unchanged `source_profile_run_v1.run`: descriptor
validation, fatal-aware launch, all three hart ISAs/devices, fixture arguments,
timeouts, owned cleanup and byte closure remain its responsibility. The v1
execution and observer receipt are preserved under `execution-v1`. The new
consumer writes `source-profile-v2`; a requested v2 profile failure makes the
new CLI fail. The frontend does not manufacture a provider or bypass a model
that is unavailable. Successful process exit is separate from independent
numeric validation and timing accuracy.

A model must actually enable and emit the supported source journals. The old
02b4 OPU journal lacks authoritative MM COM geometry and cannot provide v2 MAC
accounting; its historical v1 reports remain valid in their stated scope.
The new frontend was exercised on the existing guarded 02b4 FADD smoke ELF:
all 136 words and three explicit regions pass, and stdout, counters, summary
and source-journal bytes exactly match the frozen v1 execution. Fatal-handler,
changed-model and owned-timeout refusals remain active.

## Meaning of the reported work and clocks

Only complete checked-COM owners receive work credit. A front reservation,
canceled/wrongpath owner, planned microissue or missing write contributes no
completed work. VADD publishes 16 bytes one qualified source edge after issue;
FADD publishes 16 bytes after four. Integer adds, floating adds and MACs remain
separate units. A MAC is one MAC; the optional two-arithmetic-operations/MAC
convention is not an extra work credit.

Every OPU `(entry,K)` microgroup must join its source reservation, guarded write
callback and completion record. Its shape, opcode, tile, signedness/formats and
MAC count must agree with actual MM COM. Only the final K may project the final
MRF entry. Intermediate K numerical MRF values are not separately materialized
by this finite actor; the report counts source-controller MAC completions and
checks the final MRF publication. Generic TMOVE has no authoritative new COM
journal and receives no inferred work.

ROI endpoints come from explicit guest markers or a supplied region map, joined
to unique, returning, typed mcycle observations whose PC/raw/destination match
the actual ELF. Rates use their global model observation edges. Program mcycle
deltas are retained separately and are never converted into a linear clock
projection. Each ROI states carry-in work, commands started there and whether
their final writes occurred before its end. There are no guessed counter pairs.

The exact source capacity report
[`throughput-limits-source-v3/report.json`](../build/throughput-limits-source-v3/report.json)
is SHA-bound. Fractions compare modeled completed work/core-edge with a
conditional selected-format source ceiling under its listed assumptions. For
OPU this is up to 256 active cell MACs per accepted array edge, with at most one
selected microgroup accepted per core edge. Shape, operands, dependencies,
queues and frontend/setup/drain can lower an application's rate. Shared and
alternate-format peaks are not summed. A fraction above one is retained and
flagged as an inconsistency, never clamped.

Three time descriptions stay separate:

* VADD/FADD completed source pipe-valid unions follow the qualified one/four
  pipeline stages;
* sampled OPU preedge VDQ/IQ/sequencer busy excludes unobserved numeric-pipe
  occupancy and separate FP8 tails;
* front-to-final-write owner age includes CPU, queue and tail bookkeeping.

These are source-model observations. Physical FPGA utilization, switching,
DRAM/L2/TL bytes, bandwidth and physical rooflines remain unavailable/null.
Different INT8/FP8 fractions in one modeled program do not show that hardware
FP8 is intrinsically faster. CPU COM+1 joins, active-vector IRQ/context behavior,
source-to-image association and timing accuracy retain the native's existing
limitations.

The final consumer controls are
`timing/test_source_event_profile_v2_controls_v7.py`; they include actual-owner
missing/duplicate/cancel/wrong-K/geometry/publication/domain corruption tests,
actual CSR joins, clock conflicts and unclamped fractions above one. The real
frontend checks are `spike/check_source_profile_run_v2_controls_v4.py`.
