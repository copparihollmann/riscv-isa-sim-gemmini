> Mandatory operating policy: read [OPERATING_RULES.md](OPERATING_RULES.md). Direct-driver reuse is prohibited. Every hardware run uses the full lifecycle, current operator allocation, shared lock and complete all-user/device checks. Uncertain cleanup is withheld. Previous prepared jobs must be regenerated after this runner change.

# FireSim measurements

`runtime-comparison.json` compares all 31 semantic fields in Ethan's pasted
runtime configuration with the local manager configuration. They match. The
runtime and hardware database snapshots retain the actual inspected inputs;
`access-audit.json` records their digests and the image digest.

Managed FPGA execution is operational as of November6,2026. The installed,
pinned root inspector provides complete all-user process/FD/maps visibility.
The actual user authorized managed autonomous batches, recorded in an expiring
user-owned receipt; the shared host lock covers every lifecycle. This does not
establish continuing availability: perform fresh complete inspection and verify
receipt/boot/ownership before every launch and phase.

Successful archived references include the12-region managed smoke,
6,750-region broad batch,2,313-region CPU-layout batch and two4,050-region
buffered batches. A newer compute-hart reference,
`runs/fpga-rvv-compute1320-v1-001`, completed1320 RVV/VME regions with184,128
independent element checks, console exit0, all four phases, owned cleanup and
verified capture. It measures harts0/1 separately while hart2 boots and parks;
it does not qualify hart2 LSU liveness or concurrent Zephyr timing. See
[WORKING_RECIPE.md](WORKING_RECIPE.md) for exact artifacts and commands, and
[CURRENT_STATUS.md](../CURRENT_STATUS.md) for current ownership and receipts.
Full source/image association and final held-out timing accuracy remain
unverified. Older access refusals and prepared safety-v3 jobs are historical;
do not execute stale jobs after runner/input changes.

Verify a newly prepared job without contacting hardware with
`python3 firesim/run_prepared.py <fresh-job>`. Any runner/input change requires
fresh preparation; preserve previous receipts. A CLI label or idle scan alone
is not an operator authorization or a shared reservation.

To reproduce the compute-hart reference, use a fresh job directory and a real,
current authorization receipt. Preparation is local; `launch.sh` enters the
existing manager environment and invokes the checked four-phase runner:

```bash
python3 firesim/prepare_rvv_compute1320.py \
  --build build/rvv-compute1320-v2 \
  --expected-ready-sha256 29fe7361720babf4488ab04a803c335ef96e67758d4e492801f080043be6b774 \
  --authorization-receipt /absolute/current-authorization/receipt.json \
  --memory-probe-build build/fased-readonly-managed-v2 \
  --output runs/NEW-UNUSED-COMPUTE-JOB
python3 firesim/run_prepared.py runs/NEW-UNUSED-COMPUTE-JOB
bash runs/NEW-UNUSED-COMPUTE-JOB/launch.sh
python3 firesim/analyze_rvv_compute1320.py runs/NEW-UNUSED-COMPUTE-JOB \
  --output build/NEW-ROOT-ONLY-REFERENCE \
  --training-export build/NEW-TRAIN-EXPORT
```

Keep the combined reference and342 reserved timing labels with the validation
coordinator; fitters receive only the978-row TRAIN export after their predictions
and estimator are frozen. The compact collector accepts this exact compiled
corpus only after its complete golden/phase/section and normal-exit checks.
Failed earlier jobs remain failed even when some sections printed valid rows.
The archive is written outside the job after cleanup; capture failure is distinct
from guest failure. This reference certifies these numerical observations, not
whole-SoC accuracy, physical bandwidth or source-to-image identity.

Historical direct-driver smoke logs in `runs/fpga-smoke-access-enabled-001/`
remain calibration-ineligible. The old procedure is prohibited. Always use the
full manager lifecycle through the checked runner. Never touch Ethan's jobs.

Read-only access probe:

```bash
python3 firesim/probe.py --output firesim/artifacts/access.json
```

