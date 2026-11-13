# Source-derived Shuttle frontend work

The512-operation error is caused by actual fetch/cache history. The standalone
saved-Iris reference has different warm cache victims on harts0/1; instruction
refills starve the seven-slot frontend buffer. The original failed timings and
the immutable91c4 predictions are preserved. This evidence is fitting/debug
material, never a new held-out accuracy pass.

The full source-clock observer is closed at
`build/frontend-phase-proof-interface512-v4/report.json`. Its169,796 actual
pre/post frames include reset, WFI and non-ROI activity. No target/loader/guest
change occurred; the entire448-byte coherent signature is byte-identical to
the unobserved512 run. The prior121,877-frame observer's field projections,
all171 full refills,512 body instructions per episode and7 measured eviction
histories still pass the independent audit. Earlier failed attempts remain.

The source is Shuttle a536ed1df91a0f65770e36758291d02a8cb929c4 and Rocket
fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0; the saved FIR digest is
f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4.
The source cache and frontend components are separate from the frozen native
packages and have no refill-latency defaults. They are not yet live-integrated.

| Component | Source contract | Independent evidence |
| --- | --- | --- |
| `frontend_cache.*` |64sets×2ways×64B tags, validity,16bit LFSR and eight data-beat updates|171 full refill histories,786,574 actual checks; corrupt valid tag rejected; invalid random tag bits ignored|
| `frontend_cache_pipeline.*` |two-stage synchronous tag lookup, D-port conflicts, S1 kill, S2 hit/miss, request gating and outstanding refill|continuous reset-only replay of169,796 actual edges;1,729,305 checks;171 derived A requests/1,368 D beats;3 corruptions rejected|
| `frontend_queue.hpp` |seven-slot onehot queue, variable parcel capacity, packed rotation, dequeue/clear priority|121,877 actual per-transition pre/post states and capacity/clear controls|
| `frontend_parcels.hpp` |RVC/non-RVC CFI bit predecode, four-parcel mask, spanning32bit instruction, redirect cutoff|262,144 actual saved-RVCExpander comparisons plus packet/carry/cutoff controls|
| `frontend_select.hpp` |F0 next-PC/replay/clear priorities, queue readiness, F1/F2 valid propagation and fault enqueue|169,794 actual per-transition states;1,188,558 checks,23,924 replay selections,493 flushes plus reset/fault controls|

The continuous cache test receives only actual interface inputs: S0 valid/vaddr,
S1 translated address and kill, S2 instruction-fault kill, invalidation, memory A
ready, D data-beat fire and the actual tile reset. It computes all cache control
outputs and internal state. It never injects S2 hit/miss, A request, replacement
state or a recorded cache checkpoint. SRAM tags are unknown until written;
uninitialized invalid tags do not become invented functional state.

Queue/select tests are deliberately narrower: each observed pre-state is supplied
to verify that transition. They do not claim to reconstruct unsampled queue
activity or the complete frontend. The selector's F1 prediction and F2 predecode
target are explicit peer inputs; core redirect PC is observed from F0 only on
the flush-selected path. These boundaries remain visible in the receipt.

Relevant source lines are Shuttle `ICache.scala:49-76,90-120,155-175,207-216`,
`Frontend.scala:133-199,259-326,328-383`, `FetchBuffer.scala:16-39,76-129`;
Rocket `RVC.scala:19-43,77-111,145-169,183-186` and `BTB.scala:59-63`.
Saved `ShuttleICache.sv:106-176,238-256` confirms the concrete cache geometry
and priority. Saved `ShuttleFrontend.sv:193-198,277-288,372-381` establishes
six RAS entries; a three-bit head is not eight entries.

## Native integration contract

A sixth native epoch must compose these components on each owning hart edge.
Advancing the frontend only when a functional instruction retires loses cache
warming, refill arbitration and fetch-queue backpressure. Graph events must
record fetch requests, response/queue occupancy, miss requests and individual
return beats separately from retired instructions. CSR observations retain their
existing precise pre-edge read and retirement binding.

1. The frontend owns a fetch PC and its F1/F2 stages independently of the
   architectural PC. It must decode/cache speculative and replayed fetches and
   retain raw parcel/expanded instruction/PC/prediction payload in the queue.
   Cache warming from architectural PCs alone is not a source-exact shortcut.
2. A memory A request is created only by the cache's derived request-valid and
   real ready handshake. Its64B response is eight8B D beats, with explicit
   shared-resource/bank/clock scheduling. The first returning beat invalidates
   the selected way, each beat steals the fetch port, and the final beat
   installs the tag. A single callback at the end of a scalar8B route cannot
   express this interface. L2 hit/miss/coherence and serial-TL transport must
   supply the beat schedule; the observed33–44/734–739 delays are not constants.
