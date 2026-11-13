> Latest compiler/model FPGA campaign (2026-11-08 02:31 UTC): four newly managed jobs passed, including FP8 baseline/hybrid, encoder phase and quiet repeatability batches. Exact scripts, frozen guest builds, real counter results and independent archive reports are indexed at `/users/copparihollmann/iris-work/out/artifacts/fpga/parallel-vme-20261108/README.md` and `campaign-status.json`. Image and matching driver pins remain the ones documented below. Previous authorization receipts are expired; use the current real user receipt and fresh complete inspection/shared lock. No default simulator timing certification or full-goal completion follows from these runs.

# Verified managed Iris FPGA recipe

Latest completed reference (November6):
`runs/fpga-buffered-priority-v2-001/run.json`, all4,050 independently checked
regions,736semantic parents,2,208trialcases,3repetitions across all three harts.
ELF SHA256:
`30598c1a89abaa2e7bd0a52b3734e3cf268ab35ecabbdab652ab9bc7b29e4ff3`.
Kill/setup/workload/kill passed in24.39/115.93/317.28/24.37hostseconds,
followed by owned cleanup and archival. Capture SHA256:
`0e4e2a1268b8e897d129acd5258d8b33efc2865bccb800ebba2e0e92e6c49eeb`.
Independent analysis is
`build/fpga-buffered-priority-v2-001-analysis/report.json`; a separate stdlib-only
numeric/archive audit is
`build/buffered-priority-independent-audit-v2/report.json`.
Its exact preparation command is in [README.md](README.md). It uses a600s
foreground guest watchdog and780s host phase bound; launch with
`--timeout 780`. This is a new reordered ELF/reference, so earlier6,750-region
or buffered-v1 timing rows cannot be substituted for it. Final global Zephyrv6
reference is separate and remains unmeasured; freeze matched predictions first.

The first successful managed smoke is
`runs/fpga-user-authorized-v9/smoke/run.json`. All four tasks passed:
kill23.872s, infrasetup116.509s, runworkload120.099s, kill23.317s.
All12regions on physical harts0/1/2 matched independent host checksums;
`IRIS_BATCH_DONE.failed=0`, console process exit0. Owned cleanup and lock
release passed. The external archive SHA256 is
`fb354ed82b00704e39af70eccce8ab587680d2e8e07c0fb28e659bbcb2fce845`.
Independent archive verification is `build/fpga-v9-smoke-archive-analysis/report.json`.
This establishes operational bringup, not full-model or timing certification.

The broad fitting campaign also PASSED on real hardware:
`runs/fpga-user-authorized-v12/broad-fit/run.json`, independently verified at
`build/fpga-v12-broad-archive-analysis-v2/report.json`. All6,750regions,
3,680trialcases,736parentcases,30phase markers and1,350five-trial groups passed.
Per-hart region counts are2,375/2,300/2,075. The four managed phases took
24.016s/117.406s/469.523s/23.039s; cleanup and lock release passed. Archive SHA256:
`ac4445271bf781b10e4b09e1bafa86ded73470279a63f4ac3ef898ad641fcaeb`.
Fresh complete post-cleanup inspection found no busy processes/device holders:
`build/fpga-v12-post-cleanup-inspection-v1/report.json`.
These are fitting observations; full source/image association and the held-out
accuracy gate remain unresolved.

## Authorization and occupancy

Follow the latest AGENTS/OPERATING_RULES user directive. The obsolete requirement
for a root-owned reservation JSON was removed. The current user's explicit
launch instruction is recorded in a user-owned remote receipt, with account,
UID, host boot and freshness horizon. It does not claim an Ethan/operator
exclusive reservation. Current receipt:
`build/user-launch-authorization-current-v3/receipt.json`, authorization ID
`user-launch-20261106T203313Z-dd05e5d9`, expiring
2026-11-07T02:33:13UTC /18:33PST November6. This is a freshness horizon for the
receipt, not an invented site lease. Do not reuse it after expiry or a reboot.
For later runs, record the standing real user grant in a new receipt using
`record_launch_authorization.py` and fresh complete inspection; preserve the old
receipt and never invent new Ethan/operator confirmation.

