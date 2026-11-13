# Live event-clock integration

The graph now drives actual Spike instruction completion in an **uncalibrated
integration fixture** mode. Synthetic fixture costs are not Iris timing parameters
and must not guide workload placement or tuning.

Fetch and interrupt checks happen before issue. A fetched instruction's handler
waits for its shared-clock completion event, including loads/stores/atomics.
Each hart currently has one instruction in flight; per-hart dependency edges and
shared resources constrain events. Synchronous faults and interrupts get explicit
trap-entry events. Interrupts arriving in flight are taken after completion.

`mcycle` follows each hart's clock divider, independently of `minstret`; CY/IR
inhibit and counter writes retain their own semantics. An explicit WFI policy
controls whether a parked hart's counter advances. CLINT and time CSR aliases
derive from the global event clock, and timer edges can wake an otherwise idle
machine. HTIF requests yield at the completion group that published them.

Run the actual guest integration checks after building the fork:

```bash
python3 timing/live_check.py
```

Eight successful runs and three rejection cases verify clock-vs-retirement
independence, counter writes/inhibit, time aliases, WFI wakeup, synchronous trap
cost, idle clock policy, seed reproducibility, unequal-latency shared-memory
visibility, immediate exit with busy peers, and per-hart DTB frequencies. The
receipt `build/timing-live/results.json` binds binary/compiler/UART, source,
ELF/profile/graph/log hashes, host speed and uncertified status.

Use `--iris-timing-fixture=FILE` and `--iris-timing-trace=OUTPUT.json`. The examples
in `fixtures/` require the explicit uncalibrated purpose. Every hart needs a clock
divider and WFI policy; every operation needs an explicit ordered match rule,
resource, positive base-cycle latency and issue interval. RTC divider, trap cost,
source label and maximum cycles are mandatory. Unknown rules fail closed;
claiming calibration in a fixture is rejected. Supplied DTB timebase and nonzero
CPU clocks must agree. A recorded scheduling seed varies ready-hart dispatch
deterministically; functional mode retains its separate round-based policy.

Trace output is an explicitly partial snapshot: peer operations can remain in
flight at termination. It is not a restart checkpoint. Event timestamps and
occupancy use base-clock ticks, while guest counters can be divided, inhibited
or rewritten. Uninstrumented memory/MAC metrics are unavailable, not zero.

The scheduler scans active sets rather than the entire retained history each
event. History remains for trace export. A real timing model still needs actual
Shuttle/Rocket pipelines, scalar-vector decoupling, vector/VME overlap, queues,
caches/NoC/DRAM resources, domain mapping and measured calibration. Fetch/MMU
walks and their PTE effects occur before modeled issue; their latency is not
represented. Host-assisted syscall transport is not calibrated serial-TL.
Passing these fixtures establishes integration semantics, not +/-2% accuracy,
complete board equivalence, or Zephyr certification.
