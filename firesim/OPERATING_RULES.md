# FPGA execution contract

Follow ../AGENTS.md. Never invoke the simulator driver directly. Every run uses kill -> infrasetup -> runworkload -> kill via batch_runner.py (or run_prepared.py). A failed phase skips subsequent setup/workload and attempts ownership-checked final kill. Never clean up a foreign or uncertain job.

The user explicitly authorized managed FPGA bringup and autonomous batches in the current conversation (2026-11-06), conditional on complete idle/ownership checks. Record that actual authorization in a user-owned receipt bound to the SSH account, host boot, allocation identifier and expiry. Do not invent Ethan/operator confirmation. The former custom root-owned `/scratch/firesim/iris-exclusive-allocation.json` was an agent-added format, not a FireSim/site requirement, and is no longer mandatory.

Acquire and hold the group-shared lock `/scratch/firesim/iris-locks/fpga0` throughout the managed lifecycle. Its parent is root:firesim mode2770. Do not override another lock or claim that a CLI label/idle scan alone reserves against arbitrary operators. Recheck actual complete occupancy after acquiring it and before each action. Stop if another job/holder or genuine reservation is discovered. A token, account and host-boot bound receipt plus the held shared lock governs cooperating agents. The coordinating agent alone launches hardware.

Read-only preflight checks all visible processes, FPGA programming/simulator processes, and all process file descriptors for XDMA/PCIe mappings. Permission-denied or otherwise incomplete inspection fails closed. The reviewed fixed inspector is now installed and usable through `sudo -n -- /usr/local/bin/firesim-iris-inspect </dev/null`; ordinary unprivileged /proc visibility is insufficient. It is read-only and must match the pinned source digest. The policy has no bypass flag. Logged-in sessions are recorded as context; they neither prove nor disprove an exclusive allocation.

Recheck allocation expiry, host boot, processes and device holders immediately before each phase and cleanup. Use a unique private remote simulation directory for each run. Cleanup permits a busy process/device holder only if both its UID and working directory prove it belongs to this run. A failed/uncertain cleanup retains the lock for operator inspection. Do not reclaim it automatically.

A process scan cannot prevent an uncooperative operator from starting in the interval after the scan. A host-wide site allocation/launch service honoring the same reservation/lock is needed for a system-wide guarantee. Never claim local checks can prevent every external race.

Runner changes invalidate old prepared jobs: prepare fresh smoke/baseline/multicore jobs rather than editing their frozen receipts. Preserve all old results. Do not run hardware just to test this policy; use mocked lifecycle tests.

## Batch and capture requirements

Follow CAMPAIGN_POLICY.md: bundle compatible tests and repeats inside one ELF, profile setup costs, cache only hash-verified artifacts without bypassing programming, and preserve maximal supported counters/traces plus raw logs/results/provenance on both success and failure.