The exact installed inspector is
`5934aaa1907605a05cd6e9bca6c28e98fa6ab62dfb8339c5c5aabde59ac526d8`.
It must return complete all-user process/FD/maps visibility. Busy or unknown
holders block actions. The group-lock parent is root:firesim mode2770 at
`/scratch/firesim/iris-locks`; the held atomic-directory lock is `fpga0`,
with token/account/boot/authorization identity. No foreign lock recovery.
Only the coordinator launches hardware.

Every run uses kill -> infrasetup -> runworkload -> kill, including owned failure
cleanup. XDMA nodes can legitimately disappear after the managed module unload;
complete inspection, trusted FPGA database and actual PCIe BDF presence remain
required. The managed programmer leaves a root `hw_server -I20` daemon briefly.
The runner waits for its natural exit and then requires complete idle inspection;
it neither kills that daemon nor treats a busy inspection as permission.

## Exact selected artifacts

- Image tar: `9bbe1f12a2b18091c28b05ea43c001e579f70c8cfef0f528fcb49003212fb776`.
- Image `.bit`: `fe3e6097489f14b10ecdeaf0d781201835810de41635b46b92426095cbda1e98`.
- Original archived driver executable:
  `8f78167b754097623b031f41d7e5f121f4ae368f716255fdcf574693a071c48a`.
- Repacked matching executable/runtime bundle:
  `5457de1e9c0dd1e3c52efbf5d083bdac7dfa5a5e3124c9887961c08159b03450`.
- Smoke ELF: `d66fbb6f3b5a2d6d417cf6e209cc335801b163e964ffa8b43abd9d8ab7e2b649`.
- Broad fitting ELF: `9d6f692c98d955276e0ac7d941afefa3551a240f2f8ce39cd2a6f1ab57f44942`.

Use `build/firesim-observability-archived-driver-v3/report.json` for the full
inventory. Managed programming and post-setup transport hashes are observed;
complete original source/library-to-bitstream association and independent image
readback remain unverified. Current source pins/dirty patches are preserved in
hardware/manifest.json and each job's frozen input snapshots. Never replace
these qualifications with a full RTL/calibration claim.

## Reproducible preparation and launch

Ethan's manager is `/scratch/eygao/iris-cy/sims/firesim`. Keep it unchanged.
Preparation resolves build-recipe makefrag directories to their original
absolute paths; relative paths break in a private manager directory.
The private adapter passes the installed tool paths explicitly:

- `/tools/xilinx/2026.1/Vivado_Lab/bin/vivado_lab`
- `/tools/xilinx/2026.1/Vivado_Lab/bin/hw_server`

Their read-only wrapper inventory is `build/xilinx-tool-paths-v1.json`.
No direct driver, retained-image or programming/reset bypass is used.

```sh
python3 firesim/prepare_managed_campaign.py \
  --output runs/NEW-UNUSED-DIRECTORY \
  --driver-tar firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz \
  --observability-report build/firesim-observability-archived-driver-v3/report.json \
  --authorization-receipt /absolute/current-authorization/receipt.json \
  --fesvr-step-size 128
```

Verify inputs before execution; fresh jobs are required after source changes.
Use the actual current authorization ID from the receipt, not an invented
operator reservation. Source the environment from the original FireSim root;
the prepared job's private `manager/` directory does not contain
`sourceme-manager.sh`. The runner selects the private manager as the working
directory of each lifecycle command:

```sh
export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH
cd /scratch/eygao/iris-cy/sims/firesim
source ./sourceme-manager.sh --skip-ssh-setup
/scratch/eygao/iris-cy/.conda-env/bin/python3 \
  /scratch/copparihollmann/iris-model/firesim/run_prepared.py \
  /absolute/fresh/job --execute --authorization-id ACTUAL-RECEIPT-ID --timeout 1800
```

The sourced environment references an absent local commercial-license script;
that warning is retained, while the Conda FireSim manager environment is loaded.
It does not affect the remote installed Vivado Lab tools. Do not use shell
`set -e` to abort solely on that unrelated final source warning.

The successful broad job is `runs/fpga-user-authorized-v12/broad-fit`. It bundles
736parentcases,3680trialcases,6750regions and five trials in one ELF, covering
all seven nonempty hart subsets. Its source-supported host-FESVR quantum is128
instead of2004765. Its remote wall watchdog is1500s, with30s kill grace and
GNU timeout's REQUIRED `--foreground` option; the host phase timeout is1800s.
There is no `+max-cycles` bound. This changes the reference fingerprint; it is not a CPU/memory timing
override. The original8f driver remains unchanged. V9's successful smoke used
the original loader quantum. Do not interpret its5,372,770,202 cumulative driver
cycles or89.6s simulation wall time as program/kernel timing.

