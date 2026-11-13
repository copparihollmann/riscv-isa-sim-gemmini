# Mandatory FPGA operating rules

User directive, 2026-11-05. Applies to every agent, resumed session, helper and hardware run.

- ALWAYS use `firesim kill -> firesim infrasetup -> firesim runworkload -> firesim kill`, including ownership-checked cleanup on failure. No direct simulator-driver launches, retained-image reuse, or setup/cleanup bypasses. Batch cases inside one ELF.
- Before the FIRST kill and every subsequent hardware action, verify a current exclusive allocation from the machine operator, check ALL users/agents and device holders, and acquire/hold the shared host lock for the entire lifecycle. An idle process list or an allocation label alone is not a reservation.
- If another user/agent is running, reserved ownership is uncertain, inspection is incomplete, the host rebooted, or the lock is held: STOP. Never kill another job, override/delete another owner's lock, reset/flash/remove PCIe devices, or change device permissions to obtain access.
- Use `firesim/batch_runner.py` or its verified `firesim/run_prepared.py` entrypoint. Keep each run in its own remote simulation directory. Cleanup may target only processes proved to belong to that run and account; same UID alone is insufficient. If ownership/visibility is lost, withhold kill, preserve the lock/evidence, and request operator recovery.
- The user explicitly authorized managed FPGA bringup and autonomous batches on 2026-11-06 after a complete idle check. Record that real authorization in a user-owned receipt bound to account, host boot, allocation ID and expiry; hold the shared group lock `/scratch/firesim/iris-locks/fpga0` for the entire lifecycle. A custom root-owned reservation JSON is NOT a site requirement and is no longer mandatory. Never manufacture another operator's confirmation. Complete all-user/device inspection and ownership checks remain required.
- SSH access does not prove FPGA health, availability, image identity or calibration validity. Recheck health after recovery using the authorized lifecycle. Preserve previous evidence and failures.
- Propagate these rules to delegated agents. Only the coordinating agent launches hardware. Continue independent simulator work through hardware blockers.

See `firesim/OPERATING_RULES.md` for the allocation record and checks.

## Batch and capture requirements

Follow firesim/CAMPAIGN_POLICY.md: bundle compatible tests and repeats inside one ELF, profile setup costs, cache only hash-verified artifacts without bypassing programming, and preserve maximal supported counters/traces plus raw logs/results/provenance on both success and failure.

## Installed inspection and current authorization

The exact reviewed read-only inspector is installed at /usr/local/bin/firesim-iris-inspect and covered by the existing passwordless FireSim helper grant. User confirmed sudo installation done. Root-owned reservation-file policy was an earlier agent implementation choice and is superseded by actual user authorization plus complete idle inspection and the shared group lock. Do not ask the user/Ethan to create that obsolete file. The coordinating amd6 agent is authorized to run managed smoke then broad batches if ownership/health checks pass.
