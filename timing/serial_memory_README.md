# Archived MBUS / SerialTL / BringupSoC component

This cut joins the actual archived conversion path between Iris's four post-L2-cork ports and the FASED AXI boundary. It retains Iris `MemoryBus`, the original SerialTL serializers/PHYs/CDC queues and credit logic, the complete original Iris pad network, and full BringupSoC `ChipTop_1` including TL-to-AXI. No queue readiness, packet state or service delay is replayed from observations.

The 113-module source extraction comes from archived `FireSim-generated.sv` SHA256 `c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64`. Twenty TL-field connections are checked against the original `DigitalTop` wire assignments; all seven serialized data/ready/clock connections are checked against `FireSim`. The Iris pad wrapper preserves every original instance, assignment and bit concatenation after exposing its `DigitalTop` boundary. The external `plusarg_reader` used by diagnostic TLMonitors is bound to the saved-FIR inline source, which differs from current pinned Rocket source only by the final newline. This distinction remains in provenance.

## SDK and phase contract

```sh
python3 timing/serial_memory_extract.py --output build/serial-memory-source-new
python3 timing/serial_memory_build.py --source build/serial-memory-source-new --output build/serial-memory-native-new
python3 timing/serial_memory_check.py --build build/serial-memory-native-new --output build/serial-memory-check-new
```

Link `sdk/libiris_serial_memory.a` with `sdk/serial_memory.hpp`, C++20, pthread and atomic. When linking other Verilator component archives, use one compatible runtime, preserving exact SDK identities.

`evaluate()` settles physical inputs with all three supplied clocks low. `sample()` reads the current outputs. `commit({iris, bringup, serial})` raises all selected clocks together from the same pre-edge inputs and then lowers them; settling does not add an edge. Source-relative clock periods are 2/1/10. Bringup has an intermediate edge between adjacent Iris edges; consumers must represent it explicitly. Inputs expose the actual Iris uncore reset and original Bringup `reset_io` separately. Original reset synchronizers and CDC behavior remain inside the model. A reset edge must be supplied on every domain before active operation is admitted.

Look up names and widths through `input_fields()` / `output_fields()`. The four TL bank interfaces are `iris_mbus_auto_bus_xing_in_{0..3}_*`, source2/address33/data64. Addresses and source IDs pass directly to the original circuitry. Additional physical clients remain exported; the SDK does not silently tie them off. The output AXI interface is `fased_axi4_mem_0_bits_*`, data64/address33/ID4. External service must preserve each accepted request, data beat, mask, response and ID ownership.

Required input bits must be known, and width truncation, missing-domain reset, stale sample/commit and empty edge sets are refused. Each host method selects its owned Verilator context and restores the caller. Arbitrary unreset-state/RNG-order invariance is not established.

## Reset diagnostics are explicit

The SDK default `AssertionPolicy::SourceAlways` retains all original diagnostics. In the seeded standalone cut, a TLMonitor can see an unreset downstream decode as AcquirePerm on the first reset edge, before the original reset synchronizers take effect. That strict failure is preserved as a negative control; it is not a diagnosed FPGA fault or an invented zero reset value.

The positive qualification fixture explicitly chooses `SuppressOnlyWhileBothExternalResets`. Only the existing `STOP_COND` / `PRINTF_COND` diagnostic guards and Verilator assertion visibility are disabled while **both** physical external resets are asserted. Datapath, FIFOs, credits, reset circuitry and clock edges remain unchanged. All source diagnostics are active as soon as either reset is released. A malformed active opcode must still terminate. Initial raw fields are not qualified protocol observations; the fixture supplies inactive FASED metadata during this reset interval. This policy does not certify whole-system startup or FPGA initialization.

## Current qualification scope

The independent source-path fixture issues concurrent requests on all four bank ports: four then sixteen 64-byte reads, sixteen multibeat writes, and sixteen readbacks. It checks every returned byte/address/source/size, ownership and request/beat conservation, under client response backpressure. Seeds 1 and 17 have identical committed phase counts. Each seed produces AR36/AW16/R288/W128. Reported `source_virtual_ticks` count committed phases including the final observed edge; they are not program counter deltas or CPU cycles.

The fixture couples this path to the frozen source FASED `LatencyPipe` with **explicit synthetic** settings 30/30/16/16 and an independent AXI value backing actor. These values are test inputs, not admitted hardware defaults. The actual source/clock conversion is executed rather than replaced by a 30-cycle delay. Unknown-input and phase guards, corrupted functional data, active malformed traffic, and the strict initial-reset monitor witness are separate checks.

Full FASED functional ingress/egress and host-token behavior, unmeasured runtime settings, complete image/source association, whole-SoC reference replay, real CPU producers, all narrow/masked transaction shapes and three-hart workload contention remain outside this initial qualification. All loaded-image, whole-system timing, calibration and ±2% certification flags remain false. No FPGA was contacted by these tools.
