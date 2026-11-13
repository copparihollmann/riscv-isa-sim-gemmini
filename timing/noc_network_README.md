# Complete Iris on-chip NoC timing component

This component executes the complete configured A/C/D and B/E fabrics of the
saved standalone IrisConfig: 14 router clock domains and 26 TileLink network
adaptors. Its 246 original source modules include the configured routes, queues,
credits, reservations, arbitration, packet conversion, width widgets and source
pipeline registers. The extracted wrapper copies all 40 selected DigitalTop
instances and their original expressions/wires. It adds no link edge or fitted
latency. All peer eligibility, queue heads and grants are computed internally.

This is a timing component for the Spike functional plus causal timing model.
Tile/client CDCs, core/L1 request generation, L2/coherence managers, peripherals
and the serial-TL/DRAM path remain physical external TL boundaries. It is not a
complete SoC simulator or an attestation of Ethan's programmed image. No +/-2%
whole-workload certification or simulated-MIPS claim follows from this work.

## SDK and same-edge scheduling

`build/noc-network-sdk-v1/sdk` contains `noc_network.hpp`, the exact generated
field schema and `libiris_noc.a`. A C++20 client links `-pthread -latomic` using
the recorded compiler/runtime. Public headers expose no Verilator type/state.
The full physical boundary has 208 input fields and 295 output fields. Fields
retain source net names and widths; typed enum IDs and `input_fields()` /
`output_fields()` identify the exact schema. The counts include reset and
source-exposed router debug outputs. No external waiting/eligibility/state
fields exist. Only this exact extracted schema is qualified.

Construct with an explicit random seed; construction does not assert reset.

1. `evaluate(inputs)` holds the shared uncore clock low and settles the complete
   source combinational network. An outer scheduler may revise physical TL
   endpoint inputs and evaluate again while resolving its same-edge fixed point.
2. `sample()` returns settled outputs for that edge.
3. `commit()` advances exactly one shared uncore rising edge, then holds the
   clock low again. Another evaluate is required before sampling/committing.

`step()` is exactly evaluate → sample → commit. It returns preedge outputs, as
sampled by the independent whole-SoC observer. Both fabrics and all adaptors use
the same source sbus fixed-clock/reset nets. The saved harness has a 2 ns uncore
clock period, 500 MHz; the API counts source edges and does not infer time from
host duration. No guessed inter-router scheduling delay is introduced.

Width checking completes before physical inputs are assigned. A failed evaluate
invalidates the pending phase, so an earlier successful evaluation cannot be
committed accidentally. Sampling/committing without evaluate, repeated commit,
and snapshots during a pending evaluated edge are refused. The SDK tests eight
invalid lifecycle paths, including unchanged state/edge count after rejection.

The current native identity is
`9491901c9347368d9d2139b401bf9d19579eabf3604278b5b5c1b1e6021ae106`;
source/tool/API identity is
`9ef3ea5a363ed59cb3a0453390a1599f79e4f4c5d42bf684d4074bf30302d8a9`.
The SDK archive is
`a72640f0ef198ef14a61f9861ff708cf80bebfa9e43f3fd814717c148396a01a`.
Earlier v1/v2 native/source snapshots remain separate historical artifacts.

## Source flow admission and graph

The wrapper checks 51 inner-router input domains against the exact saved Chisel
decoder minterms and global ingress destinations. Unlisted don't-care routes
are refused, rather than assigning them a fabricated known route. Empty source
tables admit no flow. Decoder annotation suffixes are not request indices when
empty tables are present: the generator resolves each decoder input through the
saved FIR's `decoded_plaInput ← addr_N ← io.req[N]` wiring. This matters for
unused C ingresses. B/E ingress width widgets sit inside their clock domains;
checks bind the inner router interface and preserve those widgets.

The external endpoint must still follow its actual TL protocol/address/source
contract. Routing guards do not certify arbitrary invalid upstream bus traffic.
The model uses explicit two-state numeric physical inputs; inactive fields and
unknown architectural operand data are not inferred to be known zero.

`noc_network_graph.py` exports all 40 macro nodes, 1,091 source signal edges,
native storage shapes and actual endpoint handshakes. The graph records source
module hashes/lines, wire widths and connection expressions. Edge annotations
say zero **added** latency; all actual queue/route/widget latency stays in the
source nodes. Counts are endpoint TL beats on both entry and exit, not physical
link flit counts or payload-byte bandwidth. The coherent guest exercises 2,240
B/E endpoint handshakes and 20,074 A/C/D handshakes.

## Independent reference and validation

