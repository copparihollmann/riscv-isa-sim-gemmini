# Source-backed UART helper

The Ethan FireSim target replaces the base UART with **256 TX and 256 RX entries**
and requests a baud rate of 3,686,400. The saved elaboration confirms both
`Queue256_UInt8` instances, nine-bit watermarks, a 64-bit control port, and divisor
reset `0x87` (135). These are distinct from the base `UARTParams` defaults of
eight entries. See [the frozen source evidence](uart-source-evidence.json).
The relation between this local elaboration and the deployed image remains
unverified.

`UartRegisters` takes explicit FIFO depths, reset divisor and bus beat width.
It implements the source register masks, TX full and RX empty flags,
nonblocking overflow drops, TX bit-31 write suppression, partial transactions,
watermark comparisons and IRQ enables. Nine-bit watermarks require both bytes
of their field to be written; writing just byte `0x0a` or `0x0e` has no effect.
The divisor likewise requires a complete sixteen-bit field write.

TX queue acceptance depends on `txen`, while writes can queue data when TX is
disabled. Clearing `txen` during a frame does not cancel it. The explicit
`advance_tx_cycles()` API follows the source TX shifter, prescaler and stop-bit
counter in **UART target clock edges**. The host must establish that clock's
mapping to the global model; neither retired instructions nor wall time are a
substitute. Source-default `uart_tx=1` is assumed; the simulation speedup override
and optional printf side channel are outside this helper.

RX framing is an explicit boundary: a frame may start only when RX is enabled,
and a frame already started can finish after RX is disabled. UARTRx pin sampling,
debounce, oversampling, noise and errors are not implemented. Simultaneous
TileLink and FIFO edge arbitration must be provided by the integrated board
scheduler; these helpers commit a supplied transaction in call order.

The RX queue's RAM is **not reset**. At reset, an empty-status-byte read is
defined, while its data byte is unknown. A fullword initial RX FIFO read therefore
fails with `IRIS_UART_UNKNOWN_RX_DATA`; the helper does not silently zero that
storage. Once a cell has been written, its stale value remains visible when the
read pointer selects it, including while empty. Integrating a driver that polls
fullword empty reads needs an explicit treatment of unused/undefined data bits
or evidence of image memory initialization. The current helper does not certify
that driver interaction.

Run `python3 board/run_uart_tests.py`. Ten tests cover the 256-entry boundary,
watermark width and byte strobes, overflow/order, enable transitions, unknown and
stale RX data, IRQ callbacks, serial TX waveform/stop bits, and a divisor update
during a frame. The receipt binds compiler, helper/tests, source snapshots, the
available full FIR artifact, and output digests. This helper is not yet installed
in the Spike console plugin; no full-board, Zephyr or RTL timing certification is
claimed.
