# Archived FASED target timing component

This component executes the **exact archived image's `LatencyPipe` RTL**, including its admission counters, AW/W pairing, due queues, registered AXI response releaser, and periodic counters. It does not turn a measured DRAM setting into a guessed whole-SoC delay.

The initial source is archived `FireSim-generated.sv`, SHA256 `c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64`. The extraction receipt binds the bitstream/build inventory and full current source pins, while leaving loaded-image/source association false. Current Scala and driver snapshots are explanatory source context; their association with the archived image is not assumed.

## Build and check

Use new output directories for each invocation:

```sh
python3 timing/fased_service_extract.py --output build/fased-service-source-new
python3 timing/fased_service_build.py --source build/fased-service-source-new --output build/fased-service-native-new
python3 timing/fased_service_check.py --build build/fased-service-native-new --output build/fased-service-check-new
python3 timing/fased_service_clock_check.py --source build/fased-service-source-new --output build/fased-service-clock-new
```

The SDK is `sdk/fased_service.hpp` and `sdk/libiris_fased_service.a`. Link with C++20, pthread and atomic. The library owns its Verilator runtime; avoid duplicate runtime objects when linking several source components. Host methods select their own context and restore the caller's context.

`Model(Parameters, seed, source_arguments)` requires explicit read/write latencies and read/write maximum requests. It supplies **no default timing settings**. The qualified envelope is latency ≥1, maximum requests 1–16, AXI ID4, and bursts of 1–8 beats. WRAP and multibeat FIXED bursts are refused. This archived specialization has a 64-bit response datapath and 33-bit address at the full bridge boundary; the timing cut itself transports transaction metadata, not addresses or write data.

Look up physical input/output names through `input_fields()` / `output_fields()`. Every supplied input has a value and known-bit mask. Unknown required inputs, width truncation, operation before a committed reset, stale sample/commit, and duplicate commit are refused. Repeated `evaluate()` settles the same pre-edge state. `sample()` reads that state; `commit()` advances exactly one supplied **FASED model-target edge**. Reset must be driven by the caller. Invalid payloads and pre-committed-reset values are raw physical observations, not defined architectural data.

The external actor must supply the functional egress read data/last/ID and write response ID. An egress request is emitted on the preceding target edge before R/B becomes valid. Do not fabricate a memory backing implementation by ignoring that ownership and the full bridge's functional ordering. This SDK has no automatic DRAM service, SerialTL service, address translation, or CPU-clock conversion.

## What the checks establish

The independent transaction ledger uses accepted transactions and FIFO ownership, without reading internal state, replaying readiness, or injecting observed delays. It covers read/write bursts, AW-first/W-first pairing, response backpressure, IDs and ordering, capacity limits, request/beat counters, histogram accounting, reset with pending transactions, and foreign model interleaving. The directed 16-request witness returns 128 read beats with one 64-bit beat per target edge and no inserted inter-burst bubble. A wrong-latency oracle must fail.

The separate archived `RationalClockTokenGenerator` is checked against an absolute event calendar under host stalls and reset, plus a wrong-period negative control. Its source-relative periods are `[2, 1, 10]`:

| Clock stream | Archived consumers |
|---|---|
| 0 / period 2 | Iris uncore and Rocket tile2 |
| 1 / period 1 | BringupSoC uncore and FASED ep_2 AXI token qualification |
| 2 / period 10 | Both SerialTL endpoints and harness RAM |

This relationship is source/build evidence. No loaded-image clock attestation or conversion into complete CPU request latency is claimed.

## Important limits

The observed startup read/write latency values of 30 were read before driver initialization. The candidate profile preserves those observations, while `readMaxReqs`, `writeMaxReqs`, `relaxFunctionalModel`, and post-initialization settings remain unknown. The exact archived source resets those limits to 16/16 and relaxation to zero; that is distinct source evidence and is not an admitted hardware default. Driver `+mm_...` arguments can override settings, and periodic stats exclude writable registers.

Histogram bins are **not exhaustive**. Actual source bins 0–3 count occupancy 0, 1–2, 3–4, 5–8. Bin 4 is constant zero because the source never appends its advertised catch-all threshold. Occupancy >8 is uncounted. Bin0 still specifically counts pending==0. Do not sum the bins to infer all cycles or a busy fraction.

The four post-L2-cork TL ports of the memory fabric are separated from this AXI boundary by actual MBUS/SerialTL/BringupSoC logic and width/clock adapters. Those actors must be connected from source. Full FASED also includes functional ingress/egress, host-memory service and backpressure, and a BUFGCE-controlled token clock; these remain outside the initial qualified cut. The bridge can withhold target progress until functional response payloads exist. A 30-edge setting must never be attached directly to a post-L2 TL request.

Full internal four-state knownness, arbitrary unreset RNG-order invariance, loaded-image equivalence, whole-SoC timing, calibration admission, and ±2% accuracy remain unqualified. The default full external-memory service stays unavailable.
