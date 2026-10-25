# Annotated Spike

This fork observes executed RV64 scalar instructions and an optional accelerator
provider without changing architectural execution or the guest cycle counter.
Estimated target cycles are a separate JSON result. It is an approximate event
model; a successful build or a functional simulation does not qualify its timing.

## Build

Dependencies: Python 3.10+, a C++20 compiler, make, Boost system/regex, device-tree
compiler and OpenSSL development headers/libraries. Build outside this source
checkout:

```sh
python3 timing/build.py --build-dir /path/to/build --jobs 2
python3 timing/tests/run_native.py --build-dir /path/to/build
```

The source bundle includes the canonical small `merlin-timing` C++ export with its
manifest. Neither building nor running requires an installed Merlin, xDSL,
Chipyard, a compiler implementation or any benchmark data. The build records a
source manifest and embeds its digest into the feature engine. A direct build
without that identity cannot produce qualified observations.

Linux x86_64 is exercised locally. ARM64 Linux and macOS use the same source
interfaces and require their native dependency packages; set include/link search
paths for a nondefault OpenSSL installation. Windows requires WSL. Those platforms
must run the native tests before accepting a deployment.

## Run

```sh
/path/to/build/spike --isa=rv64gc_zicntr_zihpm --priv=m -m64 \
  --timing-model=/path/to/model.json \
  --timing-report=/path/to/report.json \
  --timing-input-sha256=INPUT_DIGEST /path/to/program.elf
```

A target timing provider is a separate shared library loaded with `--extlib`,
alongside the unchanged functional extension. Its source export supplies only
hardware semantics and event observation. Target scheduling/compiler code is not
loaded. Every loaded library digest, **in load order**, must match `libraries` in
the selected model. The Gemmini provider and pinned U250 facts live in this
simulator repository under `examples/gemmini/timing`. The unannotated Phase 1
baseline packaging is alongside it in `examples/gemmini/functional_baseline`.
Generic source packaging, provider builds and calibration live in Merlin's
standalone `merlin-timing` package. The target exporter calls that shared package;
exported bundles build independently using its canonical standard-library helper.
Neither route depends on the OOT compiler repository. Phase 1 produces that
compiler independently; simulator sources and selfchecks are operator inputs.

The model schema is `merlin.annotated_spike_model.v1`. It contains:

- `profile`: `phase1-public` or `historical-private`;
- `domain`: device, source-engine, feature-schema, memory-regime, scope and measured
  label-engine digests; the runtime adds the actual model-file byte digest;
- `cpu.isa`: the expanded ISA spelling reported by this pinned Spike parser;
- `scope`: `whole_program`, or `counter_pair` with a zero-based `index`;
- `scope.kind=counter_pc_pair`: use an explicit per-execution
  `--timing-scope-binding=FILE` instead of consecutive counter reads;
- `resources`: explicit IDs, names, capacities and queue capacities;
- `parameters`: explicit nonnegative prices; missing prices remain unknown;
- `cpu_execution_resources`: instruction-class to execution-resource mapping;
- `memory`: cache geometry, hierarchy paths, coherence granule and explicit
  coherence policy; and optional target-provider data in `target`.

`timing/tests/run_native.py` constructs a synthetic test configuration, including
required key spellings. **Its prices and zero provenance digests are test data,
not a hardware model or an admitted calibration profile.** Stock target exports
retain unknown queue sizes and prices rather than filling them with guesses.

## Semantics and limits

An explicit `cpu.fp_operand_timing` selection with schema
`merlin.rocket_divsqrt_operand_timing.v1` distinguishes scalar S/D division and
square-root special inputs from the normal class. The observer reads the actual
pre-instruction NaN-boxed operands and applies the selected HardFloat
`normalCase` test: zero/NaN/infinity, or a negative square-root input. Positive
subnormals remain normal. Special events retain their ordinary dependency,
execution resource and FP-state effects, and require separate
`cpu.fp_{divide,sqrt}.f{32,64}.special.{latency,occupancy}_cycles` prices. Missing
prices remain unknown. Counter-dependent class selection refuses. Without the
protocol, operands are not classified and legacy pricing/count fields remain
unchanged. This classification supplies no latency calibration or hardware
qualification; the model must separately justify its selected prices.

