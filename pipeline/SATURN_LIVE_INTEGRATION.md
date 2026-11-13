# New live Saturn native epoch

Owned native tree: `pipeline/riscv-isa-sim-saturn-live`, Spike
`72958551566a30f19444bd7e354552824e4d0a98` plus the exact frozen15b source overlay.
Frozen15b, its private dependencies, all earlier epochs and primary are unchanged.

The source bridge dependency is frozen `build/saturn-timing-live-bridge-v4/sdk`,
with component closure `build/saturn-timing-live-bridge-component-v1-final/report.json`
SHA256 `4111c76e87ff546ed75c21e17360b1428ba269ade89f2ac667a607e288af7210`.
The actual three-hart first guest/admission manifest are frozen under
`build/saturn-timing-live-guest-capsule-v1`, report SHA256
`3eea006bdc0243f957fc92d1a3b936695d43e1fad976f7d879aa5ec25e6961c7`.
This guest passes functional359 at seeds0/17 and the actual guarded native
CPU/unit hook at source reset seeds1/17. These scopes remain separate.

`iris_saturn_oracle.{h,cc}` creates an entirely separate processor and simif with
no memory or device service. It never copies main CSR shared_ptrs. Numeric VRF,
MRF and their definedness masks form private, versioned functional intents;
scalar/config inputs are transported from the actual CPU. A preview may compute
logical results ahead of physical completion. It may not publish those whole
results to the main processor at COM. A killed command rolls back its private
version and younger versions; a trap in preview restores its prior private image.

The initial oracle test executes the nine actual guest encodings and passes
1,099 checks: RVV7→8, scalar8, explicit tile zero, full A2/B3 vectors, all1024
K1 INT8 tile cells6 and row/scalar readout6. It verifies that every preview leaves
main VRF/MRF values and masks, mstatus/vstart, minstret and XPR unchanged.
Rollback to an undefined input correctly refuses. This independent oracle test
complements the actual native CPU/source-unit gates described below.

Physical publication must compare masked source data with the matching private
intent before changing main state. Compute VRF event.element_group is already
global: byteoffset=EG*16, with no additional bank offset. Source
RegisterFile.sv:284–292 computes bankmatch using full EG[1:0], line352 sends
EG[5:2] to bank0's row (other banks380/408/436). The corresponding frozen source
is under `build/saturn-timing-component-v1-final/build/saturn-timing-source-v1`.
Rocket global EG uses32bytes. A write mask does not establish definedness.

MRF physical cell index is `((clusterRow*4+clusterCol)*4+cellRow)*4+cellCol`.
For entry: tile=entry>>2, logical row=16*((entry>>1)&1)+clusterRow+4*cellRow,
column=16*(entry&1)+clusterCol+4*cellCol. Physical FP8 completion has priority over
INT8/zero/mvin for one entry, and different entries can commit in the same cell
and edge. The first capability restricts K=1; for K>1, whole-instruction final
snapshots cannot validate intermediate partial accumulations, so per-micro
numeric intents are required before expanding it.

EX candidate, EX fire, S1 MEM kill, PFC S2 front permission, dispatch generation,
physical VRF/MRF publication, scalar response and architectural COM are separate.
Caller node/PC/raw metadata is attached only at actual accepted source S0; every
later event must retain that exact owner. No nearest-PC attribution. INT8 MAC
acceptance/completion is one source-edge graph point; MRF writes do not receive
duplicate MAC credit. FP8 uses its actual accepted/completed interval.

Initial native admission uses the source frontend to latch a real instruction,
with RRD→EX one own core edge and actual unit ready/fire. It starts at a drained
scalar boundary; this is an explicit conservative admission scope, not full
source scalar/vector dual-issue qualification. Source PFC front permission and
replay/block/trap outputs decide front COM; an unsupported replay/trap refuses
rather than retiring a fabricated success. Scalar responses must update RF only
at the actual owned response. Async VME commands can release the front pipeline
while the physical unit continues, permitting real scalar ALU overlap.

