# Saturn runtime reference and timing boundary

This component contains the exact saved `SaturnShuttleUnit` for compute harts0/1
and `SaturnRocketUnit` for hart2. It is a reference for a Spike functional engine
with causal graph timing, and an integration component. Its full numerical RTL
is too expensive to be the final compiler iteration backend. It does not claim
whole-SoC timing, a held-out2% result, or identity with Ethan's deployed image.

`build/saturn-timing-component-v1-final/report.json` inventories an immutable
copy of the source, build tools, public SDK, tests, independent whole-SoC port
captures, raw guest signatures and qualification receipts. The saved standalone
FIR SHA256 is `f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
Full source-context commits and dirty patches are included; that context does
not prove the saved FIR equals a clean checkout or the programmed image.

|Physical configuration|Compute harts0/1|Rocket hart2|
|---|---:|---:|
|VLEN / DLEN / ELEN, bits|256 /128 /64|256 /256 /64|
|VRF banks / element groups|4 /64|1 /32|
|VAT slots|32|8|
|VDQ / load / store issue queue entries|4 /6 /3|2 /2 /1|
|Permute / integer / FP issue queue entries|1 /3 /3|0 / unified0|
|Outer-product unit|INT8 and FP8|Absent|
|External ATL data width|256|64|
|Shared scalar/vector FPU|Internal compute pipelines|65-bit recoded request/result|

The source contract in `build/saturn-timing-contract-v3/source-contract.json`
cites exact lines and file hashes for queues, chaining, bank reservations,
reset, scalar stage control, OPU backend registers and external interfaces.
Rocket's vector route is fixed to ATL in this elaboration. Its physical
256-bit Hella interface remains exposed; dormant Hella vector transactions are
not claimed as tested. DLEN is not the memory-bus width.

## Connecting an engine

The C++20 SDK is `build/saturn-timing-sdk-v1/sdk/saturn_timing.hpp` plus
`libiris_saturn_timing.a`. Construct `SaturnTimingCut` with the correct profile,
hart ID, seed and explicit `ReferenceScope::ExplicitTwoStateWithExternalDefinedness`.
`input_fields` and `output_fields` enumerate every physical source-width word.
There are no defaults for missing peer signals.

For each actual source core edge, drive physical inputs, call `evaluate`, sample
outputs, converge peer ready/data with repeated `evaluate`, and call `commit`
exactly once after the common edge is settled. No state advances during settle.
An invalid frame invalidates its pending commit. Clock identities are exposed;
the component invents no clock frequency, CDC delay or memory-service latency.

EX candidate, EXfire, MEMkill, COM/WB front token, replay, late retirement,
scalar result and backend completion are separate events. An engine must retain
instruction identity through them and execute Spike architectural effects only
at the source-compatible commit boundary. The observation ledger in
`saturn_timing_check.py` demonstrates their separation without supplying any
model state or readiness. `io_busy` alone does not describe all live pipeline
tails and is insufficient for idle skipping.

Memory/TLB/Hella/FPU service is external. Couple real accepted TL A/D beats,
source IDs, sizes, masks and ready signals through the configured width
adaptors/arbiter/CDC/cache/NoC. The Rocket trace includes multibeat puts and real
scalar/vector shared-FPU contention. Do not replace individual data beats by a
final line-completion event or a fitted instruction penalty.

## Reset and definedness

The source VRF is unreset memory with an actual zero-write scrub:64 compute
edges and32 Rocket edges after reset. The source gates ordinary sequencer reads
during scrub. The early-reader, VMV.vi/vx, vector-load and VME tests use random
initial data and inspect accepted physical writes; they never constructor-zero
the RAM. Ordinary move instructions retain source dummy operand dependencies.

An explicitly early compute vector load under a documented low-latency external
TL fixture can write ahead of the scrub and later be erased by it. The Rocket
single bank in this finite test holds that load until scrub ends. Therefore
instant zero initialization at arbitrary first vector access is not proved.
A functional shortcut requires an explicit post-scrub boot precondition; all
four captured ELFs satisfy it, with at least13,853 actual source edges observed
before first EX. This is a finite ELF observation, not a universal startup bound.

Tile MRF entries are unreset and remain undefined until explicitly written.
The VME first-reader test explicitly zeros its selected tile entry. Untouched
entries are checked to retain their initial values. None of these proofs allows
Spike to save tiles automatically, fabricate unknown values, or initialize them
on behalf of an OS ownership API.

The generated reference is two-state. Comparisons qualify payload with actual
valid/protocol signals and known initialization in these guests; inactive or
uninitialized words are not certified. The explicit constructor scope prevents
silently advertising general four-state definedness or production availability.

## Evidence and cost

The final `saturn-timing-replay-v2` captures cover all3 harts: VME all4 operand
format pairs plus hart2 refusal/producer; RVV SEW8/16/32/64 and LMUL1/2/4/8;
FP comparisons/reductions; shared-FPU arithmetic. Raw independently decoded
mailboxes pass all expected checks. Continuous actual-reset replay computes all
internal state, totaling932,079 per-core edges and15,127,193 qualified output
word comparisons. The shared-FPU guest contains364 Rocket request/response
pairs. No observed internal queue state or readiness is reinjected.

The SDK phase guard tests use real active prefixes, revise same-edge readiness,
recover after bad-width input and reject stale sample/commit. Output corruption
tests exercise the same qualified comparator as the successful whole-RTL replay.
Reset write transcripts also have an independent symbolic known-bit reader.

In-process active-window reference throughput is about5.2–6.4k compute edges/s
and94–98k Rocket edges/s across three seeds, including all actual guest edges
and source debug print formatting. This is component throughput, not SoC MIPS.
File parsing and text transport are outside that timed window. No idle skipping
or measured checkpoints are used. A separate fast backend must qualify each
numeric substitution against this frozen control/reference evidence.

Run the independent capsule verifier with:

```sh
python3 timing/saturn_timing_package.py --verify
```

Old `replay-v1`, failed contract attempts and the failed private-field binding
attempt are historical; the final capsule binds the stable v2/v3 receipts above.
