# Live Shuttle counter overlap

The fourth isolated candidate is native
`e0600503a0fdf0fe3391619273fe583715c64f79d08b099d6b8c35b24adf8c26`,
with clocked UART
`a531fe309cf3d6b2577bc30a6b57baf40f6a192f26d5d79eaeada24f095b2c22`.
It derives from frozen893 without changing the primary5e6 simulator. The source
worktree is `pipeline/riscv-isa-sim-counter-pipeline`; its build is
`build/spike-counter-pipeline-v1`. The explicit new fixture domain is:

```
shuttle_pipeline pure-integer-rvc-counter-sequential-frontend
```

The previous32-bit and mixed16/32-bit domains retain their behavior. The new
domain additionally admits only32-bit CSRRS/CSRRC rs1=x0 and CSRRSI/CSRRCI uimm=0
on B00/B02/C00/C02 on Shuttle0/1. All other CSR forms and hart2 use the guarded
conservative path. This does not add unrestricted CSR or system speculation.

## Source stages and hazards

Pinned Shuttle `a536ed1df91a0f65770e36758291d02a8cb929c4` provides the rules:

- `src/main/scala/exu/Core.scala:444-487`: CSR is pipe0-only and youngest
  within a packet. It can enter RRD behind older packets.
- `Core.scala:542,675-680`: CSR in EX stalls while older MEM/COM or the FP
  scoreboard is busy; EX stall blocks all RRD. The current domain has no
  asynchronous FP/vector work and uses the explicitly empty scoreboard fixture.
- `Core.scala:1082-1089,1152-1155`: CSR read data becomes valid and bypassable
  at COM. `Core.scala:1273-1303` retains the later WB RF write/bypass stage.

The actual source snapshots and complete repository SHAs are retained in the
independent CSR proof and closed893 prerequisite. The new patch cites the same
unmodified source. No source-build/Ethan-image equivalence is claimed.

For RRD acceptanceR and hart periodD, EX normally advances atR+D. For a counter
read, it advances at the later ofR+D and one edge after the last older COM edge.
That explicit EX holding interval blocks younger RRD. MEM and COM follow the
release edge; read data is ready at COM, with WB one edge later. The graph emits
a positive-duration EX hold node and a COM operation that also serves as the
result-ready node. It never emits a zero-duration operation or an early fake
result. Each instruction retains its own PC, packet, lane, dependencies and
retirement event.

The source counter policy from [COUNTER_POLICY.md](COUNTER_POLICY.md) samples
pre-edge state at the owning COM edge. Architectural retirement remains separate
from visible minstret. Precise interrupt capture waits for a source-legal RRD
edge, including EX stalls, and completes behind older instructions.

## Verification

`pipeline/check_counter_pipeline.py` emits32 independent cases on all3 harts
and checks192 actual CSR reads. It proves64 dependent operations consume their
CSR producer at COM before WB,32 independent scalar operations overlap a CSR,
and32 back-to-back pairs hold EX and separate their COM reads by3 core edges.
It checks pipe0/youngest restrictions, no younger RRD during EX hold, positive
event durations, actual guest arithmetic and two corrupted-data/schedule controls.

The source forms corpus checks all16 admitted counter encodings and verifies
that nonzero operand fields and Rocket reads remain outside the new pipeline.
Existing pipeline IRQ/timer/TCM-fault precision, native context/halt/trigger
guards, source pairing, compressed/base integer oracles and seeded replay pass.
Live8+3, memory6+7, UART12, nonlinear writes/wrap/inhibit, off-hart memory
response→counter edges, unchanged32 functional goldens and real3-hart Zephyr
scalar6/mixed9 regions pass. The captured-read profiler joins all9 mixed regions.

The original256 probe and alias control are debug/fitting evidence. This
implementation reproduces their Shuttle visible cycles and physical read spans
exactly: dependent B00=263, independent B00=136, aliases264/137 and physical
spans264/137. These result from source stages and EX hazards; no fixture timing
number or boundary offset changed. Rocket remains777 modeled versus259 actual
cycles under the conservative fixture (+200%). Full timing certification and
held-out +/-2% remain false.

The separate component validation plan
`build/scalar-component-validation-plan-v2/plan.json` freezes empty, odd and
larger bodies before model predictions or RTL observations. Freeze this native
and all gates first, record predictions against that immutable binary and the
exact ELFs, then run the RTL references. These component checks do not replace
the untouched final Merlin/Miles held-out gate.

## Review and reproduction

The review delta changes only `iris_shuttle_issue.cc`, `iris_timing_adapter.cc`
and `iris_timing_adapter.h` relative to893. It is
`build/counter-pipeline-v1-review/counter-overlap-on-893.patch`, SHA256
`6357c0c5bf7a2baf25081d3bef6a2c66104e80d9d21a82fd74db1cd5569e2f89`;
`git apply --check` passes on the exact893 source. The full overlay from pinned
Spike729 is
`9f9809291c60fde3663d2bb4425acba7b912df5401d008a81798fcc62cc72bcd`.
The closed epoch is `build/counter-pipeline-frozen-e0600503`.

```sh
python3 pipeline/build_native.py --source pipeline/riscv-isa-sim-counter-pipeline --build build/spike-counter-pipeline-v1
python3 pipeline/check_counter_pipeline.py --output build/counter-pipeline-new-directed
python3 pipeline/freeze_epoch.py --snapshot build/counter-pipeline-frozen-e0600503 --verify
```

Frontend prediction/cache state, branches/replay, broader scalar and Rocket
pipelines, vector/VME overlap/shared resources and calibrated memory still need
implementation. The model continues to refuse unknown required behavior rather
than assigning fabricated timing. Primary publication remains coordinated.
