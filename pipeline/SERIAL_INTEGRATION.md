# Successor to frozen live-cache epoch 1ac5e317

The frozen predecessor is `build/rocket-fabric-frozen-1ac5e317-v2`;
manifest SHA256
`e6dc12cc32f87118a8093cedbd9b75c92c6d78174e0392cdac0d62cc8bac1a27`.
Its source tree and build are immutable. New work starts in
`pipeline/riscv-isa-sim-rocket-serial`, from Spike
`72958551566a30f19444bd7e354552824e4d0a98` plus the exact predecessor overlay.
Primary Spike, board/CRT files and all FireSim inputs stay unchanged.

The next physical boundary is the new `iris::memory_system::System`: real
Rocket cache/tile/CDC/NoC/L2/cork plus the source MBUS/SerialTL/Bringup path.
Its remaining external inputs retain original component names; `path`
exposes the actual FASED AXI boundary. Four post-cork A/D joins are internal
and cannot be replaced by ready/data values. The LP is a separate source
peer; its parameters have no calibrated default.

The owner must evaluate Frontend/IBuf, HellaCache arbiter, System and LP to
one global fixed point before committing any selected peer. The source
relative calendar has Iris/Rocket/uncore on virtual tick multiples of 2,
Bringup/LP on every tick and Serial on multiples of 10. Intermediate Bringup
edges must run; a CPU-cycle-only timeline would lose real state transitions.
The first native mode will explicitly bind these relative periods and source
clock identity. There is no extra adapter/handoff edge and no direct
TileLink-to-30-cycle delay.

The lower-level component proof uses read/write latency 30/30 and request
limits 16/16 as explicit fixture parameters. Startup read/write 30 has also
been observed on the FPGA, but image/source association and request limits
remain unqualified. The positive component fixtures do not qualify the full
FASED functional ingress/egress or host-token bridge. Reset-only diagnostic
masking is an explicit two-state reference scope, not the default source
assertion behavior. The fixed-context composed SDK must be frozen before a
new native binary binds it.

`pipeline/axi_functional_fixture.hpp` provides a separate functional fixture,
not source timing. It snapshots data and knownness at actual accepted AXI
AR, retains exact ID/length/size ownership until final R, pairs independent
AW/W streams (including W before AW), applies byte strobes only once the
complete owned burst is known, and retains ownership through B. Conflicting
outstanding read/write or write/write regions refuse. It never rereads
mutable backing at LP egress release. Physical backing stays separate from
Spike's architectural cached-store mirror. The source LP requests functional
egress one target edge before its R/B valid; the caller supplies the already
owned snapshot on the following target phase.

The first actor proof is `build/axi-functional-fixture-v1/results.json`:
10,026 checks, 11 explicit refusals and 10,000 bounded streaming requests.
It adds no timing, recorded source state or internal ready input. Remaining
functional-order/token assumptions must stay explicit in the native mode and
report. Unqualified conflicting cases must fail closed.

The live scalar CPU machinery inherited from 1ac keeps EX request, MEM
kill/store data, WB architectural retirement/replay and later RF response
separate. The predecessor's four positive directed ELFs and early-retire
ELF pass independently on the whole saved CPU. Source IRQ with pending
loads, load-to-x0 policy, architectural memory-fault delivery, dependent
memory misses with unknown operands, vector/atomic memory, Shuttle data
cache peers and external TCM/scratchpad targets remain extensions to build.
All three harts remain present; parked-peer tests do not certify full SMP
coherence or Zephyr on the new hierarchy.

Saturn ownership metadata is separate from functional completion. A source
EX candidate may be killed in MEM or replay; PFC/IFC/dispatch/VAT generation
must establish the command owner. Accepted vector memory effects can occur
after front COM. A whole ordinary Spike vector step at COM would publish
future memory writes too early; later integration needs private functional
intents and actual VRF/TL commit events. No nearest-PC attribution or guessed
vector opcode cost is an acceptable substitute.

## Executed native path

The isolated candidate now executes real ELFs through this complete physical
path. Build with `python3 pipeline/build_native_rocket_serial.py --jobs 24`.
The matched ABI4 UART plugin is generated beside the binary; never substitute a
plugin from a different native SDK. `pipeline/rocket_serial_fixture.py` generates
an explicit test fixture for the saved reference's relative calendar. It requires
all three physical harts at period 2, a 1 GHz virtual phase unit, Bringup/LP period
1 and Serial period 10. The source-clock derivation and independent calendar
proof are dependencies of the frozen MemorySystem capsule, not FPGA clock
measurements. The numeric LP parameters remain test inputs.

