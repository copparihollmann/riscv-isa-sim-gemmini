# Source-backed Iris UART integration candidate

This separate db964-derived build connects the audited `board/iris_uart.hpp`
register/FIFO/TX state to actual Spike processes. It leaves the primary native,
legacy plugin and helper untouched. The only helper extension is a read-only
next-TX-event query, applied to a private copy by the builder.

The frozen Ethan elaboration supplies256 TX/RX entries,9-bit watermarks,
reset divisor135,8-bit data and a64-bit control port. The actual elaboration
frequency summary names `uart_clock` at500MHz. Full source revisions and hashes
are in `board/uart-source-evidence.json`; this does not attest the deployed image.

The optional independent native clock interface leaves the existing abstract
device ABI intact. Live progression passes absolute before/after ticks and the
explicit modeled base frequency. Conversion uses integer rational arithmetic:
UART edges=floor(model_ticks×500MHz/base_hz). Thus a100MHz synthetic fixture
advances5 UART edges per base tick; it is never reported as a physical500MHz
core. RTC callbacks do not advance the UART again in live mode. Functional-only
mode derives UART progression from the modeled500kHz RTC; its instruction-based
time remains approximate. Device deadlines let all-WFI cores wake for UART IRQs
without relying on a CLINT timer.

The plugin requires native `iris_device_clock_abi_v1`; an old native fails at
load/parse instead of silently using coarse ticks in live mode. It accepts the
existing `sifive_uart` device name and audited address/source1, with the existing
Iris ROM/DTB and memory map. It delivers console bytes when the source TX counter
becomes idle, preserving finite FIFO backpressure and TX enable behavior.

RX is deterministic frame-boundary stimulus, not a pin sampler or implicit host
stdin source. Set `IRIS_UART_RX_FRAMES=/absolute/file`; each non-comment line is
`start_uart_cycle completion_uart_cycle byte`, with unsigned decimal/hex values,
strictly ordered nonoverlapping frames and an8-bit byte. Frames starting while
RX is disabled are dropped; accepted frames can complete after RX disables.
UARTRx synchronization/debounce/oversampling remains unmodeled. Initial FIFO RAM
is unknown: an empty fullword RXDATA read fails closed, while a status-byte read
at offset7 is defined. Ordinary fullword empty-poll drivers require broader
undefined-bit tracking before they can be qualified; no known zero is invented.

Build from the frozen matching db964 SDK and explicitly recorded worktree:

```sh
git -C third_party/riscv-isa-sim worktree add --detach \
  "$PWD/third_party/spike-uart-dev" 72958551566a30f19444bd7e354552824e4d0a98
git -C third_party/spike-uart-dev apply "$PWD/board/uart-device/native-overlay.patch"
git -C third_party/spike-uart-dev add -N .
python3 board/uart-device/build.py
python3 board/uart-device/check.py --output build/uart-device-qualified-check
```

The builder reuses byte-identified matching native objects, recompiles the
changed simulator translation unit, relinks separately and builds a separate
plugin. Its receipt records compiler, object/library/config/source hashes,
commands and outputs; mismatched source/SDK inputs refuse the build. Primary
publication remains a separate coordinated step with a full native rebuild.

Selected tests cover the original10 helper cases plus9 clock/adapter/drain
cases;12 real three-hart process cases; and refusal of an old-native/new-plugin
pair. Processes exercise FIFO256 boundaries, raw byte order, nonblocking drops,
9-bit watermarks/full-field strobes, TX/RX interrupts from WFI, empty unknown
RX refusal and defined status polls. Both100MHz synthetic and500MHz source
clock fixtures are tested. Scripted frames test RX enable/completion behavior.

Actual scalar Zephyr and mixed scalar/VME/RVV images passed. The mixed live
fixture passed nine measured regions with a larger30M-cycle budget; the old10M
budget correctly ran out while serializing output. Actual LLVM23 GEMM with two
compute workers and a concurrent hart-2 producer passed all12,288 int32/W8A8
values per shipped/twin image. UART115200-baud serialization makes these large
acceptance outputs materially slower; no hidden output speedup is used.

Receipts: `build/uart-device/build.json`,
`build/uart-device-qualified-check/results.json`,
`build/uart-zephyr-scalar/results.json`,
`build/uart-zephyr-mixed-live-final/results.json`, and
`build/uart-compiled-gemm-h2-final/results.json`.

Before replacing the primary plugin, completion paths must explicitly drain
UART output. Set the9-bit TX watermark to1 while retaining TXEN/nstop, poll
TXWM until FIFOempty, then wait for the possible in-flight frame. With unchanged
settings, `(11+nstop)*(DIV+1)` UART edges conservatively includes a full final
stop interval. With arbitrary prior DIV/nstop changes, use
`65536+11*(DIV+1)` edges: an old16-bit prescaler can survive a DIV shrink, and
the accepted frame's stop count is latched. Hold settings during the guard;
convert to500kHz RTC ticks with ceiling division plus one phase tick. The
Zephyr apps already flush and wait1ms; parent owns baremetal runtime integration.

Minimal merge deltas are `native-clock.patch` and `helper-query.patch`; the
plugin/clock adapter live here. Simultaneous bus/FIFO-edge arbitration is ordered
by adapter calls, without a cycle-accurate TileLink pipeline. UART pin RX sampling,
source/image association and RTL/performance calibration remain unqualified.
The source-default UART TX mode is assumed; optional RTL printf/speedup plusargs
are outside this candidate. No full board or +/-2% timing certification is made.