Preserve both failed broad attempts. V10's oversized `+max-cycles=100000000000`
overflowed the archived scheduler's signed32 `atoi`, cutting off after1,624
correct regions. V11's initial timeout wrapper created a background terminal
group and stopped before startup. Standard kill killed its driver; after complete
inspection and exact boot/PID/start/UID/prior-CWD ownership proof, only its stopped
management wrapper was resumed to reap the already-dead child. A fresh guarded
standard kill completed cleanup before archive/lock release. No driver was
restarted or run directly. The diagnosis and local PTY reproduction are in
`build/fpga-v11-startup-diagnosis-v1`. The corrected wrapper passes real local
terminal initialization/expiry tests and refuses overflowing/ambiguous cycle
bounds. The complete FireSim local suite now passes144tests.

## Evidence and campaign separation

After owned cleanup, the runner archives outside the job with the unchanged
user capture utility, on success and failure. Capture errors are distinct from
guest failures. Uncertain cleanup retains the lock and withholds capture.
Use `analyze_campaign.py JOB --output FRESH-OUTSIDE-JOB` to verify every archive
member, all guest identities/checksums/completion markers and trial samples.
Setup observer data is in the manager DEBUG logs; analysis reads those exact
structured records. Transfer took only a few seconds in the observed setup;
in V12 the image transfer took2.851s, driver transfer1.787s, and programming
helper103.017s (flash including unpack/script transfer106.107s). Programming
dominated, so no staging cache or programming bypass was added.

The archive contains the managed UART and an identical ordinary-file cleanup
copy. Analysis verifies both inventories/bytes and selects one console stream;
different copies or multiple managed guest streams refuse. The first analysis
attempt is preserved at `build/fpga-v12-broad-archive-analysis`; it correctly
refused the formerly unsupported duplicate-copy layout. V2 records its repaired
analyzer source hash separately from the original archived analyzer hash.
Future jobs require fresh preparation after that source change.

Heartbeat, FASED CSV, sim-run script and raw UART are copied after cleanup.
Supplemental ordinary files from V9/V10/V11 are independently inventoried in
`build/fpga-early-runs-supplemental-v1` and archived separately at
`runs/fpga-early-runs-supplemental-v1.capture.tar.gz`; original archives are
unchanged. This image has no TracerV/AutoCounter/SynthPrint widgets. Its blank
latency-histogram file supplies no latency distribution, and aggregate FASED
counters do not provide per-hart attribution or runtime latency-setting readback.

The broad job is fitting data. Independent held-outs remain frozen separately
under `build/frozen-heldouts-zephyr-v2`; no real held-out timing was used for
fitting. No qualified calibration or held-out +/-2% result exists yet.

## Zephyr diagnostic campaign

The original285-region training ELF is
`cb4907f1ab776506fdfc93e2f60df33b3bd2b4492a0d4025742dc64901b1f32e`.
It passes the independent native functional gates at seeds0/17 but stalls on
the FPGA before `zephyr.fit.vme_or_copy.mask4.trial.0`, after25correct regions.
The exact ELF/image/driver/runtime/corpus repeat fails at the same boundary.
Both failures were bounded by the foreground180s watchdog and fully cleaned
and archived. Do not label the original program as passed because a diagnostic
ELF succeeds.

Four diagnostic ELFs each pass all285regions with independently verified
external archives: instrumented/fenced, instrumented/no-fences, original app
with only ten kernel FENCE instructions, and its exact-layout NOP control.
The latter two have identical loaded layout and ordinary symbols; only the
ten32-bit FENCE/NOP instruction words differ in loaded bytes. Their shared
saved hart2 vector-buffer address is64bytes beyond the failing original,
which also changes the initial L2 bank/route. No observer/breadcrumbs are
present in these two minimal controls. Both pass, so these results do not
establish an ordering fix. The independently checked comparison is
`build/fpga-zephyr-diagnostic-comparison-v1/report.json`, SHA256
`a42f22c2e80e749a9a891ab6a4600e3d02cd00d3f45bd49589b201cb59f42740`.
All diagnostic variants are explicitly timing-perturbed and excluded from
calibration; the causal component and production fix remain unresolved.

