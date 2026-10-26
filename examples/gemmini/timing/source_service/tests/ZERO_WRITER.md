# Selected zero-fill local writes

`source_zero_writer=1` selects the SP, repeat1 path of the selected Gemmini
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
acceptance by one edge; original pending-row tokens and command completion are
retained. Masks and useful bytes are retained per original local fragment.

The supported domain is SP-only, columns1–64, rows1–16, pixel repeats1. ACC zero
writes and repeated pixels remain unsupported. The functional extension is not
changed.

Selected source content pins:

- ZeroWriter.scala: `cc8adef645cb46a6152a74fbfed2e16cb144082910a09b21a60f48d34099c3ac`
- PixelRepeater.scala: `172347ac6c9737d03ed379c73bfdf360d1c9919f94fa5c5fd9f310437b6a31f7`
- LoadController.scala: `780ee0a292d8653fa8a822aee28e2fb2cffbc25301431b4332182008d34fcf6a`
- Scratchpad.scala: `e4d3a12c700fe9edaf5c2ce2f283ec5233a98bd103fb04054160e8097cb89a4f`

`posted_zero_writer_test` checks register visibility, same-edge replacement,
backpressure and retained masks. `posted_zero_load_test` verifies no memory
request is made and PRELOAD waits for the actual pending zero-filled weights.
