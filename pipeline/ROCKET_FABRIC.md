# Isolated Rocket frontend and scalar memory integration

This successor of frozen `2539e85c` connects live Spike hart 2 to the actual
saved Iris Rocket Frontend/IBuf, scalar/PTW/Saturn HellaCache arbiter, Rocket
L1D, tile width/xbar adapters, both asynchronous crossing halves, full NoC,
four inclusive L2 banks, buffers, bank binder and cork. Harts 0/1 retain their
previous source Shuttle frontend/scalar path; their data caches are **not**
connected to this fabric. All three physical harts and reset PC `0x10000`
remain present. This is an isolated development binary, not the published
primary simulator or an accuracy certification.

The source is saved standalone IrisConfig FIR
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
The pinned Rocket revision is
`fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0`, Shuttle
`a536ed1df91a0f65770e36758291d02a8cb929c4`, Saturn
`536774bd4c5e3bcd7813a4a0dc72fc87e5818532`, Chipyard
`b4542facf6cc9457f6e358e8f80a8b3a0ff5df19`, and upstream Spike
`72958551566a30f19444bd7e354552824e4d0a98`. The native source overlay is
recorded separately. No association with Ethan's deployed image is inferred.

`pipeline/rocket_fabric_peer.*` settles the three physical peers to a global
combinational fixed point, samples them, and commits selected domains with
the preedge inputs held. There is no additional handoff edge. The real tile
xbar assigns Icache source ID `0x42`; the adapter supplies only the original
Icache valid/address pins. The exact saved `HellaCacheArbiter_1` assigns PTW,
scalar and vector ownership/tag bits and its S1/S2 owners. Joined ready/data
pins cannot be supplied by the caller. Every external physical input has an
explicit known mask. Scoped Verilator contexts are restored on every public
phase, error, construction and destruction.

The scalar path models source EX request, MEM store data/kill, WB nack/replay
or architectural retirement, scoreboard setting, and later replay-response RF
write. A load can retire before its result is ready. RAW/WAW consumers wait
for the actual response or follow the source load-use replay; independent
instructions can retire in the meantime. Same-edge fast-load forwarding is
resolved from the real cache output before final EX address/data evaluation.
The adapter verifies that this combinational revision leaves the already
observed WB response unchanged. Source `replay_next` handles the RF port
conflict rather than overwriting a simultaneous scalar result.

Relevant source contracts are RocketCore.scala 627–638 (load miss/EX replay),
714–738 (MEM kill/replay), 763–853 (WB faults/nack, early retirement and late
RF arbitration), 1030–1089 (scoreboard, RAW/WAW/load-use and grant bypass),
and 1182–1207 (cache request/store-data/kill). The independent read-only CPU
phase proof is `build/rocket-memory-phase-proof-v2/report.json`; it observes
actual pre/post source edges, not inputs to this model.

The current native scope is M-mode with MPRV clear. It supports ordinary
RV64 integer scalar loads/stores, including their RVC expansions, in the
source cache pipeline. Named capability refusals cover load-to-x0 response
policy, atomics, FP/vector memory, architectural memory-fault delivery,
pending-load IRQ/trap contexts, translated data access, unconnected Shuttle
data peers and external TCM/scratchpad service. A dependent memory address
from a speculative missing load also refuses until its source knownness
policy is implemented. These are development boundaries to extend, not
claims that the Iris hardware lacks those instructions or memories.

The outer four-bank and CBUS actors in this epoch are explicitly synthetic
functional test fixtures. Their first-response/gap periods are mandatory
parameters in uncore edges. They are not Iris, serial-TL, DRAM or FASED timing
defaults. The native fixture uses separate physical ELF PT_LOAD backing:
uninitialized bytes refuse, BSS zero-fill is explicit, and only accepted
external Put beats update that backing. An architectural cached-store mirror
does not update physical DRAM behind the source caches. ROM/CBUS callbacks
are explicit external functional actors. Cacheable cold misses can nack and
retry; uncached reads can retire before their later data response. Those
behaviors are tested separately.

Build and exercise the isolated candidate:

```sh
python3 pipeline/build_native_rocket_fabric.py --jobs 24
python3 pipeline/rocket_fabric_load_check.py --output build/my-load-gate
python3 pipeline/rocket_fabric_directed_check.py --output build/my-directed-gate
python3 pipeline/rocket_fabric_compatibility.py --output build/my-functional32
python3 pipeline/rocket_fabric_parent_replay.py --output build/my-parent-replay
```

The new fixture lines are deliberately opt-in; the ELF path and external
service identity are explicit:

```text
rocket_fabric explicit-synthetic-external-service 2 3 1 /absolute/program.elf explicit-test-service-not-Iris-latency uncore_edges
rocket_scalar_memory source-cache-M-mode
```

The initial native composition requires Rocket and uncore to share the same
declared phase/divider, matching the saved component reference. The phase API
keeps the domains distinct. A later isolated successor will add the actual
MBUS/SerialTL/BringupSoC/FASED peers and their finer relative clock calendar;
no observed latency `30` is attached directly to a TileLink request.

`fabric_engine.*` adds accepted physical transactions whose end is unknown
until the matching response. They cannot be canceled or completed at their
acceptance tick. A separate `record_physical_edge` API records actual
same-edge work as an explicit completed point, without invented occupancy.
Both carry a nonempty source string and explicit PC knownness; an unknown
owner stays PC 0/unattributed. Private pending load storage is bounded by
physical destinations; retired COM history is not scanned or retained there.

The real load gate has twelve independent retirements after an uncached
load's WB and before its data response. The identical ELF passes on the
independent saved whole-CPU RTL observer, as do the width, fast-dependency
and WAW directed ELFs. These are functional/order checks, not cycle fitting.
The 32 prior functional guest stdouts and 24 legacy, IRQ and Zephyr graph
checks remain separate regression evidence with the new flags absent.

Full internal four-state knownness, all-three-hart source memory coherence,
new-path Zephyr/IRQ qualification, complete component utilization, sustained
speed, deployed-image association, end-to-end timing and held-out ±2% are
all unfinished. The existing primary functional/Zephyr package is unchanged.
