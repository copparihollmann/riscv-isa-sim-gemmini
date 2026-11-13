# Composed source memory-system SDK

`System` owns the frozen Rocket-cache/CDC/full-NoC/L2 fabric and the actual MBUS/SerialTL/Bringup conversion path. All four post-cork A/D connections are internal. Its external memory boundary is **FASED AXI64/address33/ID4**. The SDK supplies no backing data, latency, maximum-request default, or host-token service.

The cache/fabric comes from saved standalone-Iris FIR, and the external path comes from archived Combined RTL. These source-bound components have qualified matching physical interfaces; whole-image/elaboration equivalence remains unproved. The composed component is experimental, with calibration and loaded-image certification false.

## Interface

Use `serial_memory_system.hpp` and `libiris_serial_memory_system.a`. The build receipt gives the required child archives **in link order**, include directories, and exact digests. Parent archives remain unchanged.

`evaluate(span<Input>)` computes a global same-edge fixed point. `sample()` returns physical outputs; `commit({rocket,uncore,bringup,serial})` commits every selected peer using held pre-edge inputs. No peer is re-evaluated between commits. There is no added handoff queue or edge. Source-relative periods are Rocket/Iris uncore2, Bringup1, Serial10; intermediate Bringup edges must be represented explicitly.

Use instance `input_fields()` / `output_fields()` and exact index lookups:

- `external_input_index("rocket_cache", "io_cpu_req_valid")` retains original fabric component names.
- `external_input_index("path", "fased_axi4_mem_0_bits_r_valid")` addresses physical external-path pins.
- Outer `manager` Aready/D inputs and `path` bank A/Dready inputs are internally joined and cannot be supplied by the caller.
- `output_index()` exposes original computed physical outputs for observation and protocol ownership tracking.

The emitted schema records all276 external inputs and1150 physical outputs with widths and indices. All required bits need known masks; width truncation, failed/stale phase use, and empty edge sets are refused. The four-limb input type is the existing `MemoryFabric::Input` contract.

Physical reset inputs remain separate, including all original fabric resets, Iris external-path uncore reset, and Bringup `reset_io`. No shared reset waveform is inferred. The Serial child defaults to `AssertionPolicy::SourceAlways`. Reference fixtures explicitly opt into `SuppressOnlyWhileBothExternalResets`; this masks diagnostic STOP/PRINTF only during that reset interval, without changing datapath, FIFOs or source clocks. Original first-edge unreset-monitor failures remain archived. All active assertions are enabled.

## FASED peer and functional data ownership

The separately bound `fased_service.hpp` timing cut advances only on Bringup/FASED target edges. Parameters must be supplied explicitly. The current component fixture uses synthetic30/30/16/16; it is not an admitted observation-based configuration.

Capture requests only at actual AXI handshakes. Preserve independent AW/W ownership and byte strobes through Wlast. Bind each accepted AR to owned data and definedness, then consume that owner when the LP selects its ID through `egressReq`. The registered releaser exposes R/B on the next target edge. Do not reread mutable backing at release time if an intervening write could alter the accepted read. Cache dirty data and physical writeback ordering also require distinct outer backing, rather than an architectural store mirror.

Full FASED functional ingress/egress, host-token stalls, backend ordering and `relaxFunctionalModel` remain external gaps. Unqualified conflicting outstanding transactions must remain refused or explicitly scoped; no model setting is inferred from the observed startup30. Narrow/masked transactions and live three-hart producers remain separate qualification gates.

## Context fix and evidence

The first public lifecycle test caught destruction leaking the caller's Verilator context. In Verilator5.052, `VerilatedContext::~VerilatedContext` selects the dying context and then clears TLS. Earlier wrappers scoped only model deletion and restored the caller before the context member was destroyed.

New host-only derivatives preserve the caller outside the **entire** constructor unwind, destructor and move assignment. They replace only wrapper objects, retaining all22 Serial and3 FASED model/runtime objects byte-for-byte. Their contexts explicitly use one host thread, matching both generated models' `threads()==1`, avoiding an unused host pool. No source RTL or target edge changes.

Tests cover the complete observed constructor allocation frontier (44 injected `bad_alloc` failures plus14 successful constructions), move/self-move/destruction, all remaining unknown inputs and joined-input refusal. Historical libraries independently reproduce constructor-unwind failures at allocation12 and the move-assignment leak. The original broad component outputs remain byte-identical after the host fix:4,780,311 FASED ledger checks and528,906 Serial transport checks.

The public API's independent Hella/Icache fixtures cover a cold cache refill through the real external path, warm load/store values, and dirty-owner Icache coherence. The1230 inclusive source-phase cold refill matches the independently wired lower-level composition; it is checked as an equality, never supplied as a delay. Corrupt backing data and return ownership controls fail. These fixtures do not claim execution of a real CPU pipeline or a whole-SoC reference.