An explicitly selected cache may declare `byte_service` with schema
`merlin.cache_boundary_byte_service.v1` and a named resource, plus the positive
price `memory.<cache>.per_byte_cycles`. Each architectural event charges the
union of the exact byte intervals that reach that cache, on hits and misses.
The selected resource receives the corresponding occupancy; a parent-cache hit
does not reach a lower boundary. Missing protocol, resource or price refuses.
Absent selection preserves legacy behavior. This adds boundary byte service,
not MSHR, DDR bank/rank, replacement-policy or physical timing qualification.

The model tracks RAW/WAR/WAW dependencies, resource occupancy, bounded waiting
queues, cache tags, pending fills/writebacks, shared-memory dependencies and
accelerator-local dependencies supplied by its provider. Resource busy time is
not an additive breakdown of elapsed cycles. Local row dependencies and a shared
memory service are conservative approximations that require independent timing
qualification.

Only single-hart, machine-mode RV64 I/M/A/F/D/C plus CSR/fence/counter extensions
are admitted. Scalar floating register operations, rounding state and sticky
exception flags have explicit dependencies. Other ISA extensions, handled traps,
interrupt/debug transitions and unsupported maintenance operations remain
unqualified. Actual mapped RAM and immutable ROM are distinguished from MMIO;
ROM accesses require their own explicit price. HTIF mailboxes are external I/O
even though mapped in RAM; their polling is excluded from qualified timing.
Counter windows must close before logging or exit traffic. Devices are not silently priced
as cacheable memory. Device transfers currently require stable RAM.

The implemented cache timing policy is write-back/write-allocate with LRU tags.
The optional coherent transfer policy is explicitly `writeback_invalidate`; it
is a model policy, not a claim to simulate a coherence protocol. Instruction
fences require a private instruction cache; unsupported unified-cache maintenance
remains unknown.

Counter pairs use consecutive architectural cycle reads. Feature deltas cover
instructions after the opening observation through the closing observation.
The selected window freezes timing eligibility at its closing boundary; later
logging does not alter that window. `instructions` and `cycle_breakdown` describe
the whole executed trace; selected `feature_counts` and `estimated_cycles`
describe the selected scope. Counter-derived control, addresses, accelerator
operands or unmodeled architectural state inside/before the selected scope
refuse timing and count portability. Ordinary counter-value spills propagate
sparse byte taint through actual loads/stores; partial overwrites retain the
remaining taint. A counter spill alone is not a refusal. Device input reads
must be independent of those counter values.

Fresh reports use `merlin.annotated_spike_report.v2`. The independent
`feature_observation` contract (`merlin.spike_feature_observation.v1`) records
count completeness, exact scope, primary instruction vocabulary and coverage,
and unresolved count semantics. Complete counts do not imply complete native
timing, hardware qualification or independent output equivalence. Missing
prices/resources can leave counts usable while native cycles remain unknown.
Target providers may export `spike_timing_provider_feature_observation_v1`
without changing the original provider ABI. Missing provider status refuses
count completeness; it cannot silently clear unknown semantics.

Configured scalar Zba/Zbb/Zbs instructions require exact simulator-defined
encodings and actual register dependencies. They have a separate bit-manipulation
price class. Enabled but unused Zfh does not invalidate an otherwise supported
trace; executed half-precision forms still refuse. Other integer-extension
encodings sharing a major opcode remain unknown.
The model never substitutes estimated cycles into the guest counter.

For a capsule kernel-call label, an internal counter read must not become a
boundary. `counter_pc_pair` requires a bounded JSON binding with schema
`merlin.spike_scope_binding.v1`, exact `elf_sha256`, `input_sha256` and
`scope_sha256`, distinct aligned numeric `begin_pc`/`end_pc`, zero-based
`occurrence`, and `evidence_sha256` identifying the independent boundary review.
Only matching executed counter instructions delimit its windows. The report
records the binding and its original file digest. Missing or unmatched boundaries
refuse timing. Bindings supply addresses, never prices; keeping them outside the
model lets different linked ELFs share one frozen pricing-model identity.
The importer must independently verify that these PCs bracket the declared
kernel entry through completion wait; the observer cannot infer clock semantics
or hardware scope from the `rdcycle` mnemonic.

Software budgets bound scoreboard values, cache entries, address dependencies,
features, diagnostics, transfer work and counter windows. Only the selected
window retains feature/reason snapshots. Capacity exhaustion is reported as
unknown or rejected, never truncated into an optimistic estimate.

