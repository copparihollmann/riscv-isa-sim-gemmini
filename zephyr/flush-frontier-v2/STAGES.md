Kernel stages record scalar program points, not physical unit completion:

-100: arch_flush_local_fpu entry, before its original assertions.
-102/103: before/after the original scalar FPR-save call.
-106/107: before/after the original FP-owner clear.
-120/121: before/after the original scalar FPR-restore call.
-200: remote-flush IPI function entry, before its original pending-bit/MSIP writes.
-201/202: caller before/after the remote-flush function call.
-203: existing current-thread remote-owner wait loop returned.
-300/301/302: VRF-save entry / after original vector-CSR save before fourm8 asm / asm returned.
-310/311/312: VRF-restore entry / fourm8 asm returned / vector-CSR restore returned.
-400: original IPI pending-bit clear returned; peer records those original pending bits.
-401/402: before/after IPI handler's original local-FP flush call.
-600/610: common scalar armer thread, timer enabled/disabled.

Slots0..2 are last kernel events for physical harts0..2. Slots3..5 are main,
compute0 and producer application stage words, preserving the parent packed
sequence/hart/phase/job/stage encoding. All slots occupy128bytes at256byte
strides in the source-uncacheable system scratchpad0x58001e000..0x58001e5ff.
The snapshot copy uses0x58001f000..0x58001f2ff. Control words use0x58001fc00.
No allocation/stack/code occupies this range in the diagnostic ELF.

Hot record publication uses plain volatile64-bit stores and compiler barriers.
It has NO architectural FENCE, AMO, FP or vector instructions. Sequence equality
is only an observed consistency check; metadata can race, reorder or tear across
harts. No current PC, coherent-current-state, physical VRF/MRF completion, or
old-source timing claim is made. The uncached stores and extra scalar code/stack
traffic remain substantial perturbations.

Both variants create/join the same pinned-h1 scalar armer after phase0 printing.
One retained nonexec byte selects whether it programs hart1's real CLINT comparator
for mtime+1500000 (3000ms at500kHz), enables MTIE and MSTATUS.MIE, and preserves
that one deadline against subsequent local OS timer writes. Other harts retain
the original timer behavior. This is not a global OS-clock-owner assumption.
Initialization/ARM/terminal fences are outside the observed FPU critical paths.

The actual timer driver's first C statement calls the capture hook before its
spinlock/accounting/sys_clock_announce. The hook snapshots before UART output,
then drains UART and writes HTIF3 (guest exit1). It fires at a fixed deadline,
NOT after detecting lack of progress. If hart1 has interrupts disabled or cannot
access the scratchpad, it cannot guarantee capture; the600s host bound is final.
