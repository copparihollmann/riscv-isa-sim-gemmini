The v2 observer captures all five source/binary-proved FASED configuration
registers after normal driver exit and before owned final cleanup:

| Register | MMIO byte offset | Value domain |
|---|---:|---|
| writeLatency | 0 | uint32, all-ones refused |
| readLatency | 4 | uint32, all-ones refused |
| writeMaxReqs | 8 | uint32, all-ones refused |
| readMaxReqs | 12 | uint32, all-ones refused |
| relaxFunctionalModel | 72 | integer 0 or 1 |

These are observed configuration values, not measured memory latency or automatic
timing-model admission. There is no source-default30/16 substitution. Latencies
use FASED memory-model target-clock cycles; they are not CPU/host cycles or total
load/store latency. Max-request values are configured limits, not measured
occupancy. Relax mode is read back explicitly rather than inferred.

`audit_fased_config_v2.py` checks25 actual byte sequences in the exact archived8f
driver, including names and offsets in both readable and writable address maps,
plus presence356/magic. The additional offset instructions are readable
0x5adf2/0x5ae18/0x5b339 and writable0x5b5a7/0x5b5cd/0x5b61f. Plain source
RegisterEntry reads are non-clearing; only write.valid assigns the node. The
v1 source, binary, helper, runner, packages and old jobs remain unchanged.

The new `readonly_fased_config_v2.c` opens hardware only with the explicit
`--read-idle-device /dev/xdma0_user` mode, O_RDONLY and a PROT_READ mapping.
Presence is checked before/after and every configuration field sampled twice.
The fake-only `--test-file-pair FIRST SECOND` mode deterministically exercises a
changing peripheral snapshot; both targets must be regular files and this mode
is never used for device access. It supplies no write path or control ioctl.
Fake-file controls plus strace verify target read-only opens/mappings, unchanged
file bytes and absence of target write/ioctl calls.

The new helper installs into a **fresh unused job only**, with its exact initial
manifest hash:

```sh
python3 firesim/memory_observation_postrun_v2.py --install \
  --job NEW_PREPARED_JOB --expected-prepared-manifest-sha256 EXACT_SHA \
  --probe-build build/fased-readonly-extended-v2 --host sohumpc
```

Root reviews the resulting new manifest SHA and alone launches the unchanged
managed lifecycle. FireSim's existing `post_run_hook` is used. The complete v1
normal-exit/golden, immutable-input/runtime, fresh complete-idle, authorization,
boot, account, token and shared-lock checks are retained. Even an owned remaining
device holder is refused. This child never releases the lock or modifies
`run.json`; observation failure remains separate from the guest result.

The local sidecar directory is `postrun-memory-observation-v2`; the remote
directory is `memory-observation-postrun-v2`. These do not collide with v1 or the
pre-init reader. The unchanged guarded remote staging program is reused with
only those output/executable names changed. The exact five-register build and
independent extended MMIO audit are input-bound and rechecked.

The local prototype has a deliberately non-executable manifest status. It proves
installation and local closure, not FPGA availability or a real postdriver read.
Full original-source/loaded-image attestation, actual transaction latency and
whole-memory timing qualification remain false. An unavailable field invalidates
the five-register observation instead of silently filling a default. Root must
collect new observations through a fresh authorized, inspected, locked managed
job; no hardware or privileged installation belongs to these local tools/tests.