## Qualification

Native reports deliberately say `engine_qualification: not_established`.
Use the standalone `merlin-timing` validation tool to qualify original native
predictions against independent, same-scope measured records after freezing the
model. An empirical instruction-count regression cannot qualify this engine.

Public calibration admits only public Phase 1 sources and independent RTL labels.
Historical private records are a separate operator-only profile. All variants and
repeats of a source group stay in the same train/calibration/test split. Do not
fit on held-out models or copy private coefficients into a public profile.

Required held-out gates: at least 90% ordering agreement for measured candidate
separations above 5%, median relative cycle error at most 15%, p95 at most 30%,
at least 20 eligible pairs across three mechanism families and at least 80%
declared-case coverage. Residual intervals additionally need independent
calibration groups. Until those gates pass, estimates are diagnostic; uncertain
comparisons require RTL measurement.

### Optional serialized private-cache probe service

A cache may select `coherence_probe_service` with schema
`merlin.private_cache_probe_service.v1`, a capacity-one `resource`, `beat_bytes`,
and bounded source-derived `lookup_cycles`, `dirty_enter_cycles`,
`data_pipeline_cycles`, and `metadata_cycles`. It applies only to actual private
cache hits invalidated by the existing selected device-coherence policy.
A clean response occupies lookup + one acknowledgement beat + metadata;
a dirty response additionally enters the dirty state and pipelines line data,
then transfers line_bytes/beat_bytes beats. Repeated touches do not charge an
already invalidated line again. Each private controller has its own resource;
this does not serialize independent global A/C/D channels or infer DRAM rates.

The sum of occupied cycles on each controller is an independent protocol floor
on the architectural memory event. It is max-composed with existing scalar
cache/snoop costs, not added twice. Existing unknown prices remain unknown.
The feature `modeled.cache.<name>.coherence_protocol_cycles` describes modeled
whole-trace protocol work, not measured kernel stalls.

This is a no-backpressure approximation requiring independently pinned source
facts. CPU/cache arbitration, first-row arrival, per-line downstream scheduling,
coherence retries and additional backpressure are not reconstructed by this
floor. Selecting it cannot qualify the whole-SoC estimator.

### Provisional Rocket integer-divider bound

`cpu.integer_divider_service` may explicitly select
`merlin.rocket_integer_divider_service_bound.v1`, with `xlen: 64`,
`div_unroll: 1`, `early_out: true`, `early_out_granularity: 1`,
`response_ready: "assumed_immediate"`, and SHA256 pins `rtl_sha256` and
`source_sha256`. The selector must be reviewed against the elaborated module;
the parser validates identity format and configuration, not external RTL content.

For DIV/DIVU/REM/REMU and their word forms, this uses a conservative 67-cycle
module service bound: 65 restoring-divider states (count 0 through 64), at most
one input-sign state and one output-sign state. One additional done-state cycle
reserves the single shared MulDiv unit until ready, assuming immediate response
acceptance. Word operations still traverse this 64-bit divider. Early-out is
ignored conservatively. No existing price, queue, dependency or functional
instruction semantics changes. Explicit divide prices and this bound cannot
coexist. Unselected profiles keep missing divider timing UNKNOWN.

The report labels this a **provisional component service bound**. It is neither a
calibrated latency prediction nor a whole-SoC upper bound: core writeback,
arbitration and response backpressure remain outside this bound. Independent
public gSIM validation should compare dependent quotient/remainder chains with
worst-case signed and early-out unsigned operands, then a multiply immediately
following division to expose shared-unit release. Do not fit private labels.

### Optional committed context and scoped accounting

Optional V1 context/suffix callbacks preserve the base provider ABI. Context binds
actual committed PC, encoding, instruction length, next PC and immutable primary
ELF digest. A bounded host-only suffix lookup never fetches through guest memory
or advances guest state. Every promised suffix must subsequently match actual
commits through its closing barrier; aborts, different encodings, interrupted
sequences and incomplete report boundaries invalidate that proof. This is source
context, not an independent grant to shorten any target service.

`diagnostics.stop_after_selected_scope.enabled` may stop heavy timing accounting
after the complete originally selected counter window. Functional execution, full
console, instruction/trap counts and guest exit still finish normally. Whole-trace
timing remains unavailable rather than extrapolated from scoped resource counts.

