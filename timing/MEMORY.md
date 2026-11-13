# Memory transfer timing

`memory_path.hpp/.cpp` schedules explicit request/service/response stages on the
same native event graph. A stage has a sourced first-beat latency, launch
interval, transfer width and beat interval. A multi-beat transfer reserves its
shared port for the complete packet; requests from different harts contend on
that port. Separate declared ports can overlap. Functional memory effects run
only at the final response callback.

Every stage and port requires a source identifier. The returned transfer receipt
retains the original parameters, derived latency/interval, sources, access
address/size, and graph node IDs. A cache-line refill can transfer more bytes
than the guest access; callers must declare that transaction size explicitly.
Stage bytes are bytes on that stage, so do not sum different hierarchy levels
to obtain application traffic or arithmetic intensity.

The tests exercise three-hart serialization, independent banks, chained request
and response latency, receiving-domain clock alignment, completion visibility,
and rejected invalid paths and overflow. Their numeric parameters are synthetic.

The scalar memory extension connects this component to Spike instruction issue
in an explicitly selected integration fixture. `scalar_memory.*` extracts the
effective address of RV64 integer/FP loads/stores, C memory forms and A atomics
without reading memory or translating an address. Ordinary Spike execution still
checks instruction legality, privilege, PMP/PMA and access faults when the final
response completes. The adapter requires physical M-mode addressing, with MPRV,
virtualization and debug mode disabled. It fails with a model-capability error
for vector memory or unresolved addressing. This refusal does not declare the
instruction architecturally illegal. Existing fixtures without memory routes
retain their previous behavior.

The selected instruction cost schedules address generation. The request then
passes through the declared memory stages. Each stage uses its own clock period;
guest memory effects and retirement happen only at the final response. All harts
reserve the same declared ports, so address selection and contention affect the
program's own `mcycle` reads and which value another hart loads. No host-side
execution of a load/store happens ahead of that response. Fetches are not routed
by this extension, and a hart still has only one instruction in flight.

The fixture grammar adds:

```
memory_port PORT LANES SOURCE
memory_region HART BASE SIZE SELECT_MASK SELECT_VALUE PATH
memory_stage PATH NAME PORT FIRST_LATENCY LAUNCH_INTERVAL BYTES BEAT_BYTES BEAT_INTERVAL SOURCE CLOCK_PERIOD base_cycles
```

`BYTES=access` transfers the scalar access width; an integer declares a fixed
packet size, and zero is a fixed-latency stage without beat parameters. Paths
contain stages in declaration order. A region requires one unambiguous match
for every byte of an access. Explicit selectors can represent source-verified
bank bits; a crossing request needs splitting and is refused for now. Different
hart-specific regions can share a port. Unmapped addresses, missing ports,
ambiguous matches and unknown parameters fail closed. The graph's
`memory_transactions` retains addresses, widths, kinds, stage parameters, sources,
node identities and pending/inflight/completed state. Pending stages are not
reported as completed traffic at HTIF exit.

Run the integration checks against a binary that includes the extension:

```sh
python3 timing/memory_live_check.py --binary spike/bin/spike-iris-functional
```

The checks use six real guest runs: all-three-hart TCM/scratchpad/DRAM regions
with two costs, reversed load/store completion visibility, and a recorded seed
repeat. Invalid profiles and functional-positive vector/MPRV guests check
capability refusals separately. The standalone C++ corpus exhausts compressed
address immediates and checks integer/FP/atomic widths, route bounds and clocks.

There are no Iris latency defaults or qualified cache/NoC parameters. Cache
state/replacement/coherence, vector request expansion, NoC protocol and actual
miss routing remain unfinished. The fixture deliberately models uncached scalar
paths and does not claim that all DRAM accesses on Iris miss its caches. Passing
a supplied path does not certify correspondence to the SoC or +/-2% accuracy.

Encoding extraction follows the pinned Spike
`72958551566a30f19444bd7e354552824e4d0a98` `riscv/decode.h` immediate fields and
`riscv/insns` scalar/RVC memory handlers. Source RV64 C forms are distinguished
from RV32 compressed FP forms. The functional decoder remains the authority
for dynamic legality; the timing decoder never authorizes an instruction.

`hardware/memory-paths.json` records the configured routes and remaining unknowns.
Calibration must distinguish TCM, scratchpad, L1 hits, L2 hits/misses and serial-TL
DRAM, including mixed scalar/vector accesses and all-three-hart interference.
Unknown latency or bandwidth remains unavailable; raw link width, FPGA emulation
MHz and inclusive-cache sizing hints do not establish transaction latency.
