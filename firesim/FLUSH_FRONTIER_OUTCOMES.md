Both one-shot jobs were locally reverified from `/tmp` at 2026-11-07
03:37:44 UTC. They have not started and retain their original prelaunch hashes:

| Variant | Job | Prelaunch `run.json` SHA256 |
| --- | --- | --- |
| Timer disabled | `runs/fpga-flush-frontier-one-shot-disabled-v2-001` | `71db41796a6efab830af5c6decae746103d77d0e0deb896b8b560f79724a6e50` |
| Timer enabled | `runs/fpga-flush-frontier-one-shot-enabled-v2-001` | `b5ab2f8b723937b35c0b86011cb882462ed49247b254527f2dbe4ee670ad85d4` |

Each passes verification of269 absolute source inputs and237 prepared files.
The v4 user-authorization receipt remains current until 2026-11-07 07:53:47 UTC
(23:53:47 PST). This local review establishes no remote availability, current
boot identity, idle allocation or held lock. Root must finish the existing owned
WFI run, cleanup and capture, then perform the fresh complete idle/holder/boot
checks and shared-lock acquisition before either launch. Each launch still uses
kill → infrasetup → runworkload → kill, with owned failure cleanup and a separate
quiescent archive. Do not change a prepared job or substitute a direct driver.

Both use the original archived driver bundle5457de1e… (inner executable8f78167b…),
image TAR9bbe1f12…, TSI step128, no target-cycle limit, a600-second foreground
guest wall bound and780-second managed-phase bound. The reviewed read-onlyFASED
observer and available UART/heartbeat/memory CSV copyback remain selected. The
user-owned capture utility is the exact8058f267… file and is bound into both
jobs; the campaign-policy hash is1a20d027…. A target-cycle limit must not be
added: successful loading previously exceeded5billion cycles and this driver's
atoi32 target-bound parser is unsuitable for the proposed large values.

| Actual guest outcome after managed cleanup/capture | Meaning | What it does not establish |
| --- | --- | --- |
| Exit0, exact32 regions/30 job outputs, all embedded122880INT32 +122880W8A8 checks, independent hashes and normal DONE | This instrumented two-phase program completed. Run the frozen full analyzer. | A fix for the original stall; universal liveness; timing accuracy. |
| Exit1 with one valid `IRIS_FLUSH_ONESHOT`, six `IRIS_FLUSH_SNAPSHOT` rows, matching hart1/deadline and no normal DONE | The one-shot reached its actual timer-driver C hook and captured last-recorded source stages. It is a successful diagnostic capture of a failed/incomplete workload. | Lack of progress: the timer fires at a fixed deadline even while work progresses. No current PC/state or physical vector-completion claim follows. |
| Exit1 without the complete valid one-shot envelope, or another fatal/nonzero outcome | Another failure or incomplete capture. Preserve every raw log and use the analyzer's refusal. | A qualified six-slot snapshot or a specific FP/context cause. |
| Host exit124 or manager wall/phase timeout, no normal DONE | Bounded noncompletion within that run's limit. Preserve partial output plus heartbeat/FASED and owned cleanup/capture. | Infinite deadlock, a missing interrupt, clock gating, memory-bank cause or the source location where execution stopped. |
| Timer disabled but an `IRIS_FLUSH_ONESHOT` appears | The selected-byte policy or evidence association is inconsistent; fail closed. | Valid disabled control evidence. |

The enabled armer record must show physical hart1, delay3000ms, actual MTIE and
MSTATUS.MIE enabled at arming, and deadline=armed_mtime+1500000 ticks. This is
three seconds of the500kHz target CLINT, not three host seconds. The comparator
is hart1's own CLINT register. Once armed, the derived driver preserves that
local deadline against later OS comparator writes. The other harts retain the
original timer behavior. BOTH variants create and join the same scalar armer
thread after phase-zero printing; the one retained nonexecutable byte selects
arming/comparator/MTIE behavior. They retain identical instructions and symbol
addresses. The arm critical section and its deadline-publication fence are part
of the perturbation; only the hot observation hooks are fence-free.

The hook is the first C statement of the actual timer ISR, before its original
spinlock, clock accounting and scheduler announcement. Trap-entry assembly runs
before that statement. Entry `mstatus.MIE=0` is normal interrupt-entry behavior
and must not be called proof that the hart was disabled before the interrupt.
If hart1 has interrupts disabled, or scratchpad/NoC access itself cannot finish,
this timer cannot guarantee a dump. The600-second host bound is authoritative.

| Slot/stage frontier | Last recorded fact only |
| --- | --- |
| Slots0/1/2 | Last kernel event stamped by physical harts0/1/2. Later events may overwrite earlier ones. |
| Slots3/4/5 | Last main/compute0/producer application record. Decode sequence63:32, hart31:28, phase27:24, job23:16, stage15:0. |
| Kernel201/200/202 | Caller-before, remote-flush function-entry, caller-returned program points. No delivery/completion conclusion from202 alone. |
| Kernel400/401/402 | Existing IPI pending-bit clear returned / before local flush / local flush call returned. A later event can overwrite these. |
| Kernel102/103 or120/121 | Before/after the original scalar FPR save/restore call. |
| Kernel300/301/302 | VRF-save entry / before original four-m8 asm / asm returned.302 is not physical store completion. |
| Kernel310/311/312 | VRF-restore entry / original four-m8 asm returned / vector-CSR restore returned. |
| Kernel106/107 or203 | Before/after original owner clear, or an existing remote-owner wait loop returned. Absence is not proof the event never ran. |
| Kernel600/610 | Enabled/disabled common armer program point. |

All stage/owner/current-thread/CSR fields are LAST RECORDED observations. They
are plain volatile64-bit stores in disjoint source-uncacheable scratchpad slots,
with compiler barriers only. Sequence equality is an observed consistency check,
not proof of coherent cross-hart metadata. Treat a mismatched/odd sequence as
torn or changing; even a stable sequence retains `metadata_race_possible=true`.
No nearest-PC or owner-state reconstruction is permitted. Other harts are not
halted: concurrent console output can interleave, in which case parsing must
fail closed and raw bytes remain forensic evidence.

Run postcapture analysis using the frozen helper:

`python3 firesim/analyze_flush_frontier.py JOB --output FRESH_ANALYSIS`

A qualified one-shot diagnostic has workload-normal-completion=false even when
the analyzer accepts the diagnostic envelope. A host-timeout control remains a
failed full workload. Full normal validation is unchanged and is never weakened
to accept a partial phase. No result is used for calibration, protected original
v6 timing labels, full-source/image attestation or a2% claim.

The source/build capsule is
`build/flush-frontier-one-shot-closure-v1/report.json`,
SHA77ba1fa4d0dfd2f746172a13ccff3981828306e5411fa345dd988911784120eb.
It binds four actual359 schedule positives, actual forced ON snapshot/HTIF1,
OFF bounded no-snapshot control, identical original four-m8 blocks and eight
compiled matrix objects,56 hot instructions without architectural FENCE/AMO/FP/RVV,
11 managed-admission controls and13 snapshot-parser controls. The prior V1 mobile
CPU assertion failure is preserved separately and is not a hardware observation.
