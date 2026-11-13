The fast Shuttle frontend is a plain C++ implementation of the saved Iris
frontend control. It computes F0/F1/F2, partial instructions, the seven-slot
fetch queue, the 32-entry BTB, 512-entry BHT, six-entry return stack, and the
instruction cache's actual tag/data RAM and eight-beat refill protocol. It uses
instruction encodings and dynamic state; it contains no PC-to-cycle table.

Its physical API is in `fast_source_frontend.hpp`. `evaluate(inputs)` may run
repeatedly before `commit()` advances one source edge. Inputs are external
instruction-memory A-ready/D-data, CPU dequeue readiness, and actual CPU
redirect/BTB/BHT/RAS repair ports. Internal queue occupancy, predictions, cache
hits and replay state are computed inside the model. No idle edges are skipped.
The standalone library is under `build/fast-source-frontend-sdk-v1/sdk` and needs
no RTL runtime.

The native integration applies this frontend to Shuttle harts 0 and 1. Hart 2
retains an explicitly reported lightweight frontend until the separate Rocket
packet model is qualified. The numerical executor remains Spike. Finite
non-memory integer RVV, VME and opt-in FADD operations retain staged result and
knownness publication; scalar work can overlap their modeled backend actors.
The shared L2/data service is an empirical approximation. Source Icache misses
use its shared-L2 read path without allocating duplicate private L1I tags.

The current frozen candidate is
`build/fast-source-frontend-frozen-901cecd9`:

```
native 901cecd9123badd3530156a9a342d26787806bfc8b86df6c74a8cb6e0bac7075
UART  19698e53816996b5fad4b2e359e12c3fac5347941d6918d72e11335867ebf246
```

Use the paired UART and an explicit fixture containing:

```
shuttle_frontend source-C++-M-mode 1 16
icache_service empirical-shared-L2 1 1 explicit-service-provenance
```

The two `1` values specify the minimum first-beat and following-beat service in
the explicit fixture; they are not measured NoC or DRAM latencies. Positive
effective service coefficients may add first-beat cost. The candidate fixtures
under `build/fast-source-frontend-fixtures-901c-v1` distinguish an unfitted
baseline from a positive-cost mechanics test. Their copied coefficients do not
establish calibrated accuracy on this new engine.

Require these actual summary fields before accepting a run as source-frontend
enabled:

```
fast_source_frontend_enabled: true
source_frontend.implementation: source-derived-plain-C++-ShuttleFrontend
source_frontend.required_unreset_payload_policy: strict-refuse-required-RAS-or-RAM
```

The scope is M-mode with VM disabled. Required unreset RAS or RAM payload stays
unknown and causes a capability refusal; constructors do not manufacture
initialized architectural bytes. The unchanged three-hart boot and K1 workload
ran successfully under this policy. The configured execute-permission window
at `0x70080000..0x700fffff` comprises four aliases of the requesting Shuttle's
own 128-KiB TCM. The external memory responder canonicalizes that address; it
does not allocate extra RAM. See `hardware/memory-paths.md` and
`board/addressing.hpp`.

The qualified source component has 65 positive continuous comparisons against
the independently compiled saved RTL, across three reset seeds, including all
38 original alignment/branch-history cases, return-stack wrap, variable refill
gaps, backpressure and permission boundaries. Five copied-source corruptions
are rejected. The separate RVC expansion proof covers 262,144 inputs. Evidence:

- `build/fast-source-frontend-component-v1/report.json`.
- `build/fast-frontend-primitives-v2/report.json`.
- `build/fast-source-frontend-fadd-proof-901c-v1/report.json`: 18 actual native
  numerical, flag/knownness, pending-interrupt, dependency and refusal controls
  with the source frontend explicitly enabled.
- `build/fast-source-frontend-CPU-development-3e5dc-v1/report.json`: all 2,304
  CPU-layout main rows and 4,608 actual CSR/ELF joins. This is an intentional
  post-ROI debugger stop, not a normal guest exit. Larger warm Shuttle loops
  have zero median and p90 absolute error in this development corpus; cold
  cases and the Rocket fallback remain inaccurate. The complete signed table
  is retained. These are not global held-out results.

The first native composition exposed an empirical coherence-fallback bug:
two fetched parcels had already left the queue when an accepted load annulled
its younger integer instruction. The old memory fallback did not redirect the
new source frontend. Its exact failed pair, ELF, accepted instruction rows and
matching memory response remain archived. The successor requests a frontend
redirect only for that actual fallback, refetching the annulled instruction
while preserving the accepted load transaction. It never assigns an
architectural PC to repair a mismatch. The subsequent mixed Zephyr execution
passed all nine independent numerical regions.

`build/fast-source-frontend-speed-v1/report.json` measures about 3.5 million
in-process component edges per second on its declared active fetch/refill
fixture. That is neither SoC MIPS nor end-to-end workload throughput. Source
models, empirical service costs and accepted-intent counters retain their
separate meanings. This component and candidate do not establish full SoC,
Ethan-image, four-state power-on, Zephyr-path or +/-2% timing certification.