Use `prepare_zephyr_fit.py --help` for fresh frozen Zephyr preparation. Keep
the original build, all patches and each ready descriptor immutable. Its
`--diagnostic-ready` input checks exact build/ELF/source/gates and records
the changed experiment. Do not reuse a prepared job after its inputs change.
The actual managed launch command and full lifecycle remain as above; these
jobs use an outer360s phase timeout and remote180s foreground watchdog.

The separate `prepare_rvv_transport.py` helper freezes the120-region baremetal
LMUL1/2/4/8 transfer control, two native seed gates, independent byte/FNV64
goldens, source/compiler snapshots and a60s foreground watchdog. Hart2 is the
sole vector actor, hart0 dispatches with a bounded CLINT watchdog, hart1 waits
in WFI. Five trials compare four-group loads/stores with and without drains
at short and full vector lengths. This is a diagnostic separation from Zephyr,
not an isolated throughput or OS timing benchmark. Copyback, source checks,
owned cleanup and archival are identical to the broad campaign.

The actual baremetal transfer job `runs/fpga-rvv-context-transport-v1` PASSED
all120regions/five trials, including unfenced LMUL8 at full256-byte length.
Archive verification is
`build/fpga-rvv-context-transport-v1-archive-analysis/report.json`; archive SHA256
`816570bd32c77d1f55844586405bac1368277f2e0a77f9912e5e5b993a478f40`.
All four phases passed23.163/115.416/37.378/23.512hostseconds, followed by
independent archive analysis and a complete idle inspection. This does not
establish interrupt-time Zephyr context correctness or identify the original
stall's cause. Per-trial modeled-time calibration is still unqualified.

The separate page-boundary/CSR batch is prepared with
`prepare_rvv_transport.py --page-boundaries --acceptance-report ...` and freezes
2,550regions, five trials, zero/varied data, every group and32-byte page split,
load/store/both controls, per-hart runtime vlenb checks and output byte guards.
The exact ELF passes both native seeds and22adversarial transcript controls.
Its first real run, `runs/fpga-rvv-page-transport-v1`, fails boundedly after
1,174independently correct regions at the fifth repeat of unfenced store
group0 crossing a page128:128. Earlier four repeats pass. The guest CLINT
watchdog reports the case and exits1; full owned cleanup/archive passed.
Archive SHA256 `31e92e0610a950d14f36b3e4a319b534256eeefeeb5a8c41415fc924dd65b39b`;
independent partial report `build/fpga-rvv-page-transport-v1-partial/report.json`.
This is a failing diagnostic, not a passed calibration or a proven Zephyr cause.

`--memory-probe-build ...` enables the separately reviewed read-only startup
register observer under the SAME managed lock/inspection/lifecycle contract.
See `MEMORY_OBSERVATION.md` for build, exact source/binary/header pins, guards,
raw capture and limitations. This page run actually returned stable
readLatency30/writeLatency30, in FASED memory-model target-clock cycles, before
driver initialization. No register writes/default fallback occur. These are
neither CPU memory latency nor source/image attestation or admitted calibration.

The exact page ELF repeated the same1,174-region prefix and watchdog case in
`runs/fpga-rvv-page-transport-repeat-v3`. All printed region objects, including
absolute cycle values, are identical across runs. Both owned cleanups and
archives passed; independent comparison is
`build/fpga-rvv-page-repeat-comparison-v1/report.json`, SHA256
`6ee3deea1101888c9f4072166f89a569b3d53a817171c5895721f51f7b499fb2`.
Repeat-v2 was a separate safe refusal before any hardware action when a process
appeared during inspection. Preserve it; V3 used new preparation and checks.

The original-layout two-ADDI saved-vector cursor-shift control also fails at
the same25-region Zephyr boundary. Its all-hart shifted-copy/slack/source proof
and independent comparison are recorded in CURRENT_STATUS. Address shifting
alone is insufficient. No production fix has been certified.

`HART2_VECTOR_INVESTIGATION.md` records exact reproducers, source/control scopes,
raw archive identities and remaining hypotheses. `summarize_fased.py JOB
--output FRESH-OUTSIDE-JOB` verifies archived raw FASED CSV and emits JSON.
It deliberately leaves missing target timestamps, bandwidth, per-hart attribution,
bin thresholds and wrap/reset accounting unresolved. In particular, the inspected
source's final histogram bin never counts overflow; do not sum bins as an
exhaustive clock denominator or occupancy measure.
