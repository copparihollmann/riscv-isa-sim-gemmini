> Installed/authorized update (2026-11-06): user authenticated and completed the reviewed installation. Exact installed SHA256 is 5934aaa1907605a05cd6e9bca6c28e98fa6ab62dfb8339c5c5aabde59ac526d8. Root inspection passed with214 processes, no busy jobs/holders/errors at installation check; recheck for every action. Lock parent /scratch/firesim/iris-locks is root:firesim2770. User explicitly authorized bringup/batches when idle. Mandatory root-owned reservation JSON was an agent-invented format and has been superseded by current user authorization + user-owned receipt + group lock fpga0. Older installation/missing-allocation statements below are historical. Read OPERATING_RULES.md for current policy.

# Read-only FPGA inspection capability

The coordinator needs complete all-user process, FD and mapped-device visibility before any managed FireSim action. The locally staged `firesim-iris-inspect` supplies that capability without granting a user-controlled root interpreter. It has not been installed or invoked remotely by this work.

The latest access observation is `build/access-privilege-details-20261106/report.json`: agustin belongs to sudo and firesim and may invoke `/usr/local/bin/firesim-*` without a password. Generic noninteractive sudo still requires authentication. The existing unprivileged scan could not inspect 46 processes, the exclusive operator allocation was absent, and 27 XDMA nodes were root-owned mode0600. Those are dated observations; recheck them before use. This helper neither reserves the FPGA nor changes device permissions.

## Operator installation

Installation is a site operator action in an independently authorized root shell. Agents must not install this payload through other FireSim helpers or use those helpers as a general root write primitive.

1. Review the source and the local release manifest. Obtain its SHA256 through the trusted review channel, independently of an editable user directory. The exact expected hash is `inspector_sha256` in `release.json`.
2. Confirm this is the actual FPGA host's initial PID/procfs namespace, with a protected system `/usr/bin/python3`, `/usr/bin/env`, standard library and `/usr/bin/sudo`. Inspect `/`, `/usr`, `/usr/local`, `/usr/local/bin`: every component must be a real root-owned directory without group/other write access. If any component is untrusted, stop and have the operator repair the installation policy; do not weaken the inspector checks.
3. Copy the reviewed payload into an operator-controlled root-only staging directory. Recompute its SHA256 there and compare the independently obtained expected hash. Do not execute the user-owned copy. The following commands illustrate the copy and install only; substitute a reviewed source path and verify the hash before the last command:

   ```sh
   install -d -o root -g root -m 0700 /root/iris-inspector-install
   install -o root -g root -m 0600 /reviewed/source/firesim-iris-inspect /root/iris-inspector-install/candidate
   sha256sum /root/iris-inspector-install/candidate
   # STOP unless the hash equals the independently reviewed release hash.
   install -o root -g root -m 0755 /root/iris-inspector-install/candidate /usr/local/bin/firesim-iris-inspect
   sha256sum /usr/local/bin/firesim-iris-inspect
   stat /usr/local/bin/firesim-iris-inspect
   ```

4. Review sudo policy with the operator. The observed existing NOPASSWD prefix covers this fixed filename; no generic Python, shell, stdin script or user-supplied path grant is needed. Prefer a site-specific exact no-argument command rule if changing policy. Do not broaden privileges as an agent.
5. The coordinator may then perform its read-only probe. Its only elevated command is exactly:

   ```sh
   /usr/bin/sudo -n -- /usr/local/bin/firesim-iris-inspect </dev/null
   ```

The payload's shebang selects `/usr/bin/python3 -I -S`. It rejects arguments, input other than `/dev/null`, non-root real/effective identity, a different install path, unprotected source/ancestors, malformed sudo caller identity and command metadata. The runner independently compares exact source SHA/version, SSH caller UID/name, host boot and root inspection identity. A missing helper permits unprivileged fallback only if that scan is genuinely complete; an unknown helper, failed sudo, malformed response or incomplete root scan fails closed.

