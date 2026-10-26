# Original upstream RoCC command router

Selected LazyRoCC.scala400–419 instantiates `RoccCommandRouter` with its own
`Queue(io.in)` (default depth two, non-flow, non-pipe). RocketTile.scala251
connects core RoCC commands to that router; each Gemmini command leaves through
its selected output. The selected FIR has `RoccCommandRouter.cmd_q` of
`Queue2_RoCCCommand`.

This is upstream of Gemmini's raw command queue, LoopConv's command queue,
LoopMatmul's command queue and final unrolled queue. Those four original Queue2
instances remain unchanged. `source_rocc_command_router=1` requires the exact
upstream Queue2 facts and inserts that missing original owner before them. No
selected hardware capacity is changed and no new virtual response/latency price
is assigned. Without this selection the earlier four-queue adapter is retained.

One original CPU command keeps its PC, instruction bits and register operands
through all five queues. Non-flow visibility takes the next edge. A full
non-pipe destination cannot reuse a same-edge dequeue credit. Scalar source
admission stalls at the actual upstream queue, and fence drain retains all five
queues. The component test verifies both adapters, five actual registered
boundaries, the ten original downstream slots under pressure, the eleventh
command's real release and every original command's FIFO identity.

This models primitive command transport only. It does not expand LOOP_WS,
assign loop duration, model a scalar out-of-order window, or close Rocket's
remaining core pipeline/branch predictor behavior.
