# Local saved-IrisConfig RTL reference

This host adapter relinks the existing Verilator model without changing its
generated RTL or C++ model archive. It implements the existing
`testchip_tsi_t::load_mem_write/read` virtual hooks for the two elaborated native
RAM arrays. **The original SimTSI hooks do nothing: adding `+loadmem` to the
original executable silently skips program loading.** Use the adapter binary.

Build with `python3 board/rtl-loader/build.py`. Run the resulting executable
with explicit `+loadmem=1` inside `+permissive`/`+permissive-off`, followed by the
ELF. Ordinary runs without that flag continue to use TSI loading. Each direct
transfer is range checked against DRAM `[0x80000000,0x180000000)` and cannot cross
the native-bank boundary. The generated Xbar selects bank1 with address bit32;
each SRAM indexes address bits30:3. Byte writes preserve the other bytes.

FESVR queues ELF writes before reset. A queued `+init_write` prints “Done” before
RTL has accepted it. A bounded diagnostic accepted only257 of3532 queued32-bit
words in9000 TSI clock edges. The100MHz loader clock is ten times slower than the
1GHz testbench cycle counter; normal bulk loading therefore takes minutes.
The48-byte `tiny.S` ELF completes through ordinary TSI and through explicit
preload, proving the actual ROM/MSIP/DRAM instruction/HTIF path works.

`start-loader-bss.S` is an explicitly different functional-probe CRT. It relies
on the identified FESVR ELF loader's PT_LOAD `memsz-filesz` zero fill and skips
the redundant12KiB guest BSS-clear loop. The original CRT and timeouts are
preserved. This changes boot timing and initial cache state. Reset IPIs, guest
execution, and final FESVR signature reads still traverse the actual RTL TSI
path; the mailbox is not read through the preload backdoor.

Sources and generated-harness excerpts are frozen under `evidence/`. The saved
IrisConfig FIR/native FIRRTL memories are a separately identified reference;
they are not an attested copy of Ethan's loaded FireSim image or macrocompiled
memory implementation. One seed and selected probes do not certify all reset
definedness, full functionality or timing.

The UART harnesses differ. Saved IrisConfig has a500MHz UART reset divisor4340
and a100MHz SimUART receiver divisor868. The inspected Ethan FireSim annotation
has fixed `UARTKey(div=135)` at500MHz and configured nominal baud3686400; its
decoder does not track software DIV changes. A115200 Zephyr image changes DIV
to4339 and cannot be assumed to print correctly through that fixed bridge.
The explicit Ethan deployment overlay selects a requested baud that makes the
pinned Zephyr driver's `clock/baud-1` formula produce DIV135. Image association
and physical execution remain separate gates.
