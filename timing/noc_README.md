# Source-derived native NoC arbiter component

`noc_arbiter.hpp/.cpp` implement the three proved arbitration stages as a reusable
C++20 component. A call advances one source uncore clock edge. Parameters are
required: input VCs, router input units, flattened output VCs and the local input
index. The qualified node5/input0 profile uses6/4/13/0, with direct source and
frozen-fixture citations in `noc_sources.json`. There are no inferred latency,
clock-rate or board defaults. This implementation represents widths1..63 and
refuses unsupported widths or inconsistent eligibility inputs.

The component retains three masks and implements the source contracts:

- Inner input-VC selection uses the first request after the mask, wrapping to
  the first request. It advances its mask on a valid attempt, including when
  the router does not accept the request. A route completion overrides this
  update with `(1 << source_vc) - 1`.
- SingleVCAllocator selects an eligible input unit and advances its mask when
  any eligible input exists. Its supplied eligibility already excludes occupied
  output VCs.
- ISLIP selects an eligible output VC and updates its mask only when an
  allocation is accepted. Output grants are zero when there is no input winner.

`preview` computes outputs without changing state; `step` commits all three next
masks together. Source reset state is explicitly zero. Live replays seed once
from an observed snapshot and carry computed state afterward.

## Verification

Run `python3 timing/noc_check.py` once to create a new closed evidence directory,
or pass `--output <new-directory>`. Existing evidence is never overwritten.
`python3 timing/noc_check.py --verify` checks the frozen inputs and reruns every
saved native invocation. Neither operation uses an FPGA.

The original99 consecutive actual-RTL cycles provide297 stage transitions.
Both per-row testing and a continuous replay pass. The continuous input contains
only one state seed; replacing every later observed state with zeros does not
change its serialized input. Five corrupted grant or next-mask goldens are
rejected.

A new read-only host observer adds the previously omitted route and complete
allocator inputs to the same frozen Verilator model and guest ELF. Its3929
vector A/D events,100 full router frames and both15500-frame compact streams
match the original frozen transcripts exactly. The complete boundary yields
15499 consecutive transitions at each of the three stages (46497 stage
transitions). The native model starts at TB99001, carries all masks continuously,
and matches every output and next state through the last comparable transition
at TB129997. The final frame at129999 supplies that transition's next state.
No missing external mask-state update was found within this captured boundary.

The extra capture was necessary: the older long compact trace did not contain
route completions or all global allocator eligibility inputs. Replacing those
missing fields with assumed values would not establish a closed replay. Queue,
routing, reservation and other packet state still enter through explicit
external inputs; the mask-state replay does not certify those components.

## Finite starvation reproduction

A second native replay uses the captured finite local-egress free slots and
arbiter-ready arrivals. These arrivals are requests becoming ready at the
queue/route boundary, derived from rising ready bits, not guessed packet traffic.
The replay seeds a pending mask once, adds new arrivals, and removes only the
request selected by its own computed grant. It never injects the observed
per-cycle pending mask; that mask is only a comparison oracle.

From TB99367 through129999,15317 native edges reproduce every observed waiting
mask and inner selection. The local egress opens1532 times, every20TB (10 source
uncore cycles), and grants incoming VC1 and VC2 exactly766 times each. Initial
waiting mask61 plus766 new VC1 and765 new VC2 ready arrivals suffice. VCs0,3,4,5
remain pending and get no grants, matching the queued response headers
564,574,573,575. This explains why upstream response556 remains blocked in the
saved RTL observation. The observed free-slot period is stimulus, not a fitted
latency parameter.

This isolated-egress reproduction excludes other router traffic and derives
local output eligibility from its supplied free-slot and pending-request inputs.
The complete three-stage replay separately uses the actual full eligibility
boundary. Both are finite evidence. They do not establish infinite starvation,
global deadlock, deployment-image equivalence or a hardware fault.

## Scope and integration

The public C++ API accepts masks after queue, routing and occupancy filtering.
The graph timing model must supply those masks from dynamic state and preserve
the update order. A mean latency or a policy that advances inner arbitration
only on acceptance would erase the observed behavior.

Queue occupancy, route computation, VC reservation/free events, credits,
packet/flit ownership, NoC links, clock crossings, cache banks and serial memory
remain future integration work. This component is isolated from the shared
timing engine and primary Spike package. Whole-NoC qualification, deployment
association and timing calibration remain false. The preserved standaloneRTL
uses two-state Verilator, native FIRRTL memories, explicit FESVR preload and a
compact CRT; unknown reset effects remain outside its certification scope.
