# Reset and retained-image reuse audit

The matching Iris driver completed two three-hart smoke runs without reflashing.
Each produced the same twelve region records and exited successfully. A third
run failed without any region records; subsequent root-owned reads returned
all ones for presence, initialization and parameter registers. The device is
not currently a valid calibration source. See the immutable raw trials and
[reuse result](../runs/fpga-smoke-access-enabled-001/reuse-check.json).
The failure's cause is unresolved; this sequence does not prove its cause.

The [source audit](reuse-source-evidence.json) shows that each driver's
`simulation_init()` rewrites the ResetPulse bridge's length (default fifty target
cycles, maximum 1023). That reset is the harness reference reset. TSI queues reset
on the target reset; FASED waits for outstanding host memory, then resets its
model and ingress/egress state. TSI's method named `reset()` alone only releases
hart 0 with MSIP; it does not reset the harts. TileResetSetter controls tile reset
domains, rather than all uncore and host bridge state.

Target reset does not clear every host-side state element. UART codec FSMs and
clock/profile counters retain host state, while backing memory contents are not
automatically cleared. FASED configuration registers also persist unless runtime
arguments explicitly overwrite them. These distinctions require validation
before retained-image runs can replace the managed deployment lifecycle.

The driver's performance summary uses cumulative `end_tcycle` without a starting
target-cycle subtraction. Its global cycles/effective MHz/FMR therefore do not
measure a fresh run after retained-image reuse. Guest `mcycle` region deltas are
separate observations and remain in the raw logs; the source/image association
and calibration eligibility remain unresolved.

`readonly_fased_latency.c` is a separate root-operated diagnostic, with the
[source proof](fased-read-source-evidence.json). It maps the known XDMA control
device read-only and validates generic FireSim presence at byte offset 356 before
accessing parameter registers at offsets zero and four. It checks presence again
after sampling. Invalid presence, unstable values and all-ones parameter samples
fail with `selected_parameters:null`; invalid bus responses are never timing
values. Four regular-file fixture tests pass. This audit agent performed no
hardware read or mutation through that tool.

The actual runtime `readLatency` and `writeLatency` observations remain null.
Source defaults of thirty are not measurements, and addresses zero/four are not
parameter values. Recovery and further hardware runs belong to the root agent's
approved deployment path; no helper here flashes, resets, removes modules or
changes PCIe permissions.
