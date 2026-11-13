These are conditional source capacity ceilings, not achieved performance.

Build: python3 hardware/throughput_limits/derive.py --output <NEW_DIRECTORY>
Controls: python3 hardware/throughput_limits/test_limits.py
Frozen report: build/throughput-limits-source-v3/report.json

The associated image-build generated SV is pinned in full at SHA256
c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64.
The report stores45 exact module excerpts with original line locations,30 full
input SHA256s, source expressions, full repository commit IDs, and explicit
source/image association limits. Co-location does not prove all image build
inputs or attest the loaded implementation. No runtime/provider/profiler changed.

Per CLOCKED source edge, ready inputs and no competing resource/hazard:
                             Shuttle0/1          Rocket2
  scalar integer ALU         <=2 instructions    <=1 instruction
  scalar FADD H/S/D           <=1 add             <=1 add
  scalar FADD EX->output      4 edges             3 edges
  dependent scalar FADD       gap>=5 edges        gap>=4 edges
  vector VADD e8/16/32/64      <=16/8/4/2 adds     <=32/16/8/4 adds
  vector FP H/S/D FADD         <=8/4/2 adds        <=1 element, shared FPU
  vector FP H/S/D FMA          <=8/4/2 FMAs        <=1 element, shared FPU
  vector BF16 / FP8 FMA        <=8 /16 FMAs        not configured
  OPU INT8 / FP8               <=256 cell MACs     absent
  vector ATL A or D wire      <=32 B/beat-edge     <=8 B/beat-edge

FADD is one arithmetic operation; FMA/MAC is conventionally two. H/S/D and
BF16/FP8 peaks share selected-format physical blocks. Scalar and vector FP
share the Rocket FPU. Do not sum alternate-format or overlapping peaks.
Shuttle scalar and vector FP are distinct units but still have frontend/VRF/
writeback constraints; the catalog does not certify their aggregate rate.

The two compute FP blocks are actual64-bit SegmentedFMAPipe instances. Each
selects1D/2S/4H/4BF16/8FP8 results. Rocket uses an actual single-element shared
FP request, even with DLEN256. Thus VL32 FP16 LMUL2 requires at least32 Rocket
service edges but4 compute service edges, before setup/dependencies. LMUL
extends the group; it never multiplies physical arithmetic lanes. VL/tail/mask,
widening, reductions and other opcodes need their own work/recurrence model.

Each compute OPU has16 clusters of16 cells. One accepted full enabled16x16
subtile can perform256 MACs. Physical FP8 completion is2 edges later; the
sequencer retains2 entry hazards, so repeating one entry needs issue gap>=3.
Cycling distinct entries can issue on consecutive edges. TM17,TN17 has active
cell counts256,16,16,1 across4 subtiles, not1024 MACs. Zero-sized geometry has
zero MAC work. All-32x32 shape has4 subtiles; TK multiplies this issue work.
Row move handles at most4 32-bit elements per microissue. Zeroing/moves are
state/transport work, not MAC/FLOP work. Column readout is not configured.

Scalar dependent gaps use the finite actual saved-whole-CPU phase proof:
288 accepted H/S/D FADDs,2613 checks, EX->write4/3 and minimum write->next EX1.
This proof is source timing evidence, not a physical image performance result.

The vector wire ceilings count accepted ready&&valid DATA beats only. Get
control does not carry the logical read bytes on A; acknowledgments, masks,
partial transfers and framing reduce useful payload. MLEN128/128/256 is distinct
from physical ATL256/256/64. Intent bytes cannot establish physical traffic.
No DRAM/NoC achieved bandwidth, cache service latency or machine roof is supplied.

The optional500MHz conversion is a source requested/summary frequency, conditional
on clock running. It does not establish a measured CPU frequency or application
rate. Unknown families and illegal geometries refuse; unproved bandwidths stay
null. No empirical timing coefficients or global held-out timing labels are used.