The independent oracle is a separate complete whole-SoC build, with unchanged
saved RTL logic and selected DigitalTop data/reset wires marked `public_flat_rd`.
No clock is made public by that control file. This exposes all 503 physical
boundary fields directly, without reconstructing missing data or inventing zero
values. The observer reads settled values before each actual uncore edge. It
also preserves the earlier memory/NoC/VA and node5 observations. One old async
sink alias was optimized into its direct physical top-level valid wire; that
observer expression is replaced using the exact source connection, not a timing
approximation. The first failed compile and its diagnostics are preserved.

The reference archive and all source hashes, visibility control, compiler flags,
preload implementation, compact CRT/ELFs, raw logs and coherent TSI signatures
are captured. The preload/compact CRT is functional-reference infrastructure;
it changes load/startup timing and is not silently treated as FPGA calibration.
The saved FIR is
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
It uses native FIRRTL memories and a two-state Verilator 5.052 harness. Source
association with the current Chipyard checkout or loaded FireSim image remains
unverified. Original references/capsules, primary Spike and the shared timing
engine are untouched.

Five continuous replays start at TB 3 under physical reset and import no internal
snapshot: 308,777 edges and 41,870,177 defined physical signal comparisons.

| Guest | Edges | Whole-SoC architectural control |
| --- | ---: | --- |
| Original 9 vector memory | 64,999 | Bounded incomplete at TB 130001; original 3,929 memory/100 NoC/15,500 VA/15,500 VA2 lines unchanged |
|8-operation control | 60,242 | All 3 done; hart 2 checks 64 |
|9-operation fenced control | 62,562 | All 3 done; hart 2 checks 72 |
| Peer/local/nonlocal plus dirty eviction | 46,072 | All 3 done; hart 2 checks 72 |
| Three-core coherent publish/consume and private dirty eviction | 74,902 | All 3 done; 84 independent checks on each hart |

The new guest uses all real cores, cross-tile TCM0/1, scratchpad, conflicting
private DRAM lines, and three owners of one coherent cache line. Expected data
comes from independent formulas, not from copying another observed result.
Successful mailboxes are parsed from coherent TSI signatures. The bounded
original stall is evidence about this saved reference, not infinite deadlock or
a deployed FPGA fault.

Explicit phased stepping matches ordinary step byte for byte over 60,242 actual
edges. Seven repeated evaluations per edge match over 74,902 edges. The direct
SDK additionally flips all 24 external endpoint-ready inputs, settles, restores
the original inputs and settles again before each commit: 135,144 actual edges
retain identical outputs. An active-traffic snapshot after 45,000 edges restores
with constructor seed 42 and reproduces the remaining 19,999 output rows exactly.
Changed source identity is refused before model-state deserialize. Snapshots
are same-build trusted component artifacts; external actors/TL future inputs
must be saved or reproduced separately for a whole-system restart.

The independently handwritten local FIFO/arbiter model is rerun unchanged and
projected onto full-network node5 VA/SA counts for 52,806 common edges, 105,612
checks. This is an independent local subset cross-check, not an independent
handwritten implementation of every other router. Five data/source/ready/debug
corruptions are detected. Finite traces do not exhaust every legal flow/state.

## Build, replay and speed

The build scripts refuse existing output directories. Fresh reproductions use
new names; preserve all existing receipts.

```
python3 timing/noc_network_extract.py --output build/new-network-source
python3 timing/noc_network_routes.py --source build/new-network-source --output build/new-network-guarded
python3 timing/noc_network_build.py --source build/new-network-guarded --output build/new-network-native
python3 timing/noc_network_sdk.py --model build/new-network-native --output build/new-network-sdk
```

This recipe is for the checked-in exact schema. A changed interface requires a
new generated API schema and explicit qualification. The complete source/tool/
schema identity changes visibly; no old timing certification is inherited.
For the frozen build, `noc_network_check.py` compares raw physical output rows,
and `noc_network_accept.py` joins independent signatures, preserved transcripts,
phase/lifecycle/snapshot tests, handwritten projection and benchmark digests.

The SDK benchmark times source stepping plus output stores, with parsing,
digest computation and all text I/O outside the timer. Seven full-reset repeats
measure approximately 109–110 thousand complete-fabric edges/second, about 9.1 µs
per edge on this host. Every defined output digest matches the independently
parsed whole-SoC trace. Same-edge readiness revision is a separate correctness
mode and has its own cost. These are component throughput/host costs, not SoC
MIPS or target frequency. No idle skipping, sampling or fast-forward is used.
