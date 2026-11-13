# Saved Iris cache/controller SDK

This isolated SDK executes the actual saved `ShuttleDCache`, `DCache`, and
four-bank `InclusiveCache` RTL in process. It introduces no fixed hit/miss cost,
cache-state input, observed readiness correction, or added clock edge. It is not
connected to the published Spike timing engine yet.

The source is the immutable standalone `IrisConfig` FIR capsule with SHA256
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
Its native FIRRTL memories were regenerated with firtool 1.75.0. This is not
proof that this saved design and Ethan's loaded FireSim image have identical
build inputs or memory timing. The local source audit records those distinctions.

The extractor includes 102 unmodified RTL modules: 36 reachable from each
Shuttle cache, nine from Rocket's cache (including its specialized TLB/PMA/PMP
logic), and 60 from inclusive L2; some modules are shared between cuts. Model
instances retain their independent control, metadata, replacement, data arrays,
MSHRs, writebacks, probes, and queues. No cache array is host-initialized to zero.
A new instance requires an explicit committed reset before active operation.
The constructor seed selects arbitrary unreset simulation state; it is not a
claim about hardware reset contents or four-state definedness.

Build and run the independent checks:

```sh
python3 timing/cache_hierarchy_extract.py --output build/cache-hierarchy-source-NEW
python3 timing/cache_hierarchy_build.py --source build/cache-hierarchy-source-NEW \
    --output build/cache-hierarchy-native-NEW --jobs 8
c++ -O3 -std=c++20 -I build/cache-hierarchy-native-NEW/sdk \
    timing/cache_hierarchy_check.cpp \
    build/cache-hierarchy-native-NEW/sdk/libiris_cache_hierarchy.a \
    -pthread -latomic -o build/cache-hierarchy-native-NEW/check
build/cache-hierarchy-native-NEW/check
```

`cache_hierarchy.hpp` is the public Pimpl interface. Each `Model` exposes the
exact physical input/output schema for one component. `Bits` contains four
little-endian 64-bit limbs. Width/count errors fail closed. Call `evaluate`
repeatedly to settle same-edge peer ready/data feedback, `sample` to inspect
outputs, and `commit` exactly once for that component's rising clock edge. Neither
`evaluate` nor `sample` advances time. Commit/sample without fresh evaluation is
refused. The SDK exposes no internal cache or Verilated state accessor.

The actual boundaries differ:

- Shuttle scalar L1D has a 64-bit TL port, an external S1 physical address,
  S1/S2 kills, and a CPU request/tag/data response pipeline. A blocked refill
  stays in the actual MSHR machinery. A warm load can complete through its
  two-stage request pipeline.
- Rocket L1D has 256-bit Hella CPU data and 256-bit TL data at the cache pins.
  Its external tile master and NoC are narrower. Actual width adapters, arbiters,
  and Rocket CDCs must connect these boundaries. A cached miss can nack the CPU;
  the source CPU must retry it. `phys=true` is a passthrough/PTW-style request
  which still uses supervisor PMP checking; it is not the normal bare-M CPU
  request setting. The auxiliary Saturn TLB request and PTW interfaces are
  exposed, not replaced with automatic translations.
- Inclusive L2 exposes all four actual inner/outer bank interfaces, control
  accesses, B probes, C releases/probe data, D grants, and E acknowledgments.
  The outer pins precede the real cache cork and MBUS/serial machinery. A
  write-ownership conflict waits for the old owner's actual C response.

The default `UnresetReplayPolicy::RefuseUse` checks a concrete source-definedness
gap in Shuttle: `DCache.scala:359` consults `isWrite(replay.bits.cmd)` even when
`replay.valid` is false. The replay arbiter selects MSHR3's queue head when no
replay is valid. That 16-entry queue RAM has no reset. A CPU write can therefore
make the stall counter depend on unwritten command bits. The SDK tracks accepted
queue writes per physical slot using its own controller signals, never observed
whole-SoC state. It refuses the affected new write before committing the edge
when the selected command is undefined. A genuine enqueue defines the slot;
dequeue can expose an unwritten next slot. Reset does not pretend to clear RAM.
`ExploreConcreteReset` (driver `--explore-concrete-reset`) explicitly permits one
arbitrary reset realization and reports that unknown timing was concretized.
The independent semantic corpus opts in to that diagnostic mode; separate checks
exercise default refusal, real enqueue qualification, and refusal after head
advance. This narrowly scoped guard is not a proof that every other reset signal
is defined. GoldenGate/FPGA initialization must be established separately; no
zero-initialized implemented memory convention has been attested here.

A scalar architectural operation must first pass the real core's privilege,
translation/PMA and exception logic. Shuttle's cache takes an already translated
physical address and does not substitute for its upstream TLB. Rocket's specialized
cache contains the corresponding PMA/PMP path. CPU tags, nack/retry, S1 store data,
kill phases, individual response beats, and all source/sink IDs must be preserved.
An accepted refill or coherence transaction survives a younger CPU redirect.

The complete NoC SDK is a separate peer (`noc_network.hpp`), as are the saved
Shuttle frontend and Saturn units. This SDK does not shortcut their actual
TL buffers, source-ID transforms, width adapters, crossbars or CDC queues. All
three saved harts and Iris uncore use 500 MHz in the audited saved elaboration;
the serial link and external memory endpoint have distinct source clocks. This
API advances local edges and never infers those rates from FPGA wall time.

Independent tests supply explicit synthetic external service beats to check
semantics. Service delay is a test stimulus, never a fitted Iris timing
parameter. With no supplied D service, a cold miss does not complete. The test
oracle computes line contents from integer formulas, then checks warm hits,
stores, AMOADD, LR/SC, dirty probes, four-bank parallel fills, uncached TCM access,
PMA/PMP refusals, and ownership handoff between source-configured coherent clients.
Four arbitrary reset seeds prevent a single zero-like initialization from being
used as evidence of defined data.

The separate whole-SoC observer changes only read-only visibility of physical
cache pins. Its replay validates the mechanical cut by feeding external pins;
it never feeds a cache's own hit/ready/MSHR or metadata output back as state.
Invalid-channel payload and inactive auxiliary TLB payload are excluded by
explicit source protocol rules. The scalar replay refuses an active auxiliary
TLB request outside that declared corpus. Such boundary replay is not a complete
closed-loop memory prediction: tile adapters, NoC, L2, serial/DRAM service must
be composed before making that claim.

Remaining integration work includes exact tile/manager adaptor cuts, coherent
peer composition, instruction and vector interference, PTW/TLB state, multi-clock
serial service, and the chosen FireSim memory model's runtime parameters. Unknown
service settings stay unknown. No whole-model timing accuracy, full RTL
certification, deployed-image association, or ±2% claim is enabled by this SDK.
