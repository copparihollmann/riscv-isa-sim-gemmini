# Scalar SMP bringup parser successor

V2 preserves every V1 source, qualification, prepared job and receipt. The exact
ELF remains `5d1014af26e4be4c42562864f8bfbbadece3cbfae750da3065db000d213baabc`:
clean pinned Zephyr, unchanged scalar app and Ethan DIV135 board overlay. Fresh
native359 seed0/17 executions again pass all six actual region checksums and
normal HTIF exit. No target kernel, board or configuration changed.

V1's custom driver-exit parser accepted a token substring in malformed lines.
V2 requires exactly one whole `[COMMAND_EXIT_CODE="0"]` line, allowing only
horizontal whitespace around it. Missing/unbracketed/partial/prefixed/suffixed,
duplicate or nonzero markers refuse, even if a PASSED string is present. The
unchanged generic runner still collects the same actual IRIS_REGION protocol;
the strict V2 archive validator adds this independent completion defense.

All six rows, the exact actual `IRIS_BATCH_DONE {"failed":0}` footer, independent
checksums and all four successful managed phases plus owned cleanup/capture are
required. Prior25-region failures remain failures. No host-generated regions,
cycles or additional target footer fields are introduced.

The NEW V2 job uses original8f driver, TSI128,180s foreground guest watchdog and
360s per-phase timeout. Preinit observation and unchanged optional postdriver
five-register V2 hook are installed; the hook is the last preparation operation.
Root alone may launch after fresh full occupancy/auth/boot/group-lock checks.
Neither preparation nor this agent contacts hardware.

SMP completion covers three pinned workers with mutex/yield/semaphore work and
two1ms sleeps each. Explicit per-hart ISR/IPI counts are absent. Scalar6 success
does not certify RVV/VME context or resolve the old original25-region stall.
No whole source/image or timing certification is claimed.

Strict analysis after root's owned cleanup/capture:

```sh
python3 -B firesim/analyze_zephyr_bringup_v2.py NEW_JOB --output NEW_ANALYSIS
```
