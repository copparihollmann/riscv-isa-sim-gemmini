# Saturn source activity profiles

`iris_model.saturn_profile_cli` turns the frozen, qualified Saturn activity
projection into `summary.json` and a Perfetto/Chrome `timeline.json`. The
projection was compared against independent whole-RTL captures with all three
harts and three reset seeds. Its producer capsule is
`build/saturn-timing-activity-component-v1-final/report.json`, SHA256
`dacc122ab6c4011eca188d538173b983992e86cfbd4a5ededef72fe207a494b0`.
See [the activity contract](saturn_timing_activity_README.md) for source signal
definitions and the producer's qualification limits.

Generate a profile in a new directory, without contacting the FPGA:

```sh
python3 -m iris_model.saturn_profile_cli \
  --component build/saturn-timing-activity-component-v1-final \
  --component-sha256 dacc122ab6c4011eca188d538173b983992e86cfbd4a5ededef72fe207a494b0 \
  --case vme --output build/my-vme-profile
```

Other available cases are `rvv`, `fpcomp` and `shared-fpu`. Existing demonstrated
outputs are `build/saturn-source-profile-{vme,rvv,fpcomp,shared-fpu}-v3`.
Each run records its exact input hashes, retains both Python consumer sources,
and checks the capsule receipt, artifact hashes/modes/sizes, actual reference
completion, all three reset-seed qualifications, projection/contract binding and
complete stream consumption. Changed or missing evidence refuses profiling.

Open `timeline.json` in Perfetto's trace viewer. Each hart has distinct tracks
for backend activity, vector pipes, VME activity, reset scrub, selected queue
occupancies and accepted/completed work. Unknown intervals are visible gaps in
qualification; their placeholder zero is never treated as idle or completed
work. Overlapping busy tracks are not added together.

The source TestDriver period is derived from the exact compiled reference and
its counter implementation. These captures use a 1 ns TestDriver period and
2 ns source core edges. Neither coordinate is silently substituted for `mcycle`:
source CPU counters can hold during WFI. The FPGA's emulation frequency is also
separate. The summary explicitly records that no `mcycle` projection is inferred.

States observed before edge E describe the preceding source interval. Accepted
work and completion commit at E. There is no interval before the first sample.
For a cropped region, state intervals are clipped and commit events use
`[start_tb, end_tb)`. A completion inside a region can belong to work accepted
before it; acceptance and completion therefore need not balance within a region.

Optional `--regions regions.json` accepts a JSON list such as:

```json
[
  {
    "id": "explicit-source-window",
    "hart": 0,
    "start_tb": 31273,
    "end_tb": 201647,
    "source": "Explicit source-observation window; not a guest mcycle region"
  }
]
```

The demonstrated shared VME activity span is in
`build/saturn-source-profile-demo-v1/regions.json`, with its derivation script and
input/output hashes. It selects actual qualified source activity boundaries and
extends the final commit to the next captured source edge, without inventing a
cycle. Output is in `build/saturn-source-profile-vme-region-v1`. This diagnostic
span includes scalar validation and communication; it is not a kernel-only
performance measurement.

The VME source guest independently requires 4,216 INT8 MACs and 16,864 FP8 MACs
on each compute hart. The profile preserves those accepted and completed totals.
It reports 929/930 VME busy intervals for harts 0/1, while the backend source flag
reports 1,090/1,146; these are different source predicates. Hart 2 has no VME
work. Reset scrub is 64 edges on each compute hart and 32 on Rocket.

The compute array's conditional physical ceiling is 256 MACs per source edge.
`counts.*.per_known_source_edge` supplies achieved acceptance or completion rate;
the conditional ceiling is separately recorded. It is not a sustained throughput
promise: FP8 same-entry issue spacing and operands constrain it. Vector per-dtype
peaks remain unavailable until their functional-unit mapping is qualified.

This interface does not infer numeric data knownness from control knownness.
External memory bytes, per-function ownership, CPU utilization, additive stall
breakdowns and rooflines remain unavailable in this projection. Internal VRF
write bits and VMU requests are not external traffic bytes. Causal ownership and
the external protocol ledger must be supplied before those metrics are emitted.
These profiles are component evidence, not a full-model or FPGA ±2% certificate.
Reported decoder frames per second measure profiling only, not simulation MIPS.

## Physical events in the live graph

The ordinary graph profiler also accepts source events that occur at a single
physical edge. A producer declares `physical_acceptance: true`, its
`physical_source`, and explicit `pc_known`. Unknown ownership must use
`pc_known: false` and PC zero; it remains unattributed even if the ELF has a
symbol at zero. Guessing a nearby instruction is not supported.

A same-edge completion additionally declares `physical_edge: true`,
`completion_policy: "same-source-edge"` and `completed: true`, with
`submitted == start == end`. It contributes work and a Perfetto instant without
an invented occupied cycle. A source request with a matching later response
uses `completion_policy: "matching-source-response"`; it remains incomplete
until that actual response. At a partial graph's current boundary, a newly
accepted request can have zero elapsed duration without implying completion.
Completed intervals must have positive elapsed duration. Source actors cannot
be retrospectively canceled. Region point accounting is `[lower, upper)`.

The source CPU/cache demonstration at `build/rocket-fabric-load-profile-v1`
already uses this interface. Its external service remains an explicit synthetic
fixture, so the result demonstrates graph/profile integration rather than
hardware timing calibration.
# Exact function ownership and source memory lifetimes

The qualified ownership capsule supports a second profile that uses the actual
physical command PC and complete instruction word. Every attributed instruction
is checked against the bound executable ELF; static symbol bounds supply the
function name. Later commands and reused VAT slots do not change an earlier
command's owner. The producer's `caller_node` is opaque synthetic EX metadata
and is never used as a native CPU graph identifier.

```sh
python3 -m iris_model.saturn_owned_profile_cli \
  --component build/saturn-timing-ownership-component-v1-final \
  --sha256 05b079b646a4a13723409d50879d9f4d923f543d5a6bf7aba28c4e640fa79b6f \
  --case vme --output build/saturn-owned-functions-NEW \
  --nm /scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm
```

Other cases are `rvv`, `fpcomp` and `shared-fpu`. The CLI verifies the pinned
capsule and dependency inventories, complete three-seed replay/corruption proof,
ELF bytes, source timebase and full event counts. Those four actual source
captures contain 188,364 observations and 6,030 matched physical TL transactions.
The VME case attributes compute work to `benchmark_main`, tile clearing to
`zeros`, and most stores to `readrow`, preserving separate physical-kind counts.
These are the standalone saved-Iris RTL captures, rather than Ethan-image data
or a live native CPU graph.

`summary.json` reports per-hart/function physical event counts, kind-specific
source amounts, register write-enable bits and declared transaction bytes.
Counts at successive stages describe the same work and must not be added into
retired instructions, application bytes or MAC totals. Reset scrub stays
unattributed. Raw data/write masks do not establish numeric initializedness.

`timeline.json` contains aggregated zero-duration physical source points and
actual accepted-A-to-final-D transaction spans. Each span retains command,
hart, transport source, address, declared size and both TB/source-edge elapsed
coordinates. Its duration includes downstream delays and does not isolate DRAM
latency or contention. Overlapping spans are not additive CPU stalls. No unit
occupancy, retirement counts, missing per-level traffic or roofline is inferred.

Seven ownership-attribution tests cover late work after another command,
instruction/generation corruption, omitted acceptance, packet mismatches,
source counts/order and reset scrub. The full root profiler suite currently
passes 162 tests. The four demonstrated profiles and exact source/ELF inputs
are archived in the owned-profile demonstration closure.