3. A core flush clears fetch buffering and invalidates F1/F2 frontend work.
   It is **not** `ICache.invalidate` or an instruction-fault S2 kill. An already
   accepted wrong-path refill must finish and can change tags/replacement even
   after its instruction is discarded. Source `Frontend.scala:181,201,350-381`
   and `ICache.scala:63-72,97-105` distinguish these signals.
4. BTB/BHT/RAS, instruction translation and source MEM branch resolution must
   generate those peer signals from owned state. F2 unconditional jump/return
   predecode and MEM resolution have different roles. Source frontend calls use
   rd bit0; source MEM RAS correction calls require rd=x1 and returns rs1=x1,
   rd=x0 (`Core.scala:694-744`). Preserve these actual distinctions. RAS entries
   start unknown, delayed writes and explicit core updates have source priority.
5. Wrong-path pure packets require graph cancellation and precise younger-state
   discard. Source branch resolution occurs in MEM (`Core.scala:690-748`),
   while architectural effects remain ordered at COM. Cancellation must not
   undo shared memory/cache effects already accepted. Do not execute wrong-path
   traps, CSR writes, MMIO or stores merely to find the next PC.
6. Keep explicit source refusal for unsupported debug/virtual fetch, unmodeled
   translation/prediction state, missing memory parameters and absent beat
   support. Conservative drained CFI timing remains scoped as such until its
   source pipeline/redirect is implemented. No native flag may silently claim
   these components are active before their live coupling is tested.

The next native coupling depends on the reviewed combined knownness/pipeline
ABI and a causal line-refill interface, not a sampled RTL trace used as a replay
oracle during normal simulation. Existing primary5e6 and isolated91c4 remain
unchanged. No FPGA action or Ethan-image association follows from this work.
Full functional/RTL/timing certification and held-out+/-2% remain false.

```sh
python3 pipeline/frontend_cache_check.py --output build/frontend-cache-new
python3 pipeline/frontend_queue_check.py --output build/frontend-queue-new
python3 pipeline/frontend_cache_pipeline_check.py --output build/frontend-cache-pipeline-new
python3 pipeline/frontend_parcels_check.py --output build/frontend-parcels-new
python3 pipeline/frontend_select_check.py --output build/frontend-select-new
python3 hardware/frontend_phase/analyze.py --output build/frontend-phase-proof-interface512-v4 --verify
```


## MEM branch control and comparison extension

`frontend_branch.hpp` implements the source MEM resolver alongside the existing
frontend components. It accepts source per-lane uops and EX comparison/write-data
results and computes selection, target, misprediction, BTB/BHT update enable,
short-forward-pair suppression and corrective RAS decisions. It is not yet a
live native branch pipeline. The actual512 run covers169,012 post-reset frames,
303 selected uops:267 conditional branches,13 JALR returns and23 JALs. Its
339,842 comparisons pass; three corrupt output controls reject changed
misprediction, predictor update and next PC.

No false BTB prediction or short-forward pair appears in that observed program;
those regimes are separately directed source controls. There is no observed
JALR rd=x1 call in this ELF. Its core RAS write-data path remains a source-derived
control, without a whole-CPU execution claim. The source writes MEM wdata into
the corrective RAS update (`Core.scala:738-740`), while JALR architectural link
override is written into the next COM uop (`Core.scala:793-795`). These phases
must not be collapsed into a guessed universal return-address value.

The helper's six integer branch comparisons match787,968 actual outputs across
both saved Shuttle `RocketALU` and Rocket `RocketALU_6` modules:64 boundary pairs,
16,384 deterministic random pairs and16,384 equal pairs, six branch conditions
and both DW values. The actual architectural decode uses DW_XPR; the second DW
control confirms the source comparator is independent of that shift/result bit.
Three unsupported comparison forms are explicit refusals. This does not certify
ALU issue/retirement or prediction timing.

The extended read-only proof is
`build/frontend-phase-proof-branch512-v5/report.json`. All169,796 prior interface
field projections still match, the448-byte signature is unchanged and the
171 refills/7 eviction histories remain intact. The extension does not modify
RTL, actors, clocks, memory preload or program bytes.

```sh
python3 pipeline/frontend_branch_check.py --output build/frontend-mem-branch-new
python3 pipeline/frontend_branch_compare_check.py --output build/frontend-branch-compare-new
python3 pipeline/frontend_branch_rejections.py --output build/frontend-branch-rejections-new
```
