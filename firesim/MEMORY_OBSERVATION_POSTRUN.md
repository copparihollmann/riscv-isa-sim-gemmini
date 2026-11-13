The opt-in `memory_observation_postrun.py` captures the existing reviewed FASED
latency registers after a normal driver/guest exit and before the coordinating
runner's owned final cleanup. It uses FireSim's existing workload
`post_run_hook`; the frozen runner, existing pre-init observer, driver, image and
previous jobs remain unchanged.

Installation is only for a fresh unused prepared job, identified by its exact
pre-install `run.json` SHA. It adds a workload hook, a frozen plan, the unchanged
reviewed read-only observer executable and a separate local output directory.
Run the installer as the final preparation step after authorization, goldens and
the parent input closure have been added:

```sh
python3 firesim/memory_observation_postrun.py --install \
  --job NEW_PREPARED_JOB --expected-prepared-manifest-sha256 EXACT_SHA \
  --probe-build build/fased-readonly-managed-v2 --host sohumpc
```

No installation command accesses the network or device. Root reviews the new
prepared hash, then alone launches it through the unchanged managed runner. The
usual kill/setup/run/kill, complete all-user/device inspection, current standing
authorization, boot identity, shared lock and ownership-checked cleanup remain
mandatory. `--prototype-only` makes the hook refuse any observation. The local
prototype tool additionally changes its prototype manifest's status so the
unchanged `run_prepared.verify` refuses execution before hardware access.

The installed hook runs inside the managed `runworkload` process after FireSim
has observed the driver exit and copied back results. Corigine's deploy manager
inherits an empty `terminate_instance`; this step does not reset/reprogram the
board. Root's parent process still holds its shared lock and subsequently runs
the mandatory final kill and capture. The hook requires the exact normal driver
exit-zero marker, driver PASSED, all declared independently checked region
goldens, and no fatal/failure marker. A manager exit alone is insufficient.

The hook verifies immutable source/prepared identities, actual runtime identity
with only the runner's owned-directory substitution, the current account/boot,
authorization receipt and lock token. It performs complete fresh idle checks
both before and after the read; even a remaining owned device holder is refused
because the driver should already be gone. No shared lock is acquired/released
by this child. Unknown/foreign occupancy prevents the read. The parent retains
its independent cleanup checks and will withhold unsafe cleanup as before.

The remote output directory is `memory-observation-postrun`, distinct from the
old pre-init `memory-observation`. The binary uses O_RDONLY/PROT_READ, checks
the FireSim magic before/after, and reads offsets0/4 twice. The new helper uses
the exact reviewed remote observer program with only its output directory
changed. It preserves device/runtime/binary identity and lock/receipt checks.
The child writes `postrun-memory-observation/observation.json` plus raw transport
sidecars and **never modifies `run.json`**; the parent retains an in-memory
manifest. Optional observation failure stays separate from the guest result.
The existing post-cleanup full-job capture includes these local sidecars.

The archived8f driver ELF independently confirms readable and writable
writeLatency0/readLatency4 (entry PCs0x5acff/0x5ada6/0x5adcc and
0x5b4ca/0x5b55b/0x5b581), master presence356 (rodata0x7cff0) and magic
0x46697265 (0x6b5e4). Source `FASEDMemoryTimingModel::init` writes supplied
configuration once; `finish` only operates optional histogram/range readouts and
files. Its existing archive has no latency histograms/range registers to select.
Archived `fpga_shutdown`0x59060 only unmaps/closes host handles, without FPGA
control writes. Co-located Combined SV exposes the registers directly on read
and changes them only on host reset or explicit MCR write. Current inspected
sources and the exact archived function bytes are both bound; full original
source/build-to-loaded-image attestation remains false.

A successful result means **post-driver configuration registers** in FASED
memory-model target-clock cycles. Subject to the bound source behavior and no
intervening reset/other writer, it establishes the terminal configured values
after initialization, rather than the old startup defaults. It is not a measured
transaction latency, total CPU load/store latency, memory distribution, source
clock conversion or physical image readback. A final value alone does not prove
the entire historical run without those source/ownership premises. No new value
is inferred from the source reset default. Zero and other observed values are
observations, not automatic admissible timing-model parameters.

The unchanged binary captures only read/write latency. `readMaxReqs`,
`writeMaxReqs` and `relaxFunctionalModel` remain unobserved; do not substitute
16 or any other source default into a physical service claim. Capturing those
would require a separately reviewed extended no-write binary. No FPGA run is
part of the local qualification or mock tests.