```sh
python3 pipeline/rocket_serial_native_check.py --output build/my-serial-directed
python3 pipeline/rocket_serial_guards.py --output build/my-serial-guards
python3 pipeline/rocket_serial_writeback_check.py --output build/my-serial-writeback
python3 pipeline/rocket_fabric_compatibility.py \
  --binary build/spike-rocket-serial-v1/spike --output build/my-functional32
python3 pipeline/rocket_fabric_parent_replay.py \
  --binary build/spike-rocket-serial-v1/spike --output build/my-legacy-replay
```

Final-byte gates are `build/rocket-serial-native-final-v2` (five positive exact
prior ELFs and eight capability refusals), `build/rocket-serial-guards-v2`
(thirteen calendar, source-identity, width and explicit-scope refusals),
`build/rocket-serial-functional32-final-v2` (all 32 original functional stdouts)
and `build/rocket-serial-parent-replay-v2` (24 legacy graphs, precise IRQ and
Zephyr scalar/mixed graphs unchanged with new flags absent). The real late-ROM
load retires at virtual phase 8530, receives its data at 8576, and permits twelve
independent retirements between those events. Those values are predictions of
this explicitly configured candidate, not calibration numbers.

`build/rocket-serial-writeback-v2` executes nine dirty congruent lines, observes
20 real AXI reads and nine real AXI write transactions, and reloads every line
against independent integer goldens. All nine write actors complete; no AXI read
or write remains at exit. The congruence uses the source four ways, 512 KiB and
four banks (`IrisConfigs.scala:214–219` at chipyard
`b4542facf6cc9457f6e358e8f80a8b3a0ff5df19`), with the elaborated nine-bit bank set
in `build/cache-hierarchy-source-v1/rtl/InclusiveCacheBankScheduler.sv:154`.
The exact same writeback ELF also passes the independently reset whole saved CPU
in `build/rocket-serial-writeback-whole-CPU-v1`. That functional comparison uses
the saved standalone RTL's own external memory environment and supplies no LP
latency fit or whole-image equivalence claim.

The writeback gate exercises an ELF layout with a zero-file-size PT_LOAD BSS
whose file offset lies beyond EOF. That is valid: the new private
`serial_backing.hpp` validates offsets only for file-backed bytes and explicitly
zero-fills BSS. The predecessor's backing is unchanged. Unknown non-ELF backing
bytes still refuse; accepted byte-strobed outer writes are the only subsequent
physical backing updates.

`build/rocket-serial-peer-component-v1` checks the same source composition before
native integration (110,492 checks over seeds 1/17), including mixed RVC parcels,
cross-fetch instructions, scalar cache producers and a dirty-owner handoff to
Icache while DRAM still has the old bytes. `build/rocket-serial-lifecycle-v1`
checks failed construction, foreign context restoration, destruction, repeated
same-edge evaluation, joined-input refusal and commit phase guards (34 checks,
14 refusals). The private AXI actor has 10,026 checks/11 refusals, including
10,000 bounded requests and read snapshots protected against later backing
mutation. JSON/Perfetto output for the actual writeback graph is under
`build/rocket-serial-writeback-profile-v1`.

This epoch retains source-based Rocket scalar EX/MEM/WB/late-RF behavior and the
predecessor's explicit capability refusals. It does not yet connect harts 0/1
scalar data caches, Saturn vector memory or shared FPU. The directed new-path
guests retain all three physical harts and park the other two; they do not
qualify SMP coherence or Zephyr on this new hierarchy. The old qualified
functional Zephyr mode continues to work with the new flags absent. Memory
agent and Saturn bridge work proceed in separate successors; these limitations
are development boundaries, not claims about Iris's hardware capabilities.

The full FASED functional ingress/egress/host-token bridge, full internal
knownness, pending-load IRQ/trap delivery, full source memory fences/atomics,
all-three-hart source memory/Zephyr qualification, loaded image association,
held-out whole-workload timing and +/-2% remain incomplete. No certification
flag is promoted by these component or native functional passes.
