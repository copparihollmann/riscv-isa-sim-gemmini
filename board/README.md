# Iris physical boot and board integration helpers

This directory freezes the actual 192-byte Iris RV64 boot ROM and provides
tested boot-register, readonly-ROM, timer-register and physical-map helpers.
They are not yet installed into the normal Spike executable. No Zephyr boot or
FPGA equivalence is certified by these tests.

## Exact boot protocol

The prefix is copied from the configured TestChipIP resource
`generators/testchipip/src/main/resources/testchipip/bootrom/bootrom.rv64.img`.
Its SHA256 is
`5f6ae520d6612da2b31c2ee70bc872b743a77bbde0abba87bf96aa5fc249a216`.
`manifest.json` identifies source commits, source bytes and fact citations.

All three harts reset at `0x10000`. The ROM sets `mtvec=0x10040`, enables MSIP
interrupts and waits in WFI. The external program loader writes the ELF's start
address to the 64-bit register at `0x1000`, then sets hart 0's CLINT MSIP.
Hart 0 probes successive MSIP registers to release secondaries; the first
nonexistent hart reads zero and terminates the probe. Secondaries wait for
hart 0's MSIP to clear before clearing their own MSIP and entering the program.

The ROM performs `mret` to the boot-address register's value. It provides
architectural hart ID in `a0`, and points `a1` at the appended DTB at `0x100c0`.
The data is the actual dynamically selected DTB, rather than a hard-coded
address pointing outside the ROM. The ROM aperture is 64 KiB, readonly and
zero-filled after prefix+DTB, matching `TLROM` behavior for unused high addresses.
Boot-register byte writes merge into the 64-bit value; unmapped registers in
its 4-KiB page read zero and ignore writes, matching `TLRegisterNode.undefZero`.

## Devices and permissions

`physical_map.hpp` is generated from the exact saved elaborated memory map. It
checks the whole access range, real holes, R/W/X permissions, and the exported
atomic-capability bit. In particular, the system scratchpad is executable but
does not support atomics. The helper does not instantiate RAM for MMIO, enforce
individual bus transfer sizes, or install PMA checks into the Spike MMU.

`TimerRegisters` in `iris_clint.hpp` exposes byte-correct per-hart MSIP,
`mtimecmp`, and `mtime`. Call `advance_rtc()` with **modeled 500-kHz RTC ticks**;
it does not infer time from instructions or host wall time. IRQ callbacks have
the signature `(hart, bool msip, optional<bool> mtip)`.

`mtimecmp` is not reset in the RTL. The helper tracks initialization per byte,
rejects reads of unknown compare bytes, and represents MTIP as unknown until
all eight bytes are initialized. It preserves atomicity of a 64-bit MMIO write
and handles 32-bit high/low updates independently. It does not decide how the
core must react if software enables MTIE while its compare is unknown; the
integrated board adapter must explicitly fail closed in that situation.

The source audit also found remaining gaps in generic Spike devices:

- Iris PLIC is one interrupt source with six M/S contexts, maximum priority 1
  and a 64-MiB aperture. Generic Spike uses a 16-MiB aperture and four priority
  bits; using it unchanged does not reproduce the Iris device.
- RTL PLIC priorities, thresholds and enable registers are uninitialized `Reg`
  storage. Only pending bits and level-gateway in-flight state reset false.
  An integrated model must preserve this distinction from reset-to-zero state.
- The UART is the SiFive register layout at `0x10020000`, interrupt source 1.
  Its watermark levels are at byte offsets `0x0a` and `0x0e`; their width derives
  from FIFO depth. Ethan's FireSim target overrides the base defaults with
  **256-entry TX/RX FIFOs and nine-bit watermarks**, confirmed in the elaboration;
  the earlier eight-entry reading of the base defaults does not apply to this
  image configuration. TX/RX enable and interrupt enable reset false.
  Interrupt status is `(tx_count < tx_watermark)` / `(rx_count > rx_watermark)`;
  the existing immediate-output console plugin is not a timing model of those
  FIFOs or the serial line. The new [UART helper](uart-notes.md) preserves those
  register/FIFO semantics and source TX state but is not yet in the console
  plugin. The [PLIC adapter](plic-notes.md) now has ordinary-process regression
  results, with pipeline timing and full board equivalence still unverified.

## Build and test

```sh
python3 board/prepare.py
python3 board/build.py
```

Preparation writes only this directory. Tests link current Spike libraries and
execute the frozen ROM on three real Spike processors and CLINT. They exercise
both loader release after WFI and release before the first instruction, with
different hart stepping orders. They check all three entry PCs, `a0/a1`,
interrupt clearing, M-mode entry, readonly-ROM faults, DTB bytes, padding,
byte-merged register writes, permission holes and timer initialization/edges.
`test-results.json` retains helper input, linked-library and artifact digests.
The native fixture manually supplies the physical reset-PC hook; it does not
demonstrate that the usual Spike command already uses this boot path.

The tests also build and dynamically load `build/libiris_board_boot.so` with
device factories `iris_bootreg` and `iris_bootrom`. The ROM factory takes the
prefix and DTB file paths and verifies that its appended DTB exactly matches
the active simulator DTB. Loading this plugin alone is insufficient: normal
Spike still installs its default reset ROM at `0x1000` unless core integration
changes it, which conflicts with the physical boot-address register.

## Unapplied core proposal

`python3 board/propose_core_patch.py` emits `core-changes.patch` and base-input
digests. The patch has been checked for clean application but **not applied**.
It adds an explicit `--iris-bootrom=<prefix>` selection, sets physical reset PCs,
replaces default ROM installation, and models the loader's boot-address/MSIP0
write after ELF loading. It appends the simulator's current DTB dynamically.
The proposal's applicability is tied to its recorded base-input hashes; partial
adoption by the parent core can make whole-patch application fail, which requires
review rather than automatic rebasing by the board helper task.

The parent integration must reconcile this proposal with the online scheduler,
wire the RTC and unknown interrupt state, enforce the physical map in all MMU
paths, and provide matching PLIC/UART behavior. It must refresh the simulator's
patch/build provenance and execute actual multicore Zephyr tests afterward.