The helper reads fixed `/proc`, `/sys`, `/dev` metadata and fixed FireSim database/allocation paths. It does not open FPGA devices, execute subprocesses, write files, change modes, allocate, lock, flash, reset or kill anything. It checks FD links and maps even when cmdline is empty; PID reuse, inaccessible process data or newly appearing PIDs make the scan incomplete. PCI-resource mappings use canonical and bus sysfs paths; XDMA, XVSEC, VFIO, UIO, physical-memory and anonymous VFIO/IOMMU references block operation conservatively. An unrelated PCI resource holder is uncertainty, not permission to proceed. A scan cannot exclude a process starting after the scan: genuine site allocation and a shared launch/lock policy remain required.

## Managed path and capture

`managed-path-audit.json` binds the observed Corigine source, helper hashes and privilege branches. Corigine inherits the Alveo flow: copy infrastructure/extract driver, remove XDMA, program through the installed FPGA utility, load XDMA, and apply XDMA/PCIe permissions. The five active helper source hashes match the dated root coordinator observation. This is source/read-only evidence; no setup has been attempted under the new privilege state. `has_sudo()` tests generic `sudo -ln true`, so its false result does not mean the fixed helpers are unavailable. AWS/rootfs/switch/pipe privilege branches are outside the prepared bare-metal no-network workload. Re-audit before enabling them.

Prepare fresh jobs after every runner/helper/input change. Both preparers accept `--observability-report`; the Python API is `prepare(..., observability_report=path, profile_interval=1000000)`. The historical default audit is `build/firesim-observability-candidate-v2/report.json`, SHA `3c11c53f38a275ebfa29f850738071404c7516b817721d26a74623021446bc0f`. Supply the reviewed audit explicitly for each new candidate; v2/v3 inventory schemas are accepted, with their exact report SHA and matching image/driver archive hashes frozen into the prepared job. Root selected the original archived driver from the same bitstream build for the next reference, because the previous candidate changes the TSI host-memory loader configuration. That replacement requires its own driver bundle and audit; do not mix identities. Preparation records the positive target-cycle profile interval. An inventory identifies a candidate, not the loaded image. Allocation/inspection, complete managed setup and deployed association still require proof.

Every authorized job uses kill -> infrasetup -> runworkload -> kill. Allocation, boot, all users/device holders and the held shared lock are rechecked before every phase and cleanup. Failed or uncertain cleanup retains the lock and withholds a quiescence claim/capture. Never recover that lock automatically or kill another account/run. Only the coordinating agent launches hardware.

Each phase has independent raw `.stdout` and `.stderr`, elapsed host seconds, exit/timeout state and actual manager/runtime/HWDB digests. Setup host time includes transfer and programming unless their internal logs provide separately measurable boundaries; the runner does not invent that split. Before workload launch, a read-only audit hashes the privately staged image archive, driver archive and ELF, retaining its raw streams even on refusal. This is a transport check, not proof of what was programmed. Images are not retained/reused to bypass setup.

After confirmed owned cleanup, optional copyback records `memory_stats0.csv`, `latency_histogram.csv` and `sim-run.sh`, with explicit missing/empty/error states. Optional evidence failure does not become a guest correctness failure. This candidate has periodic FASED outstanding/beat/error counters, but no instantiated TracerV, AutoCounter or SynthPrint. Its latency histogram is unavailable/empty; selected read/write latency values and range counters are unavailable. Do not infer their existence from linked generic class symbols.

The unchanged user-owned `capture_run.py` runs after cleanup and lock release, on success and failure. Its archive and raw utility stdout/stderr are outside the job. A changing-file refusal preserves `.partial`; capture failure has a separate status and never replaces a guest failure or changes a completed guest into a functional failure. Archives contain the pre-capture run manifest; the current run manifest additionally records archive outcome/hash, avoiding a circular hash claim. Bundle broad compatible cases and repeats inside one ELF, preserve fitting/held-out separation, and retain raw measurements and unavailable instrumentation explicitly.

## Local verification

`python3 -m unittest discover -s firesim/tests -v` exercises mocked lifecycle/privilege/transport failures, synthetic procfs/device holders and local process/capture streams. It does not SSH, install the helper, open FPGA devices or execute a hardware lifecycle. `release.json` records the exact local source/test results. Full FPGA health, loaded-image association, calibration and +/-2% validation remain unqualified.