### Optional source-memory identity transport

V1/V2 memory query callbacks reopen the exact last ordinary device observation
without warming a cache, repeating transfer observation or issuing another timing
event. Cache slot/fill generation, reader-return source and native MSHR source
remain distinct identities. V2 lookup metadata uses a distinct output struct and
install symbol; the V1 struct/installation remains available unchanged. Scalar
completion is not a first beat, line-fill visibility or RR admission proof.

Finite source ownership and ready-response arbitration are experimental building
blocks. They require actual closed input frontiers, all shared scheduler actions,
source leases and per-beat availability. The optional resident-epoch guard rejects
future CPU/device shared arrivals before a claimed final response and incomplete
closing fences. No default model enables a new response scheduler or obtains
qualification from this transport. Joint posted CPU/DMA event composition remains
necessary for the general case.

### Experimental posted-stage composition

The mirrored core `PostedTimeline` and `PostedEngineStage` commit effects only
at actual stage dispatch. A pure readiness query cannot reserve a future bank
or change accounting. Pending completion tokens keep future source results
separate from command admission. Each source adapter must supply closed external
arrival frontiers, pending row ownership and actual stage/queue laws; stable
callback order supplies no hardware arbitration grant.

`PostedAggregateMemory::post_accepted` is an actual native MemorySystem consumer.
It defers the one ordinary cache/coherence classification until the caller-proved
accepted request event, so intervening CPU/device arrivals are visible. It then
posts owned Engine work and a completion token. The inherited scalar service
provides only an aggregate completion bound, not a first response beat, source
MSHR allocation, per-row visibility or closed RR proof.

No observer or default provider is switched to this route. Full source-service
command actors, pending read/write generations, CPU acceptance/backpressure and
finite response dispatch remain integration work. The component tests establish
causal event composition, not new end-to-end timing accuracy or physical labels.
Compact per-role summaries count model callbacks (including retries), pending
and token-blocked callbacks, dependency-release delay, unresolved tokens and
peak depth; they are not unique stall attribution or capsule progress.

Focused no-simulation check: `python timing/tests/run_memory_milestones.py
--build-dir <task>/.tmp/memory-check [--boost-include <include>]`.

### Optional source-owned device read pipeline

`memory.device_read_pipeline` is an explicit inactive source-law selection,
not a fitted price or a default. Schema `merlin.source_device_read_pipeline.v1`
requires `enabled:1`, the single `device` path's `cache`, positive bounded
`directory_stages`, `mshr_plan_stages`, `source_d_stages`,
`scalar_lookup_cycles`, and `source_receipt_sha256`. The unchanged cache hit
AND miss prices must equal that declared scalar lookup component. A separately
priced byte-service cache is refused by this law.

The native cache owner replaces that scalar component at the original lookup,
before dependent DRAM recursion and the existing private-probe/response `max`
joins. It applies to device reads only, excluding coherence writeback subrequests.
It does not add its stage count to a final composite `SharedEffects` duration.
CPU requests and device writes retain their original path. Features
`modeled.cache.<cache>.source_read_pipeline_{applied,extension_cycles}` expose
coverage of this replacement without claiming measured utilization.

For the selected public source, Directory1 + registered MSHR plan1 + SourceD2
means four cycles including scalar lookup1. Request/return buffers are owned by
the target transport separately. SourceD throughput, cache miss first/last-beat
readiness, finite MSHR arbitration, and coherence completion still require their
own source laws; this component does not establish a complete memory scheduler
or timing accuracy. See `timing/tests/run_device_read_pipeline.py` for bounded
synthetic cold/hit, coherent-max, unchanged-path and refusal checks.
# Typed write transaction side channel

`write_transaction.hpp` is an optional versioned service, installed separately
from the unchanged v1 `Services` ABI. A transaction's byte coverage and mask
are not its useful modified-byte interval. The first implementation accepts
one contiguous16-byte client beat, classifies only useful memory intervals,
and refuses unsupported cache ownership before altering cache/taint state.
`memory.device_write_request_pipeline` explicitly selects source-owned
Directory/MSHR readiness; it excludes SourceD ACK/storage stages, which remain
the consumer's responsibility. This conditional source model changes no
default profile or price and provides no global timing qualification.