FENCE eligibility must use actual source backend_busy/trap_check_busy (plus the
CPU's other source conditions), never the observer's pending() metadata as an
injected ready signal. Pending ownership remains a drain/exit/unsupported-context
check and keeps delayed work attributable after VAT slot release. No vector
memory or shared FPU is admitted in the first profile, and no whole Spike vector
step may publish shared memory at early COM. Future vector-memory publication
must follow owned actual physical beats and matching responses.

The unchanged first guest uses all-three-hart CRT/barrier RAM. Until both Shuttle
source cache paths are connected, its first live Saturn profile leaves source
Serial/scalar-memory mode disabled and explicitly retains the existing functional
shared-memory fixture. It must not claim full SMP coherence, Zephyr or memory
fence qualification on the new source hierarchy. All three harts remain present.

The v4 bridge resolves boot/inactive knownness with an explicit source-proven
predicate convention. Unknown inactive payloads may be concretized only where
RTL does not consume them; active required inputs remain strict. It never
establishes architectural initializedness from a placeholder. Full knownness,
timing, image association and +/-2% flags remain false.

## First executed native gate and guard successor

The actual live hook now executes the real three-hart ELF. Its first prediction
(native `31324c3accae8ad6a15197e6c424e109539b2d368e04c3d0c85667c08c7d98ca`)
was frozen **before** an exact-ELF whole-RTL timing observation under
`build/saturn-native-prediction-313-v4/report.json`, SHA256
`5d075b36512b05082bd82d742560974ea8fdc5058a313981e6d1cf1d9af6b1dc`.
The capsule reconstructs the exact old source overlay and captures raw output,
graph, inputs and SDK dependencies. The guarded successor never rebinds it.
Three earlier failed closure attempts remain preserved; they exposed enclosing
Git path filtering, compiler `-MP` phony targets, and an EX-only assertion that
needed to include the source MEM-ALU result stage. The source/native prediction
was unchanged through those archive fixes.

The final guarded native is
`16972504ccc0bc6b988947d07705ae5f75a8e55b893b08a53c5d25642f8a8b09`, with ABI4
UART `0462cd9ab35d3fe1c3644ecc72b8ae76f4b1903542ab6037d913d916064220fd`.
`build/saturn-native-final-v1` and `build/saturn-native-final-seed17-v1` both pass
values `8 6 64`, completion `DONE 3`, all nine real EX accepts and architectural
COM retirements, 1024 explicit physical zero writes, 1024 INT8 MRF writes and 194
physical VRF bytes. Two actual scalar responses supply `8` and `6`. All private
intents and physical unit lifetimes are released at exit.

The four source MAC points at ticks12988–12991 perform 256 MACs each and overlap
scalar work: MEM_ALU at `0x800004ee`, EX at `0x800004f0`, MEM_ALU at `0x800004f2`,
EX at `0x800004f4`. Same-packet RAW pairing accounts for the MEM results. There
is no whole packet step, divided clock, estimated opcode penalty or zero-latency
hack. Each actual architectural COM additionally asserts numeric VRF/MRF values
and masks stay unchanged. Only matching physical events may publish them.

Program counters are unchanged between the initial and guarded candidates:
`mcycle = 12976 13073 13082 13127`, `minstret = 6379 6447`. These are predictions
with the explicit functional-memory/instruction-service fixture. They are not
source memory-hierarchy predictions or a fit to reference timing.

The live bridge is now source-qualified v4, library SHA256
`047ae13dab928557175002c9a4622ccadae163ec1f6d150eee4e399367d258e6`, capsule
`build/saturn-timing-live-bridge-component-v1-final/report.json` SHA256
`4111c76e87ff546ed75c21e17360b1428ba269ade89f2ac667a607e288af7210`.
Its explicit inactive-input convention permits only source-proven ignored
payloads to be concretized: invalid EX payloads; unused scalar operands selected
by the saved early decoder; unused MEM FRS1 for the finite integer patterns; and
late rounding fields only while actual PFC S2 is invalid and IFC idle (or reset).
It preserves real architectural knownness. Active EX configuration/VSTART/PC/raw
and required operands remain strict. Native masks come from actual CPU
transports. Per-owner live references cover all unit lifetimes; intent release
uses their union with CPU unretired/scalar-response ownership after processing
same-edge writes. The two reset edges have their own metadata timestamps before
the guest origin; translating bridge metadata by that reset origin adds no
source edge or guest cycle.

`build/saturn-native-guards-v1` passes eight actual refusal cases: incorrect
PC/raw, missing entry/schema, vector memory, FP compute, K2 partial reductions,
and a context change while the real unit still owns work. FP/VME hardware
capabilities remain distinct from this first wrapper's supported scope. Pending
interrupt/context handling is refused; no successful retirement is fabricated.
All32 original functional stdouts and all27 legacy/IRQ/Zephyr graphs are unchanged
with the new flag absent (`build/saturn-native-functional32-v1` and
`build/saturn-native-parent-replay-v1`). JSON/Perfetto output is under
`build/saturn-native-profile-v1`.

Reproduce in fresh output directories:

```sh
python3 pipeline/build_native_saturn_live.py --jobs 24
python3 pipeline/saturn_native_check.py --output build/my-live-Saturn
python3 pipeline/saturn_native_check.py --seed 17 --output build/my-live-Saturn17
python3 pipeline/saturn_native_guards.py --output build/my-Saturn-guards
```

The numerical projection identity shown inside the graph identifies the
underlying source timing/numeric cut; wrapper policy and full executable
identities are separately bound by build/capsule receipts. The outer runner
validates the ELF and every admitted PC/raw word against the compiler-produced
manifest. No general-ELF or full-model qualification is inferred from the finite
capability. K>1 requires intermediate per-micro numeric reductions, FP8 needs its
real delayed result/rounding state, and vector memory needs actual owned beats
before the scope expands. The all-three-client memory successor is developed
separately and will merge only after independent native gates.

The initial313 run retired100,921 instructions in22.982652 host seconds, about
0.004391 simulated MIPS, including construction/reset, software execution, UART
and graph output. Later parallel guard runs have different host contention and
are not a controlled speed comparison. This is below the iteration-speed goal.
A practical fast path requires separately measured dominant costs and
source-proven idle/state evolution or independently validated approximation;
`pending().empty()` alone never authorizes skipped clocks. Full speed,
knownness, SMP memory/Zephyr timing, image association and +/-2% stay unqualified.
