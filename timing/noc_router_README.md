# Causal node5 return branch

`noc_router.hpp/.cpp` extends the qualified arbiter into one real node5 return
branch: input0 from node4, six input VCs, and the local NIF3 egress. It computes
FIFO contents and pointers, VC state, waiting requests, VA grants, switch packet
locks/masks, output reservation, egress FIFO occupancy, credit returns and every
valid output flit. The fixed source-qualified profile and citations are recorded
in `noc_router_sources.json`; no latency or capacity was fitted.

The source input FIFOs have five entries each and are neither flow-through nor
pipelined. The egress FIFO has two entries, is flow-through, and supplies a switch
credit only while completely empty. The output reservation releases when a tail
flit is switch-allocated; a new allocation wins if release and allocation coincide.
Newly allocated VCs enter switch allocation on the next edge. The input switch
retains a packet lock until its tail and rotates its mask on idle cycles as the
source specifies. The existing `noc_arbiter` implements all three VA masks.

## Continuous real-RTL validation

One snapshot at TB90001 initializes the native state. Subsequent input records
contain physical accepted-flit arrivals and data, NIF3 downstream ready, peer VA
requests and route-completion inputs. Observed FIFO state, waiting masks and
egress availability never enter another native step; they serve only as goldens.
The snapshot contains only explicitly captured state; inactive FIFO payloads are
not treated as defined architectural data.

The read-only observer obtains accepted data from the just-written input FIFO
slot after the clock edge and binds it to the pre-edge valid/VC/enqueue address.
It refuses a valid arrival without a real FIFO enqueue. This is the accepted
external flit, not an injection of queue state into the model. Other snapshot and
output values come from the old stable pre-edge frame. The RTL model is unchanged.

The native model matches all compared states and outputs continuously for:

| Actual RTL guest | Native edges | Incoming flits | Consumed output flits |
| --- | ---: | ---: | ---: |
| Original unfenced9, bounded incomplete run | 20000 | 8084 | 8059 |
|8-iteration control, actual RTL success |15243 |347 |347 |
|9-iteration load-fenced control, actual RTL success |17563 |457 |457 |

The original case retains25 flits in its input/egress queues at the observation
boundary. Its waiting VCs and starvation arise from native FIFO, switch, credit
and reservation state, rather than a recorded waiting/free-slot waveform. The
passing controls drain the observed traffic. Both actual passing guests provide
coherent TSI signatures with all three harts done (64/72 checks on hart2).

The native driver carries every modeled state between edges. Source-derived
unit cases check flow-through bypass, downstream stalls, reservation allocation
while the old tail remains buffered, delayed switch eligibility and returned
credits. Invalid flow, profile, peer-local contention, FIFO and route boundaries
fail closed. Corrupted goldens are rejected.

## Scope

This is a local return branch, not the complete four-input, three-output router.
Other input machines and forwarding outputs supply explicit external peer VA
requests. All captured input0 flits target node5/egress0, and no peer requests the
local egress during these windows. The model refuses a nonlocal physical input
flow or a peer local-egress contender. Captured peer requests may depend on
unmodelled forwarding reservations; they are an explicit component boundary.

Source route-completion transitions accept an external result, but these local
return traces exercise no route requests. The routing relation and nonlocal
forwarding, network-output reservations/credits, peer input queues, NoC links,
endpoint/CDC state and cache/serial memory remain future integration. Whole-router,
whole-NoC, deployed-image and timing calibration claims remain false. This code
is isolated from the shared timing engine and primary Spike library.

The underlying reference remains the saved standalone IrisConfig FIR with native
memories, two-state Verilator, explicit native-RAM FESVR preload and the compact
CRT. Unknown reset effects have not been proved irrelevant, and it is not bound
to Ethan's bitstream. No FPGA action or RTL repair was performed.
