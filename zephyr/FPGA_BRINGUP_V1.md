# Scalar SMP FPGA bringup, new exact ELF

This is a small functional bringup on Ethan's fixed-UART image. Root alone may
launch the prepared job after fresh occupancy, authorization, boot and shared
lock checks. It uses the mandatory kill/setup/workload/kill lifecycle and owned
failure cleanup/capture. Preparation and analysis contact no hardware.

The original clean Zephyr cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0 kernel and
existing scalar app are unchanged. A fresh build selects the existing
`ethan-firesim` board overlay. The resulting ELF is
`5d1014af26e4be4c42562864f8bfbbadece3cbfae750da3065db000d213baabc`.
The preserved all5OS scalar6 image instead selected physical115200/DIV4339;
it is not this FPGA candidate. The new image reads back DIV135, uses a requested
baud3676470 and source UART clock500MHz, matching the source-fixed bridge.

The actual program emits six ordinary IRIS_REGION objects: GEMM16 and valid
conv2d8, each with pinned workers on harts0/1/2, mask7 and independent checksums.
It then emits exactly `IRIS_BATCH_DONE {"failed":0}`. No host records or cycles
are generated. Each worker exercises a shared mutex/yields and two1ms sleeps.
These demonstrate finite SMP/timer/synchronization paths upon completion; no
per-hart interrupt or IPI count is emitted, so those counts are not claimed.
No vector instructions or VME context are configured in this first packet.

The DRAM-linked RV64 ELF enters at0x80000000. The actual compiled reboot path
stores64-bit1 to aligned, file-backedzero `tohost`, using the original driver's
normal HTIF exit. The console drains before reboot. Archive acceptance requires
all six rows, exact independent sums, actual footer, COMMAND_EXIT_CODE0 and the
driver PASSED marker, plus all four managed phases/cleanup. A PASSED marker alone
is inadequate: the failed historical25-region run contained it alongside exit124.

Historical source-bound audit is at
`build/zephyr-fpga-functional-status-audit-v1/report.json`. Several perturbed
285-region Zephyr images exited normally on all three harts; the original image
repeatedly stopped after25. Its cause and actual stall PC are unproven. A new
scalar6 success would not resolve that vector/context failure.

Fresh native359 seed0/17 runs passed normally. Kernel source/header dependencies
are retained from Ninja's actual compiled dependency database. Qualification is
`build/zephyr-fpga-scalar6-bringup-qualification-v1/ready.json`.

The managed recipe uses original8f driver, TSI step128, a180s foreground workload
watchdog and360s per-phase bound. It sets no target max-cycles: the original
signed32 parser and loader/global-cycle history make a low target bound unsafe.
The preinit read-only MMIO observer and optional postdriver five-register V2 hook
are both bound. Readback is configuration in memory-clock units, not measured
latency, source/image association or timing certification. A sidecar failure
remains separate from the guest result.

After root completes capture, strict analysis is:

```sh
python3 -B firesim/analyze_zephyr_bringup_v1.py JOB --output NEW_ANALYSIS
```

No hardware has been launched by this agent. Initial scalar success should gate
any later separate RVV/VME-aware SMP reference; those require their own exact
ELF, context/golden protocol and managed lifecycle. The actual original25-region
and later probe failures stay visible even if this smoke passes.
