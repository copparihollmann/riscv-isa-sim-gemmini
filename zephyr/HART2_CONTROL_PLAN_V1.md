# Hart2 control task driving compute harts: source plan only

Keep the launched mixed9 ELF/job/source unchanged. A future NEW app can retain
the exact Iris board, clean-base cd45 kernel plus558cefc context overlay and
Ethan DIV135 console. This document is not target execution or admission proof.

Bootstrap on hart0 creates one persistent worker pinned to hart0, one pinned to
hart1 and a scalar-only controller pinned to hart2, then blocks. Each worker
calls iris_vme_enable once while pinned solely to its compute CPU. No other
thread deliberately uses vector/FPU/VME state on that CPU. Hart2 never issues
VME and initially avoids vector use, retaining its control/synchronization and
shared-memory interference role rather than detailed timing calibration.

Use actual Zephyr semaphores and per-worker64B-padded descriptors/output storage.
Controller prepares operands, golden-dependent poison and an epoch/sequence;
gives each selected worker's start semaphore; workers execute, store output and
matching completion sequence, then give done semaphores. Controller accepts
only expected hart/sequence and completed outputs. One command per worker can
be outstanding. Do not substitute a loose volatile polling scheme. Pinned
kernel sem.c95-158 serializes give/take with a spinlock and wait queues, and
actually readies or pends threads. This is the existing OS synchronization
path being tested, not a newly claimed fabric visibility shortcut.

Bundle compatible cases into one ELF:

* RVV e8 payloads32/64/128/256B using LMUL1/2/4/8 on harts0/1, repeats1/4/16/64.
  A load/add-byte/store kernel has independent modulo256 element goldens.
* UnsignedINT8 matrix TK1 square active shapes8/16/32, same repeat counts.
  Reuse exact source geometry setters and row semantics; require actual ELF
  and full active-cell proof before enabling any smallTM/VL shape. No FP8 or
  signed-format alias expansion is inferred from macro names.
* For each combination run compute masks1,2,3, each three trials:252 controller
  dispatch groups and336 compute-hart regions in one program. The controller
  remains active on hart2 throughout. Buffer all measurements, then emit from
  hart2 after a completion sentinel; no between-group UART is necessary.

The new plan prospectively reserves vector128B and matrix16x16x1 across every
repeat, mask, active hart and trial:96 reserved regions,240 potentially training
regions. All data initially remain functional validation only; this partition
does not authorize fitting. Freeze exact IDs/program/split before hardware.
Root alone receives reserved timing labels. No timing labels informed the plan.

For every dispatch the controller initializes input/output outside harts0/1's
ROI and poisons each active result with independent golden XOR0xffffffff.
Workers compute and fully drain before completion. Compare all active bytes or
matrix cells outside ROI, not merely a sum. A separate host integer oracle
derives each word/checksum. Matrix inputs can use a bounded unsigned pattern
so golden[r,c]=repeat*A[r]*B[c] mod2^32, independently checked by a literal
integer k-loop. Row readout is the supported row path; no column semantics or
fullMRF coverage beyond the explicitly read active cells is implied.

The kernel source supports the intended one-owner contract: iris_vme.c9-27
refuses noncompute/invalid-affinity/ISR use, claims lazy vector ownership before
tile zeroing, then marks initialized state. fpu.c232 onward still contains
local/remote ownership flushing, and initial vector restoration copies four
m8 groups. This risk remains. One owner/hart avoids intentional competition;
it does not prove no interrupt, save/restore or remote-flush event occurs.
Existing switch-count API can report actual callbacks outside ROI, without
manufacturing IRQ counts or treating zero callbacks as a failure.

Actual mhartid checks prove the controller is hart2 and each worker its target.
Emit a separate IRIS_CONTROL functional record with dispatch/completion counts
and sequences, plus only actual harts0/1 CSR ROI records. The unchanged runner
can declare compute active-harts0/1; a new strict archive validator must also
check the controller record/all words/footer. Do not fabricate a timed hart2
region. CLINT metadata may bracket dispatch/completion for global ordering,
with500kHz quantization stated and no overhead subtraction.

Completion needs explicit failure transport. soc.c29-41 hardcodes success0
and tohost1 in sys_arch_reboot; passing a reboot type cannot produce failure.
Before admission, prove a private app-only finish path can quiesce workers,
drain the actual UART and write encoded HTIF failure3 when needed using the
existing htif_lock/tohost interface. Alternatively preserve failed numerical
footer/host-watchdog semantics honestly. Do not edit shared soc/HTIF drivers or
claim a panic completed normally. Normal and forced-timeout/omitted-kernel
native controls must establish the selected path.

Required future gates: exact body/opcount/roles/LMUL and scalar-controller ELF
proof; fresh359 seeds0/17 with all active values; measured-kernel omission and
stale/duplicate completion controls; strict actual host script envelope; frozen
IDs/split/source closure; only then a new root-managed job. Use full four phases,
fresh complete inspection/auth/boot/group lock, owned cleanup and capture on
both outcomes. Set host watchdog from measured console/runtime rather than
invent a target-cycle bound. No additional job is prepared by this plan.
