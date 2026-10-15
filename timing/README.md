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
describe the selected scope. Counter-derived control, addresses, stored data or
unmodeled architectural state inside/before the selected scope refuse timing.
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
