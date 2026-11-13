# Saturn causal ownership and initial live bridge

This component joins accepted source commands to physical activity. It does not
estimate instruction latency and does not attribute work to the nearest PC.
The initial live bridge is a finite integration capability, not a completed
Spike/Zephyr timing model or a claim of 2% accuracy.

The source cut remains the frozen `dacc122a` activity component, derived from
standalone IrisConfig FIR `f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
Its native RTL/runtime/numeric objects are unchanged. The ownership SDK replaces
only the read-only host wrapper; its receipt checks all 341 other archive
members byte for byte. This standalone elaboration is distinct from the saved
FireSim elaboration and the currently deployed FPGA image.

## Interfaces and lifetime

`saturn_timing_live_bridge.hpp` exposes repeated `evaluate`/`sample`, then one
`commit(global_tick, accepted_EX_caller)` per real source edge. Peer ready/credit
signals must converge before commit. The bridge adds no clock edges, readiness,
queue contents, memory responses, or state restoration. Each source edge has a
strictly increasing caller timestamp. The bridge preserves its own Verilator
context during construction, evaluation, commit, failure cleanup and destruction.

A caller node is metadata. It binds only on the actual PFC S0 accept and must
match the physical PC and complete 32-bit instruction. EX candidate, EX fire,
S1 kill, PFC S2, IFC replay transfer and frontend permission remain separate.
Frontend permission is not architectural CPU retirement.

The ledger checks continuous VAT occupancy/head/tail/debug-counter evolution.
Each allocation carries a full host sequence and per-slot generation. The
hardware debug ID may wrap at 16 bits. VAT release means scheduling release;
owners remain in the actual finite execution, FP8, readout, iterative, memory,
response and register-bank buffers after the VAT slot becomes reusable.

Every physical write has a source clock edge and original command/dispatch/
microissue where established. There is no guessed TL/FPU PC owner. Events are
available as typed C++ values and gzip NDJSON from the differential reader.
`pending()` reports conservative metadata lifetimes. It is not a replacement
for source eligibility and does not permit idle skipping.

## Register and matrix writes

Normal VRF writes commit on the current edge. RegisterFileBank gives the normal
port priority over its one-entry low-latency holding buffer and incoming LL
port. The ledger follows that buffer's exact accepted generation, element
group and bit mask. It records source scrub separately: 64 writes on each
compute unit, 32 on Rocket. No constructor zeroing is performed.

Compute has four VRF banks; Rocket has one. The element group identifies the
architectural bit interval starting at `element_group * DLEN`. `bit_mask` and
`data_words` are little-endian 64-bit chunks; VRF data is masked before emission.
The mask is a physical write-enable mask, **not** evidence that operand bits
were initialized. The caller must independently prove numeric definedness.
Source zero/scrub writes have source-proved zero payloads.

MRF events retain the actual per-cell, per-entry priority from
`OuterProductCell.sv`: FP8 completion, then INT8, then zero, then move-in.
FP8 completion and a current operation can write two different entries on one
edge. INT8 multiplication/accumulation is a same-edge physical event, not an
invented positive-duration transfer. FP8's two valid stages remain source-owned.

`mrf_cell = ((cluster_row*4+cluster_col)*4+cell_row)*4+cell_col`, and each cell
has 16 entries. For the qualified row/compute mapping, the sequencer's entry is
`{tile[1:0], row_quadrant, column_quadrant}`. Thus tile is `entry >> 2`, row is
`16*((entry>>1)&1)+cluster_row+4*cell_row`, and column is
`16*(entry&1)+cluster_col+4*cell_col`. This mapping does not certify the unsupported
column readout semantics. The FPGA's accepted column observations remain a
separate diagnostic; no fabricated mathematical-column or illegal result is used.

The host extractor binds real physical inputs retained as Verilator `Vcellinp`
temporaries. Where the same cluster move-in value is shared by all 16 cells,
it verifies literally identical source input expressions and records those
source paths/hashes. It does not recreate an optimized-away expression by guess.

## VMU and scalar responses

LIQ/SIQ allocation, load-tag reservation, store request/SIFQ/ROB lifetime,
accepted external A beats and matching D beats retain full macro generations.
Rocket may accept an early external Put beat before the internal wide request
fires on its final down-sized beat; ownership starts at its earlier real
reservation. A buffered external request retains its accepted packet address.

The load-response queue is source depth two. Compute has two load-segment
buffer slots; Rocket has one. The extractor proves `wrow != 0` equals the real
segment-buffer input acceptance for every physical EEW/segment-index encoding.
The implementation refuses missing generations, but the four current whole-SoC
workloads do **not** qualify segmented-memory behavior. No segmented-coverage
claim follows from non-segmented replay success.

MaskUnit tail/result ownership follows the actual selected pipe token, then the
integration's depth-two scalar response queue. Zero-VL scalar responses retain
their actual frontend command even though they bypass VAT. The real scalar
readback fixture validates RVV results through this queue.

## Initial native capability and functional publication

`build/saturn-timing-live-bridge-v2/sdk` is the numeric-projection bridge used for
the next isolated native integration. It requires a provenance-bearing explicit
encoding whitelist, all driven physical input bits defined, and an exact caller
token for every accepted command. It rejects vector-memory commands before
their accepting edge, unconnected memory/FPU requests, unsolicited responses,
missing caller metadata and unresolved numeric projection. A rejected commit
poisons the instance and advances no source edge.

This bridge never invokes Spike's architectural step or publishes guest state.
The native caller owns private, versioned numeric intents and must discard
killed candidate forks. Only the matching physical masked VRF/MRF commits and
owned scalar response may publish state. Preview must not dirty real CSR/VS/
minstret. The first executed-ELF capability is initialized integer compute with
no pending vector memory, shared FPU or interrupt interaction; the full
three-hart/Zephyr/memory integration remains separate work.

## Reproduction and evidence

The source SDK is `build/saturn-timing-ownership-sdk-v7`, the whole-SoC observer
is `build/saturn-timing-ownership-rtl-v7`, and the extra source schema is
`build/saturn-timing-ownership-source-v11/schema.json`. Captures under
`build/saturn-timing-ownership-capture-v4` retain the original VME, RVV, FPComp
and shared-FPU architectural signatures. Their continuously replayed event
streams are in `build/saturn-timing-ownership-replay-v12`.

```sh
python3 timing/saturn_timing_ownership_proof.py \
  --replay build/saturn-timing-ownership-replay-v12 \
  --captures build/saturn-timing-ownership-capture-v4 \
  --sdk build/saturn-timing-ownership-sdk-v7 \
  --bridge build/saturn-timing-live-bridge-v2 \
  --output build/saturn-timing-ownership-proof-NEW
```

The explicit synthetic EX fixture is not CPU or ELF execution. Its two profiles
each execute 65,539 accepted commands, 65,538 actual VRF writes, a real scalar
readback and one debug-ID wrap. The full numeric bridge proof is in
`build/saturn-timing-live-bridge-wrap-v2/report.json`; constructor/phase/input/
capability/context failures are in `build/saturn-timing-live-bridge-guards-v1`.
These are component proofs, not simulated SoC MIPS or timing calibration.
