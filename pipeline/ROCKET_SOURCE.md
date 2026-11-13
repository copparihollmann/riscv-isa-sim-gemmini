# Three source frontends and scalar pipelines

The isolated Rocket successor adds the actual saved `Frontend` → `IBuf` path
to the two existing source Shuttle frontends. Each hart now has its distinct
scalar pipeline and source instruction-cache/fetch/predictor control. This is
an integration milestone, with synthetic external memory service and explicit
conservative boundaries for the remaining instructions. It is not a calibrated
whole-SoC simulator or an Ethan-image accuracy claim.

The immutable candidate pair is in `build/rocket-source-2539e85c-candidate`.
Its native SHA256 is
`2539e85cfa5defb3835d9f74ea8ed645dd935767e2326d13f6b1017cd9f884c9`;
UART is `ba59d430bfe0c23737828f4a9f13bcb9a0ac66e1c494ef56ab2ab3f9d77173f1`.
It derives from pinned Spike `72958551566a30f19444bd7e354552824e4d0a98`
and frozen source-counter1d52. Primary359 and older epochs are unchanged.

Select `rocket_frontend saved-rtl-M-mode` with the Shuttle source frontend,
private scalar values, and Rocket pipeline. The fixture
`pipeline/rocket-source-synthetic.fixture` also selects the source WFI counter
policy. It deliberately supplies synthetic base clock, core dividers, generic
instruction costs and external instruction-memory first-beat/gap values.
Without a supplied service, the first instruction-cache miss is refused.
No measured readiness, cache contents, predictor state or latency is injected.

The source Rocket path uses four-byte fetch packets and its real IBuf, with
compressed and cross-packet instructions, cache misses, BTB/BHT, and frontend
RAS. Both source frontend and IBuf use the direct core clock in this elaboration
(`RocketCoreParams.clockGate=false`). A replay token travels EX → MEM → WB,
redirects at WB, and retires no guest instruction. Completed wrong-path EX work
is retained as physical occupancy; younger future stages are canceled. Accepted
instruction-cache return beats survive CPU redirects.

Rocket's MEM next-PC comparator checks the actual younger EX PC, otherwise the
current IBuf PC if either IBuf or frontend response is valid. It does not use
Shuttle's per-uop prediction convention. JALR's corrected link becomes available
at MEM; Rocket interlocks its RAW/WAW dependencies in EX only. CSR dependencies
interlock in EX and MEM. MEM control runs after current frontend evaluation and
respects WB redirect priority. Source references are `RocketCore.scala645–659`,
`1041–1053`, `1101–1122` and `1124–1142` at rocket-chip
`fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0`.

IBuf readiness is independent of instruction validity. When the first half of
a 32-bit instruction arrives at the end of a fetch packet, ID can be invalid
while readiness is needed to accept the second half. An initial native bridge
missed this and stalled at `0x8000005e`; the bounded failed trace is retained.
The bridge now permits empty-ID assembly under CPU, exception, WFI and capacity
guards. Conservative instructions retain synthetic standing-valid control and
redirect the queued stream on completion. Their real CPU stage timing is not
qualified by this scalar-subset milestone.

Every frontend instance owns a Verilator context and selects it at construction,
evaluate and commit. Host-only context derivatives preserve the exact compiled
RTL objects. Three standalone instances versus three construction/interleaving
orders match 10,800 physical-output rows over 14,400 edges, including an unrelated
active context before every phase. Invalid reevaluation prevents a stale commit.
These tests qualify the seeded reset/active outputs tested, not arbitrary
unreset RNG histories or production knownness.

The Rocket source boundary transports all eight PMP entries dynamically.
The old upstream Spike reset installed a compatibility all-memory NAPOT region;
that is not Iris reset behavior. This isolated Iris-mode epoch instead preserves
source A/L reset-to-zero and uses the actual 35-bit physical address width,
giving 33-bit PMP addresses. Native tests check reset, WARL width, locked writes,
configuration refusal, and instruction fetch independent of data MPRV. Source
PMP R/W/X and address power-on knownness remain unqualified. Source references
are `CSR.scala549,688,854–864,1684–1692`, `PMP.scala34–46,62–67`, and the emitted
source frontend's PMP port widths. No clipping of a synthetic wide state is used.

The actual Rocket custom CSR `0x7c1` resets to `0x208` (`CSRFile_2.sv`);
the frontend receives that source reset value. Guest accesses are explicitly
refused until native functional support for this CSR exists. CEASE likewise
retains its prior explicit unsupported-core-instruction refusal on hart2.

Validation covers source MEM control against two million comparisons with exact
emitted RTL expressions, seven live control cases including determinism and
refusals, unchanged 32 functional guests and 24 legacy timing runs, actual
processor context/PMP guards, all-three-hart WFI/timer/wake cases, IPI/access-fault/
illegal-instruction guest goldens, and real Zephyr SMP six scalar plus nine mixed
FP/RVV/VME regions. A separate actual native completion-hook test on harts0/2
clears a captured IPI before `step(1)` and verifies its trap cause, mepc, trap
vector, and zero retirement. The live peer-pulse test reports its observed order;
it does not claim that pulse clears before COM when it does not.

The source WFI test preserves wake through a pulse cleared before actual ID.
Its post-wake frontend gap is observed rather than fixed to one core edge.
Legacy numeric count-WFI remains synthetic and passes its negative control.
FP/RVV/VME and data-memory operations retain conservative boundaries. Actual
tile/fabric/source-ID/CDC/NoC/L2/serial memory coupling, detailed vector overlap,
full definedness, calibration, end-to-end speed goals and held-out ±2% remain
unfinished. Instruction memory must return fully known bytes in this subset.

Reproduce the component and integration checks using the source-bound commands
in their `results.json` files. Build with `pipeline/build_native_rocket_source.py`.
Freeze/verify the final closure with `pipeline/freeze_rocket_source.py`. No FPGA
operations are part of these local tests.
