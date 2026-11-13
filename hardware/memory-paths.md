# Iris memory paths and timing inputs

The saved `IrisFiresimNOCflushCombinedConfig` elaboration has **three distinct
requesters per hart**: instruction fetch, scalar data, and Saturn vector memory.
[memory-paths.json](memory-paths.json) records all 36 requester/region routes,
bank selection, clock connections, source hashes and line citations. The audit
does not establish the deployed bitstream's build identity or supply calibrated
latencies. Every unmeasured timing field remains `null`.

| Component | Source/elaboration result | What remains to measure |
| --- | --- | --- |
| Harts 0/1 | VLEN 256, DLEN/MLEN 128; vector TL requests up to 16 B | Scalar/vector issue, request expansion, overlap and queue delays |
| Hart 2 | VLEN 256, DLEN/MLEN 256; vector TL requests up to 32 B | Shared scalar-FPU throughput and vector-memory overlap |
| Scalar L1 | Shuttle I/D 8 KiB each; Rocket I/D 16 KiB each | Load-to-use, miss/refill, replacement and coherence costs |
| Vector memory | Every hart uses an independent TileLink path, bypassing scalar L1D | L2 hits, NoC contention, arbitration and transaction overhead |
| Per-Shuttle TCM | 128 KiB; two 64-KiB banks; bit 6 selects bank; 32-B bank port | Local versus remote access, bank conflicts and AMO service |
| System scratchpad | 128 KiB; two banks; bit 6 selects bank; 8-B bank ports; no atomics | Dependent loads, vector traffic, saturation and bank contention |
| L2 | 512 KiB, four banks, four ways; bank bits 7:6, set bits 16:8, 64-B blocks | Hit/refill timing, bank/subbank conflicts and coherence interference |
| Main NoC/uncore links | Identified SBUS tile links, L2 ports and scratchpad ports carry 64-bit TL data | Packetization, arbitration, buffering and router occupancy |
| DRAM path | Iris L2/MBUS → 16-bit serial-TL port 1 → bringup port 0 → AXI4/FASED | Selected runtime settings, useful payload bandwidth and complete round trip |

The `useL1DCache` name in Rocket's Saturn configuration is misleading for this
revision. In `saturn.rocket.Integration`, both `load_use_tl_reg` and
`store_use_tl_reg` are initialized true and never assigned afterward. Both force
the independent `TLSplitInterface` path. The vector memory interface aligns each
Get/Put request to its full MLEN width; a 128/256-bit request can then serialize
through the 64-bit uncore. Data traffic cannot be modeled by giving all harts
the same scalar-cache hit rate or treating DLEN as system-bus bandwidth.

## TCM addressing includes hart-local aliases

The external memory map alone is incomplete for the Shuttle requesters. Each
Shuttle has a direct path to its own canonical TCM, while another hart's
canonical TCM goes through the system NoC. Address offsetting and region
replication also expose **0x70080000–0x700fffff** on harts 0/1: four mirrors of
that requesting hart's own 128-KiB TCM.

The storage identity is:

```text
canonical = 0x70000000 + hart * 0x20000 + (address & 0x1ffff)
```

These aliases must share RAM and supported AMO effects with the canonical TCM;
they are not extra capacity. They retain read/write/execute and AMO permissions.
Both canonical TCM and these aliases reject **LR/SC**: both core TLBs separately
require cacheability for LR/SC, and these TCMs do not support AcquireB. Scratchpad
also rejects LR/SC and additionally lacks AMO support. Hart 2 and external SBUS
requesters do not expose this private
window. Preserve the original guest address for architectural PMP/trap handling
while routing the access to its correct backing storage and timing resource.
The audit freezes both the Scala remappers and the elaborated private address
masks `AddressSet(0x70080000,0x7ffbf)` / bank 1 `+0x40`.

Memory protection is also heterogeneous: the Shuttle cores have no PMP entries,
while Rocket exposes eight with four-byte granularity. A single generic Spike
PMP configuration cannot describe all three cores.

## Actual local clock connections

The local FIR and clock-bridge annotation resolve the clock chain more precisely
than the DTS's zero-valued CPU clock fields. All three Iris harts, Iris uncore,
TCMs, scratchpad and L2 use the **500-MHz** output. Rocket still has instantiated
asynchronous crossing logic, although its separate input is tied to that same
clock by this harness. The bringup system's DRAM/AXI bus uses **1 GHz**, and the
interchip serial PHY uses **100 MHz**. The timer timebase is **500 kHz**.

The Shuttle async configuration fragment targets `InCluster(0)` while these
tiles elaborate in `InSubsystem`; their actual master/slave crossings are
synchronous TL buffers. Trace-DMA attachment crossings are separate and must not
be mistaken for the ordinary core memory path. None of these target clocks is
the FPGA's host emulation rate, and none is yet bound to a verified deployed
image build.

## Reference memory endpoint

`BaseCorigineMimicTurboGTConfig` selects `LatencyPipeConfig` through
`WithDefaultMemModel`. This is a latency/bandwidth pipe, not a DDR3 bank scheduler.
Its source runtime defaults are **readLatency = writeLatency = 30** endpoint
clock cycles. These are neither measured CPU memory latencies nor proven current
remote register values. Request/response serialization, NoC, caches, crossings,
queues and arbitration lie outside those endpoint defaults.

The saved successful November 4 and failed November 5 launch scripts contain no
`+mm_*` overrides or runtime-conf selection. The driver leaves hardware defaults
intact when no memory settings are supplied. The generated memory-model registers
are addressable for future verification; register offsets 0 and 4 are addresses,
not latency values. Actual deployed values/build identity still need verification.

Similarly, inclusive-cache `outerLatencyCycles=4` feeds `memCycles` resource
sizing. It does not impose four-cycle DRAM timing. TLRAM's advertised minimum of
one cycle and the two-cycle Shuttle I-cache pipeline are structural facts;
they are not complete core load-to-use measurements.

The local elaboration emits a warning that the selected decoupled serial PHY
can deadlock under heavy load. Retain failed/timeout runs and analyze saturation
before certifying multicore contention. A successful light workload does not
establish saturation behavior.

## Calibration coverage

The JSON maps exact existing v1/v2 case IDs to identifying questions. Current
coverage includes local scalar TCM, scalar scratchpad, warm/eviction-attempt
working sets, dependent loads, shared/private reads across all seven hart
subsets, atomic false sharing, hart-2 vector writes, instruction footprints, and
distributed producer/compute/consumer rotations.

Still required are explicit remote-TCM requester sweeps, local-alias tests,
same-bank/different-bank probes, scalar/vector variants for every memory level,
identified L1/L2 hits and misses, mixed read/write saturation, vector request
queue pressure, NoC-route conflicts, real serial saturation and actual Zephyr
scheduling/preemption interference. The existing cache preparation is an
eviction attempt; it does not prove all accesses are cold.

Regenerate and verify the audit with:

```sh
python3 hardware/memory_paths.py
python3 hardware/memory_paths.py --verify-live
```

Source integrity, modeled semantics, actual FPGA reference measurements and
held-out timing accuracy are separate gates. This audit passes only the first.