`batch_runner.py` prepares a writable isolated manager deployment. It copies the
ELF, configuration, and manager entrypoint, and links read-only manager libraries.
It changes the copied entrypoint to preserve known-host checking and use the
account/key selected by the local SSH configuration. It does not read private-key
contents. A matching prebuilt driver bundle is required for execution, preventing
an implicit driver rebuild in Ethan's shared source tree.

Preparation only, using the frozen priority fitting ELF and exact previously
verified image/driver (choose unused output and a current real authorization):

```bash
python3 firesim/prepare_buffered_priority.py \
  --build build/campaign-buffered-priority-v2-final \
  --expected-ready-sha256 e6259bb479743e74f6e433cc60c34552d28e1cc35d2818d9252f537d66fe8bca \
  --authorization-receipt /absolute/current-authorization/receipt.json \
  --memory-probe-build build/fased-readonly-managed-v2 \
  --output runs/NEW-UNUSED-PRIORITY-JOB
```

To execute a freshly verified job, use `firesim/run_prepared.py <fresh-job>
--execute --authorization-id <actual-receipt-id>` with Python from the working
Chipyard FireSim manager environment. The upstream setup is
`source sourceme-manager.sh
--skip-ssh-setup` from the FireSim directory; on this host the Conda Python is
`/scratch/eygao/iris-cy/.conda-env/bin/python3`. The general system Python lacks
the manager's Fabric/argcomplete/cryptography dependencies. The allocation value
records the real user authorization; it is not an allocation service or
permission prompt. Source from the original FireSim directory, not a private
prepared manager directory. Preserve the optional missing-license-script warning
without aborting the otherwise loaded environment; see the working recipe.

Execution rechecks the user-owned authorization receipt, host boot, expiry,
complete all-user processes/FDs/mapped-device visibility and shared lock ownership
before **each** kill/setup/run/cleanup phase. It holds the shared lock across the
whole lifecycle and uses a unique private remote simulation directory. A failed
phase skips subsequent setup/workload and attempts ownership-checked cleanup.
UID alone cannot establish ownership: cleanup also requires the run's directory.
Uncertain cleanup withholds kill and retains the lock/evidence for operator
recovery. Never reclaim another lock or kill an uncertain/foreign process.

Local scans/locks cannot prevent an uncooperative external operator from starting
a new job after inspection; site-wide allocation must coordinate those actors.
See [OPERATING_RULES.md](OPERATING_RULES.md) for authorization and lock semantics.
The obsolete custom root-owned reservation JSON is not a site requirement.

Bundle many **cases inside one ELF**. A case manifest is a nonempty JSON array
containing unique `id` strings and `active_harts` lists, plus any descriptive
metadata. Cases can use hart 2 for DMA while harts 0/1 compute. This does not
implement a target-side benchmark harness or turn separately linked ELFs into
one program. Separate ELFs require separate full lifecycle invocations.

Each output directory has `run.json`, task logs and manager results. The manifest
hashes the ELF, image, driver, original runtime/HWDB, prepared entrypoint and
prepared runtime. It retains per-task status and cleanup failures. Host elapsed
seconds are recorded only as execution cost; they are never reported as target
cycles. `completed_uncertified` means the manager lifecycle finished, not that
guest results or timing passed certification. Region cycles must come from the
program's counter reads; hardware tracing/counters remain as configured rather
than being silently assumed available.

Profiling ELFs emit `IRIS_REGION ` followed by one JSON object containing
`case_id`, `region`, `hart`, `start_cycle`, `end_cycle`, `instret_delta`, and
`checksum`. Counter/checksum values are unsigned 64-bit JSON integers. The runner
checks case/hart membership, rejects reversed/wrapped intervals and duplicate
identities, and includes ELF/image hashes with each parsed record. Give repeated
trials distinct case ids. Use `--require-regions` for calibration so missing
case/hart measurements fail the run. An emulation-wide cycle summary is retained
separately from guest regions. Nonzero console process exits fail the run even
when the manager itself returns zero.

Tests:

```bash
python3 -m unittest discover -s firesim/tests -v
```
