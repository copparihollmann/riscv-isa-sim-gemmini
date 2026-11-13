# Source WFI and counter policy

This experimental successor to frozen frontend778 adds CSRFile's WFI counter
policy on all three harts. It uses the saved Iris source design and the existing
Shuttle source frontend. Rocket's source frontend is a separate next step.
The old numeric `count_wfi` fixture option remains explicitly synthetic.

Select `counter_policy source-ungated-stall` and `hart H DIVIDER source` together.
The parser rejects source/numeric mixing. Source policy requires actual captured
CSR reads for profiling; it cannot infer a guest counter from global time.
`pipeline/source-counter-synthetic.fixture` deliberately supplies synthetic core
clocks and instruction-memory service. These are integration stimuli, not
calibrated Iris parameters. Unknown external instruction service still fails.

CSR.scala646–650 increments `mcycle` on `ungated_clock` only when pre-edge
`csr_stall` is false and CY inhibition is clear. Lines1093–1095 give pending
locally enabled interrupts and exceptions priority over WFI entry. Lines1231–1233
define the stall as WFI or sticky CEASE. Therefore the WFI entry edge counts,
parked edges and the wake edge hold, and the following edge resumes counting.
Local pending interrupts wake WFI even when global MIE is zero. CLINT `mtime`
continues using its independent timer clock.

Every source-policy hart edge is visited; there is no idle skipping. The native
policy samples local device lines before their edge update. The actual SoC
interrupt synchronizers and crossings are not yet timing-qualified. A short IPI
clears Spike's transport-only waiting flag at the source wake edge, while CPU
issue stays blocked for that edge. This preserves a wake pulse that has cleared
before the next instruction can issue.

The actual saved Rocket has `clockGate=false` (RocketCore.scala51); its IBuf,
frontend and CSR inputs use the direct core clock. The generic optional Rocket
clock-gate code is not evidence of a gate in this elaboration. Shuttle connects
CSR `ungated_clock` directly to its clock (exu/Core.scala58–62). Stopping
`mcycle` during WFI follows CSR stall, rather than an invented gated-clock rate.

Counter read snapshots still occur at the owning COM pre-edge. Source CSR
write-over-increment priority, inhibit behavior, wraparound and architectural
retirement are separate concerns retained from the previous counter epoch.
Conservative memory completion that is not on its hart edge is refused under
this policy; it cannot reuse a stale pre-edge snapshot.

The source-counter state class is independently compared against the saved
Shuttle and Rocket CSRFile RTL for44 transactions. The earlier38-transaction
clock proof is retained. All source facts are bound to rocket-chip
`fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0` and Shuttle
`a536ed1df91a0f65770e36758291d02a8cb929c4`; reports carry full file hashes and
line citations. The CEASE sticky bit is component-tested. Native hart2 CEASE
keeps the existing explicit unsupported-core-instruction refusal until its
source CPU halt semantics are integrated. Only hart2 advertises `xrocket`.

Evidence includes all3-hart timer/WFI and short-pulse tests,32 previous functional
guests,24 byte-identical legacy timing runs, actual processor context guards,
precise interrupts/access faults/illegal instructions, and real Zephyr SMP
six-scalar and nine mixed FP/RVV/VME regions. The strict early-clear IRQ test
uses an owned fixture with a shorter explicitly synthetic peer-clear operation;
the original guest-passing run that lacked that temporal witness is preserved.
Nine regions also pass the captured-CSR profiler with the source policy.

Freeze and verify with:

```sh
python3 pipeline/freeze_source_counter.py --output build/source-counter-frozen-1d521b4a
python3 pipeline/freeze_source_counter.py --output build/source-counter-frozen-1d521b4a --verify
```

This is an isolated source/functional milestone. External memory/coherence/NoC
timing, Rocket frontend coupling, FP/RVV/VME overlap, full knownness, Ethan image
association, calibration and whole-model held-out ±2% certification remain open.
