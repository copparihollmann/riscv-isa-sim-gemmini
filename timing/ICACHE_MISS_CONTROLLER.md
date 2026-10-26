# Selected demand I-cache miss controller

`cpu.instruction_miss_service` selects the Rocket ICache/Frontend local demand
path around the existing original V10 finite LLC admission. It requires the
selected 64-byte line, 128-bit four-beat refill, latency-two ICache, no ITIM,
and two-entry non-flow/non-pipe tile A/D queues. Source and FIR hashes are
explicit model inputs. No target or latency is selected by default.

ICache.scala338–385 detects the demand miss after its two lookup registers.
TilePRCIDomain's selected CPU A queue adds its original registered handoff before
the LLC may classify/admit this request. Native MemorySystem suppresses only
the original private I$ miss lookup price, before recursive lower-service joins;
all original lower requests, bytes, source identities and finite credits remain.

The existing source response owner returns its actual final original LLC beat.
The tile D queue hands it to ICache on the following edge. ICache.scala394 and
431–452 prohibit a same-edge lookup during that refill write and publish the
valid tag on the following edge. A fresh latency-two lookup then supplies the
CPU fetch token. These transitions are actual posted events with one original
controller identity, not an additional DRAM request or a completion estimate.

One I$ demand refill is outstanding. In the no-ITIM selected path, D.ready is
always asserted; the four original beats are accepted at most once per edge.
The two-entry tile queue therefore cannot fill from this sole demand stream:
its registered final-beat handoff suffices for local replay readiness. Original
LLC response actors retain every actual beat and their own backpressure. A
second demand or duplicate response identity fails instead of creating capacity.

This is the demand controller domain of the existing committed-instruction
observer. Speculative Frontend/FQ/predictor state, competing in-flight CPU data
responses and frontend replay phase relative to speculative requests remain
outside this local closure; this selection does not assert their timing is
fully modeled. The admitted path preserves the existing explicit translation
policy. The focused test checks actual request admission, final-beat/replay
publication, arbitrary delayed lower response, original single-request capacity
and repeated-identity refusal.

A redirected 32-bit instruction at the final halfword may need two cold aligned
fetch blocks. These are two original I$ line Gets, each with its own original
LLC source ownership. The native consumer clips the actual useful fetch-byte
interval at the line boundary and admits the second only after the first
controller's replay response. One architectural instruction and its original
PC/bits remain, and no second simultaneous I$ refill credit is created. It does
not apply this split to a DMA packet or to any other original transaction.
