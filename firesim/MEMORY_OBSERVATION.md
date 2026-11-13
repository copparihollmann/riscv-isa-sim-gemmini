# Read-only startup memory settings

`memory_observation.py` optionally samples the reviewed FASED register layout
inside the managed hardware lifecycle. It runs after programming, complete idle
inspection and staging verification, before the simulation driver initializes.
The full `kill -> infrasetup -> runworkload -> kill` remains mandatory.

Build the exact reviewed observer without contacting hardware:

```sh
python3 firesim/build_memory_observer.py --output build/NEW-observer
```

The C source SHA256 is
`4990a9d4db717fc2b1cb30aa14b0f2b8653f30f9c58f93e9d164aae0f89b59e9`;
the reviewed native binary is
`0becce9fa23ffe402395ded77d3c761a83a0117095bd49e9d8a07028d38bf780`.
The fresh build retains exact compiler/assembler/linker, startup/library input
digests, preprocessed input, assembly, object, link map and four real regular-file
admission controls. The first attempted static link lacked the host static C
library and is preserved separately; the successful observer uses dynamic
linking. The remote interpreter/libc and Python identities are captured rather
than assumed to match the build host.

Add `--memory-probe-build build/NEW-observer` to fresh
`prepare_zephyr_fit.py` or `prepare_rvv_transport.py` preparation. It freezes the
observer executable, build receipt, inputs, helper and selected register/header
contract into the job before any hardware action. A changed source/helper/build
requires new preparation. Never amend an old prepared or executed receipt.

The runner rechecks complete all-user/device occupancy, account/boot/expiry and
shared lock immediately before and after observation. The remote helper checks
the same held token/account/boot/authorization before opening the device and
after reading it. It stages only into this run's private directory, verifies the
reviewed executable digest, uses isolated Python and a clean subprocess
environment, and verifies the XDMA character node resolves to the expected
`0000:01:00.0` PCI function. It uses no sudo and changes no device permissions.

The pinned C program opens `/dev/xdma0_user` with `O_RDONLY|O_SYNC`, maps one
page with `PROT_READ`, checks the FireSim presence word before/after, and samples
the read/write latency registers twice. A missing device, permission failure,
changed BDF/node, bad presence, unstable samples or all-ones response yields
unavailable values. There is no fallback to the source default. Probe failures
and partial transport bytes are archived separately from the guest outcome;
occupancy/ownership failures still stop hardware actions and may withhold cleanup.

Raw evidence is under the job's `memory-observation` directory and
`run.json.readonly_memory_observation_result`, archived after owned cleanup.
The recorded values are **startup register observations in FASED target-clock
cycles**. Driver initialization can override them if given memory-model
configuration arguments. The actual runtime/HWDB/plusargs remain captured.
They are not whole-SoC memory latency, CPU cycles, a memory latency distribution,
per-hart traffic, image readback, source-to-image attestation or admitted
calibration. Generic FireSim presence does not identify a particular image.

Local controls, including foreign occupancy before/after observation, unavailable
device behavior, malformed samples, stale inputs and partial transport, are in
`tests/test_memory_observation.py`. The complete FireSim suite passes138tests at
this epoch. No test opens an FPGA device.
