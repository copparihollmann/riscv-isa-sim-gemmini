# Finite source-derived FADD scheduling component

`rvv_fadd_eg_source_v1.hpp` is a standalone C++20 control component for the
saved Compute128 Saturn configuration used by compute harts 0 and 1. It does
not change a native engine, model descriptor, fixture, or default selection.

The admitted operation is unmasked IEEE `VFADD.VV`, `vstart=0`, full `VLmax`,
SEW16/32/64, and aligned LMUL1/2/4/8. VLEN256 and DLEN128 give two 128-bit
element groups per architectural register in this particular source profile.
LMUL therefore supplies 2/4/8/16 groups. Neither this geometry nor its timing
is transferred to Rocket or another vector configuration.

The component models the actual VDQ4 without flow/pipe, FP issue queue3 with
pipe, one sequencer, and four source write-pipeline stages. A command accepted
at the backend input at edge E can first issue at E+3 through the empty queues.
Each accepted microissue writes its EG at E+4. The current write edge remains
in the older-writer hazard mask until that edge commits; there is no invented
same-edge VRF bypass. Normal VRF reads are asynchronous in this source, under
the qualified no-scrub/no-competing-port conditions. The component adds no
extra guessed read latency.

Read/write hazards are EG masks. A younger command can consume an older EG
after its physical write while the older command still has other groups in
flight. Other sequencers' older read/write intents and actual read/write-port
availability are explicit `Ports` inputs. Whole-register or whole-VRF actor
completion is not substituted for these masks. Default available ports mean
the explicitly quiescent, uncontended conditional case; they do not prove
runtime port availability. A native caller must establish that condition or
connect the real arbitration and older-intent inputs.

`step` returns pre-edge handshakes, occupancies, candidate/read/write group
identities, the actual microissue/write events, and pipeline stages, then
commits exactly one source edge. Active work forbids skipped or repeated
edges. Command generation IDs and live VAT reuse are guarded. The component
has no cancellation API for an accepted backend command. Pre-COM speculative
CPU reservations and replay must be handled separately by a future bridge;
accepted source work must retain its owner through completion.

Frozen qualification is in `build/rvv-fadd-EG-source-v4/report.json`:

- 96 full saved-unit runs: three IEEE widths, four LMULs, same destination,
  alternating independent destinations, producer/consumer chaining, and
  WAW-only streams, two randomized-reset seeds, 96 commands per run.
- 9,216 commands, 69,120 microissues and physical write beats, 2,281,470
  edge-field comparisons including all queue handshakes, eidx/EG/VAT identities,
  pipeline stages, write events, and FFLAGS-valid timing.
- A separately compiled original `ExecuteSequencer_1` and `PipeScheduler`
  matched 90,000 randomized continuous edges and 943,398 fields. External
  RAW/WAW/WAR masks and actual module read/write-port backpressure were driven
  at their public input ports. This is conditional module qualification,
  not proof of a whole-SMP arbiter.
- Six actual model mutants failed against source: early physical write,
  missing RAW, missing WAW, ignoring the writing edge, extra IQ capacity, and
  collapsing destination EGs into a whole-register identity.
- Optimized and checked-library guard runs each passed 25 checks and 15 typed
  refusals for geometry, identity, edge order, and real EG/port holds.

The saved-unit reference has explicit two-state/reset scope and uses the
already pinned ownership SDK. Original generated RTL bytes are unchanged.
Its source mapping and exact new compile/link commands are recorded; no
hardware timings, protected labels, fit, CPU latency constants, or default
provider changes were used.

This is a control proof. FP result values and known masks, per-operation
exception flag values and their OR/knownness accumulation, FS/VS dirty state,
CPU/IRQ/trap interaction, physical VRF numeric publication, cancellation and
integration with other VUs remain unqualified. Matching FFLAGS-valid does not
qualify FFLAGS values. Future overlapping numeric execution must publish the
owned EG and local flag delta at each source write, rather than restoring a
whole-VRF or whole-FCSR snapshot early. FP8/BF16, widening, reductions, masks,
partial VL, nonzero vstart, and Rocket shared-FPU arbitration are outside this
finite component's admitted geometry.
