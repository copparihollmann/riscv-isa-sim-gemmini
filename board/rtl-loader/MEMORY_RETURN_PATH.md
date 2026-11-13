# Saved-RTL return-path allocation observation

The nine-iteration, hart-2-only vector-memory reduction reproduces a bounded
NoC allocation starvation mechanism without FP arithmetic. No RTL was changed.
The FPGA was not contacted. The older frontier, packet and selected-vector
capsules remain unchanged.

The exact guest ELF is SHA256
`987e5e3691959520351086fdd9761ffbbbe4d50511e4af047ca70c825158280d`.
The saved standalone IrisConfig FIR is SHA256
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
This is distinct from the saved FireSim combined FIR and is not associated with
Ethan's loaded image. The run uses Verilator 5.052, native FIRRTL memories,
explicit native-RAM FESVR preload, the compact CRT and seed1/reset2. Four-state
undefinedness is unavailable; unknown reset effects have not been proved
irrelevant. Bounds below are testbench cycles (TB), with two TB per 500MHz
uncore cycle.

## Exact request and response

| Boundary | TB | Source |
| --- | ---: | ---: |
| Vector reader accepts Get32 at 0x80003940 | 99057 | tag12 |
| Rocket asynchronous master crossing accepts A | 99081 | 44 |
| NoC master3 accepts A header | 99081 | 556 |
| L2 bank1 accepts Get32 | 99117 | 556 |
| L2 bank1 emits D header | 99133 | 556 |
| L2 bank1 emits four D data flits | 99135–99141, step2 | 556 |
| Node3 input VC1 contains response header | 99139–99141 | 556 |
| Node4 input VC0 contains response header | 99143 onward | 556 |

The reader is input0 of `TLXbar_i2_o1_a35d256s6k4z4u`: its source ID gains bit5,
so tag12 becomes44. Rocket's tile master xbar preserves that six-bit source.
`TLAToNoC_3` adds 0x200, giving556. An earlier exploratory inference reversed
the reader/writer source banks and incorrectly gave524; the final reader and
source citations use556.

All five L2 response flits pass ready/valid. Source556 never reaches the
Rocket-side NoC return adapter during the130000TB run. The response is intact,
not dropped: for15428 consecutive observed uncore edges, TB99145–129999,
node4/input-from3/VC0 holds its header at queue slot3, valid and in state2
(`g_v`, waiting for VC allocation). Routing permits only outgoing port1/VC0.
It receives no grant. That outgoing VC opens at99159,99199 and99339; other
incoming VCs take all three slots, after which a downstream reservation holds it.

## Downstream phase lock

At node5/input-from4, VCs0,3,4,5 retain response headers564,574,573,575 and remain
in allocation wait throughout TB99367–129999. The local egress becomes available
1532 times, first99379 and last129999, exactly every20TB (10 uncore cycles).
Every such slot selects and grants incoming VC1 or VC2,766 times each. The four
waiting VCs receive zero grants; their attempts occur when the egress is occupied.
The held downstream VC0 therefore blocks node4's response556.

This matches the source arbitration contracts. `InputUnit.scala` advances its
internal round-robin mask on a valid attempt even when the request is not
accepted, while `SingleVCAllocator.scala` first filters occupied output VCs.
The reader independently reconstructs all15500 observed inner selections from
waiting masks and prior masks. The result is bounded, phase-locked allocation
starvation sustained while later responses/reissues continue. It does not prove
infinite starvation, global deadlock, a deployed FPGA fault or the irrelevance
of the host/native-memory/initialization conditions. No speculative fix was
applied. In particular, replacing this behavior with a fitted mean memory
latency would lose the observed interaction.

## Controls and reusable reference vectors

The same new path observer runs the eight-iteration control successfully with
64 checks on hart2 and all three harts done. The nine-iteration original ELF
passes72 checks with the separately built HTIF idle4096 adapter. A changed ELF
that fences the three operand loads also passes72 checks with baseline polling.
These are finite controls, not a general fix. HTIF backoff changes traffic and
phase; fences change guest execution and timing.

All sampled vector A/D transfers match the frozen original packet transcript
exactly across the path, router, and two VA observer variants. Their overlapping
full router and compact VA frames also match exactly. New instrumentation only
reads public generated state and logs old stable values when the actual source
clock rises; it does not write RTL state.

`noc_transitions.py` extracts99 consecutive actual-RTL transitions, TB99121–99319,
for node5. Each covers three stages: inner input-VC selection and next mask,
router input arbitration and next mask, and ISLIP output-VC selection/grants and
next mask. Inputs include the observed post-routing/occupancy eligibility masks;
this is not a complete NoC model. An independent integer implementation checks
all297 stage transitions and rejects five grant/mask corruptions. The future
graph NoC adapter can consume `noc-arbiter-transitions.json` directly. It must
preserve dynamic queues, reservations, mask updates and traffic phase.

Run `python3 board/rtl-loader/memory_path.py --verify` for the closed capsule and
`python3 board/rtl-loader/noc_transitions.py --input <capsule>/build/rtl-loader-diag/noc-arbiter-transitions.json`
for the standalone transition contract. The capsule records exact binary,
ELF, generated-source, host-library, observer-source, transcript and source pin
hashes. Constellation's inspected checkout is clean at
`c1b42cd0c7c7d6e4fc1ed9bf1f86fbd3b31ac510`; generated HDL and the saved FIR,
not that fact alone, bind the observed design.
