# Selected zero-fill local writes

`source_zero_writer=1` selects SP and overwriting ACC, repeat1 paths of the selected Gemmini
ZeroWriter. It requires DIM16, byte elements, first-layer PixelRepeater enabled,
one ZeroWriter request register, one PixelRepeater register, and max columns64.
The original zero pointer sentinel does not enter StreamReader, translation,
TileLink, cache lookup, or DRAM. LoadController issues each original row even
when its configured external stride is zero.

The request register emits masked DIM-sized column bands at block-stride local
addresses; PixelRepeater registers each band before the local write. Either
register can replace on its final output handshake. A held upstream request is
software custody of the LoadController's single ready/valid owner. It is not an
extra hardware queue. The two hardware registers remain bounded under stalls.
Zero local writes arbitrate after execute and ordinary DMA local writes. Any
valid final normal scaler output also suppresses zero writes, including one
headed to a different local bank. Local row publication follows actual SP write
acceptance by one edge, or ACC acceptance by two edges. ACC pixels hold their
original register until the physical bank arbiter accepts them. ACC masks expand
each input lane into four byte enables; useful-byte accounting uses ACC width.
The final local fire returns the original response; registered command tracking
completes on the next edge. Independent pending-row publications remain owned
through a fence even when command tracking has completed. Masks are retained per
original local fragment.

The supported domain is SP or overwriting ACC, columns1–64, rows1–16, pixel
repeats1. Accumulating ACC zero writes, shrinking ACC zero writes and repeated
pixels remain unsupported. Shrinking would allocate input-width tracker bytes
while Scratchpad's zero response reports accumulator-width bytes; no matched
allocation/return protocol is established for that combination. The functional extension is not
changed.

Selected source content pins:

- ZeroWriter.scala: `cc8adef645cb46a6152a74fbfed2e16cb144082910a09b21a60f48d34099c3ac`
- PixelRepeater.scala: `172347ac6c9737d03ed379c73bfdf360d1c9919f94fa5c5fd9f310437b6a31f7`
- LoadController.scala: `780ee0a292d8653fa8a822aee28e2fb2cffbc25301431b4332182008d34fcf6a`
- Scratchpad.scala: `e4d3a12c700fe9edaf5c2ce2f283ec5233a98bd103fb04054160e8097cb89a4f`
- DMACommandTracker.scala: `a0fbc60a1cdd4f58636a3aafed630f5bec106176fa3e5b57ce028321ac73e0b6`

`posted_zero_writer_test` checks register visibility, same-edge replacement,
backpressure and retained masks. `posted_zero_load_test` verifies no memory
request is made and PRELOAD waits for the actual pending zero-filled weights.
`zero_accumulator_load_test` checks both physical-port and conservative-port
domains, partial and multi-band masks, ACC publication, byte accounting, and
retained unsupported accumulating/repeated-pixel mappings.
