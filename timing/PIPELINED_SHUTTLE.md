# Live pure-integer Shuttle pipeline design

This experimental extension is being developed in an isolated sibling Spike
worktree. The primary functional/memory package remains unchanged. Source pins,
overlay identity, file hashes and line intervals are frozen in
`pipeline/evidence/source-design.json`. This is a source-backed pipeline subset,
not a calibrated Iris timing profile.

The existing live adapter calls `step(1)` only at a modeled completion event,
which correctly orders shared-memory effects and timer/device time. It permits
one in-flight instruction per hart, so it cannot represent Shuttle's observed
IPC above1. The replacement must overlap multiple packets in EX/MEM/COM/WB;
issuing two instructions then waiting for their whole packet is insufficient.

## Source constraints

`Core.scala:78-142` defines EX, MEM, COM and WB registers for both lanes. RRD
selection and forwarding use the source-specific `shuttle_issue` classifier.
Pure results are EX or MEM; a same-packet RAW producer can move lane1 to MEM.
`Core.scala:650-674` exposes the corresponding EX bypass readiness. The MEM/COM
forwarding and priority are retained, including unused instruction fields that
retime an otherwise independent ALU. `Core.scala:1272-1304` writes the RF in WB;
`998-1018` retires at COM. Those are separate events.

Interrupts are selected at RRD with higher priority than frontend faults or
illegal decode (`255-284`). Their exception tag traverses the pipeline. Already
issued older ALUs must retire before the tagged interrupt PC; clearing an IPI
later must not erase the captured exception. COM exceptions kill younger work
(`1190-1215`). Spike already suppresses newly pending interrupts while an issued
instruction completes; the new path must also latch a deferred exception instead
of taking it at an older unretired architectural PC.

## Initial domain and explicit limits

The first subset accepts verified32-bit, pure integer ALUs on harts0/1. It
excludes CFI, memory, atomics, FP/vector, configuration/CSR/system instructions,
triggers, single-step/debug, translated instruction fetch and unmodeled external
stalls. Such boundaries drain the pure pipeline before using the existing
conservative path. Hart2 keeps its single-issue adapter. This subset does not
claim excluded instructions cannot pair in RTL.

Frontend prediction tags are not guessed from opcodes. An explicit experimental
sequential-frontend fixture is required until a source-backed frontend model
supplies those tags. M-mode direct executable instruction fetch avoids page-table
A-bit writes from speculative translation. A second-slot fetch fault is retained
and attributed to its own PC; it never escapes through the first instruction's
`step` call. Unknown dynamic inputs refuse the optimized path or remain a named
unmodeled timing boundary.

## Architectural state and bounded event flow

A per-hart queue holds at most four packets, corresponding to the four source
pipeline registers. Each packet has one/two instruction records, its RRD
acceptance cycle, source lane plan, producer dependencies and generation ID.
Architectural Spike state remains at the oldest unretired PC. The fetch frontier
advances separately only through known sequential pure ALUs.

A pure ALU may be fetched and scheduled without evaluating its value: it has no
shared-memory/CSR effects, and its functional value is needed only when it
retires. At COM, cached instructions execute individually in exact program/lane
order through Spike's real handlers. Earlier committed register values produce
the same architectural result as the modeled bypasses; producer-ready events
control issue independently of those architectural writes. AUIPC uses its actual
retiring PC. There is no functional execution of a younger pure instruction at
issue time.

Every instruction receives a real result-ready event and a COM event. A plain
ALU produces at EX; a retimed lane1 produces at MEM. MEM scheduling keeps the
source path's extra stage, including structural retiming without a semantic RAW.
COM callbacks can retire both lanes at one modeled cycle, while several newer
packets remain in flight. WB has its own later event for source RF availability
and bounded queue release. All event durations are positive. Dependencies and
stage events replace clock scaling, zero-latency hacks and unconditional
`step(2)`.

Stage distances are measured from the chosen RRD acceptance boundary: EX-ready
+1 hart cycle, MEM-ready+2, COM+3, WB+4. The exact counter observation phase must
be compared with the reference RTL before claiming cycle accuracy. Fixed stage
distances alone do not model frontend/cache or branch penalties.

RRD integer hazards are recomputed from the live packet slots in the source
LL/WB/COM/MEM/EX order and lane order. The last matching producer wins. The
source RF scoreboard stays ready for this pure-only domain; unknown late
writers prevent entry. EX backpressure, an occupied stage or a full queue blocks
new acceptance. Missing structural/dynamic inputs remain unknown.

## Precise deferred traps

A new read-only Spike interrupt probe may capture `std::exception_ptr` from the
existing interrupt-selection implementation, without `take_trap` or PC changes.
At the next RRD opportunity, a pending interrupt or deferred fetch fault becomes
a lane0 exception sentinel; no younger instructions are admitted. At its COM
boundary, the captured exception is rethrown inside Spike's normal `step(1)` trap
handling with the correct architectural PC. This preserves priority, tval,
privilege handling and fatal hooks while retaining a latched interrupt even if
the live line later clears.

The implemented first guard admits only known base RV64I ALUs. An unexpected
trap from an admitted pure instruction ends the timing run with a named fatal
refusal; it never resumes younger work under incorrect timing. A general
exception/squash/replay path for broader speculative instruction classes remains
unimplemented. Non-pure illegal instructions drain to the ordinary Spike trap
path. Graph event completion is distinct from architectural retirement, and a
latched interrupt sentinel never contributes to minstret.

Counter reads and all memory/vector/config operations remain serialized
boundaries. mcycle/mtime advance with the shared event clock; minstret advances
only for real committed instructions. All three harts share that clock and the
existing memory/device scheduler. No shared-memory operation may be executed
ahead of its modeled event.

## Required validation before any publication

1. Long independent/dependent pure streams demonstrate multiple overlapping
   packets and source-legal dual issue, not whole-packet serialization.
2. RAW, WAW, x0 and unused-source-field retiming agree with source control;
   counters and graph retirement counts agree per instruction/hart.
3. Deferred second-slot faults, illegal instructions and latched timer/IPI
   exceptions preserve precise PCs and suppress younger effects.
4. Counter reads, branches, fences, memory and traps drain safely; memory issue
   still uses the current guarded live adapter on all three harts.
5. Functional outputs and interrupt/atomic checks agree with the current model;
   deterministic schedules replay identically. Single-step/debug are explicit
   refusals/boundaries rather than silently bypassed.
6. Saved-Iris RTL microbenchmarks determine the counter phase and measured
   throughput/error. Until then profile metadata remains uncalibrated and the
   +/-2% held-out gate remains false.
