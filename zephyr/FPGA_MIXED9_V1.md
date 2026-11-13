# Preserved mixed9 Zephyr SMP functional FPGA packet

No target rebuild or source change is needed. The exact preserved ELF is
`93a52d8935e6e0a3d63a88ded86f44f2802cfceb4e0f919d4e272bb56567a306`.
Its clean-base Zephyr pin is cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0 with
exact context overlay558cefc2f57225774cc891e1df0d2f7149f6e834a7012b4c0735f0fba0d1aa1b.
The existing Ethan overlay requests3676470baud from500MHz, reads DIV135 and
matches the fixed bridge. All current source/patch/build digests are checked.

One ELF bundles nine actual IRIS_REGION objects. GEMM16 and conv2d8 run on all
three pinned workers, with independent row-stride checksum goldens. The final
operation runs32 unsignedINT8 TK1 matrix accumulations and yields on each of
harts0/1, then sums32words of tile0,row0 (1024). Hart2 instead performs32iterations
of an ordinary e8m1 VL32 load/yield/store and sums32bytes per iteration (1024).
No VME instruction is deliberately executed on hart2. Main coordination and
console/HTIF completion are on hart0; hart2 is a functional vector worker and
source of shared scheduling/memory interference.

Detailed timing work remains focused on harts0/1. All nine actual guest counters
are retained for provenance, but this is a functional packet and no hart2 timing
calibration or whole timing certificate is claimed. The actual footer remains
`IRIS_BATCH_DONE {"failed":0}`; no host regions/cycles are invented.

Fresh native359 seeds0/17 pass normally. Independent host arithmetic derives all
nine checksum sums. Actual ELF encodings prove the32-command loop, row readout,
hart2 copy loop and kernel's four e8m8 full-VRF copy groups. The app has only one
vector owner per hart and emits no actual context-save/restore, IRQ/IPI or
migration counts. Yields do not prove competing same-hart owners. The32-word
row checksum is not a fullMRF per-word verification. Explicit hart2 VME refusal
is tested elsewhere, not by this packet.

The context kernel's first lazy restore can execute four256-byte m8 loads. This
remains relevant to prior hardware context-stall evidence: original285 stopped
after25 while several perturbed285 images completed. New scalar6 now passed
hardware, but that does not resolve the vector/context failure or certify this
preserved mixed9 image. A bounded failure remains an informative result.

Root alone launches the NEW prepared job after complete current inspection,
authorization, boot and shared-lock checks. It uses kill/setup/workload/kill,
owned cleanup and quiescent capture on either outcome. Original8f driver,
TSI128,180s foreground guest watchdog,360s phase bound, no target max-cycles.
Preinit and optional postdriver5register read-only observers remain separate
from guest success; config readback is not physical latency certification.

The prelaunch-bound analyzer validates actual dated util-linux script framing,
the header command against both captured sim-run copies, one exact bracketed
exit0 footer, actual PASSED, allnine goldens and allfour managed phases. It
preserves malformed/missing/duplicate-marker rejection. Remote script binary
version is unavailable unless separately captured; source/image association
remains false.

```sh
python3 -B firesim/analyze_zephyr_mixed9_v1.py JOB --output NEW_ANALYSIS
```
