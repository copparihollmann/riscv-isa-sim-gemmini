# Complete source-generated node5 router component

`FullNode5Router` runs the complete configured `Router_5` subtree from saved
standalone IrisConfig RTL. All four input machines, both network outputs, the
local output, route computation, VC allocation, switch allocation, FIFO storage,
credit counters and reservations evolve inside the component. No fitted delay,
peer eligibility, waiting bit, queue head, grant, free-egress observation or
ongoing state injection enters its API.

This is one causal timing component for the planned Spike functional plus NoC
timing model. It is not yet connected to the shared engine. Full NoC, cache/CDC/
NIF integration, SoC speed, +/-2% whole-workload timing and deployed-image
certification remain unclaimed.

## Build and use

```
python3 timing/noc_full_router_build.py --output build/my-node5
python3 timing/noc_full_router_bench_build.py --model build/my-node5 --output build/my-node5-sdk
```

The SDK contains `noc_full_router.hpp` and `libiris_node5.a`. Clients need C++20,
`-pthread -latomic`, and the compiler/runtime recorded in `build.json`; public
headers have no Verilator dependency. The benchmark links this actual SDK, not
an alternative component. The selected build uses Verilator 5.052, assertions,
explicit randomized two-state initialization, `OPT_FAST=-O3 OPT_SLOW=-O3`, and no
`--public-flat-rw`. Original debug/public-flat and earlier experiments remain in
separate historical build directories.

Construct with an explicit random seed. Construction does not assert reset.
Supply every uncore rising edge through `step(inputs)`. It evaluates old-state
combinational outputs, returns those outputs, and advances the entire router
through that edge. The saved harness clocks this domain at 500 MHz; the API counts
edges and does not synthesize a host frequency or a guessed latency.

Inputs, all physical router ports:

| API field | Exact connection |
| --- | --- |
| `from_network[0/1]` | Flit from node 4/node 6, including73-bit payload, head/tail, flow and VC |
| `from_local[0/1]` | NIF 3 A/C ingress, global ingress IDs 6/7, with global egress ID |
| `downstream[0/1]` | Six-bit credit-return and VC-free event masks from node 4/node 6 |
| `local_ready` | NIF 3 D consumer readiness |
| `reset` | Actual router reset |

Outputs include both network flits, both local-ingress ready signals, both
upstream credit/free masks, the local D flit, and all eight exposed VA/SA stall
debug fields. Ports 2/3 debug counters are wired to zero by this RTL; the API
preserves that source behavior. Each network input has six 5-entry FIFOs. The
local ingress stages have source-generated depth 2 route buffer, depth 2 route
queue, depth 2 VA buffer and depth 1 VA response queue. Local egress has depth 2.
Network output units maintain downstream credits and VC reservations and pass
the granted switch flit; an extra network-output queue is not fabricated.

The exact saved decoder annotations define 48, 30, 9 and 4 legal input routing rows.
The decoder's unlisted default is don't-care, so valid flows outside those
minterms are refused. Physical field widths and global A/C destination IDs are
also checked. The source tables and endpoint map are included verbatim; changing
the design requires a new source identity and new validation.

## Actual-reset and snapshot entry modes

Qualification starts at whole-SoC TB 3 under actual reset and replays every
subsequent 500 MHz edge. It imports no internal snapshot. Inactive flit payloads/
metadata and reset outputs are not claimed defined. Whole-SoC and standalone
router initialization are separately randomized; their checked defined outputs
match after physical reset. Additional seed 17 replays are checked as a bounded
reset-independence control, not general four-state definedness certification.

An optional `save(path)` / `restore(path)` serializes the generated native state
after an edge. A source/tool/API identity is checked before model-state
deserialization. Snapshots are scoped to this exact frozen generated native
build; they do not import whole-RTL internal state and are not a cross-version
format. The tested continuation saves after 45,000 actual edges, restores in a
new process with constructor seed 42 and reproduces the remaining 19,999 rows
byte for byte. A changed identity is rejected. Malformed Verilator serialization
can terminate the simulator; these snapshots are trusted run artifacts.

## Independent validation and speed

`noc_full_router_observer_build.py` links a new read-only observer to the cached
whole-SoC executable/model archive. It changes no RTL. A/C packing is reconstructed
from the actual TL adapter queue/bypass state. Network tail/payload ports that
are not public in the cached executable are sampled from the actual just-accepted
destination FIFO write, checking enqueue, VC and old write address. Credit/free
events come from physical destination dequeue/tail logic. These observer reads
never drive DUT inputs. The exact uncore reset binding is `!sync_0`, verified
against the cached generated sequential condition, rather than an inferred
reset synchronizer stage.

Four independent whole-SoC captures cover 233,875 edges and 4,180,598 defined
physical signal comparisons:

| Guest | Edges | Whole-SoC outcome |
| --- | ---: | --- |
| Original 9 vector-memory sequence | 64,999 | Bounded incomplete at TB 130001, same old architectural/NoC/VA transcripts |
|8-operation control | 60,242 | All 3 done; hart 2 checks 64 |
|9-operation fenced control | 62,562 | All 3 done; hart 2 checks 72 |
| New peer/local/nonlocal and dirty-eviction guest | 46,072 | All 3 done; hart 2 checks 72 |

The new guest drives both network and both local ingress machines, including
node 0 TCM and node 1 scratchpad returns through input 1 and dirty cache C traffic.
Finite traces do not exhaust every legal routing row/state. Successful control
signatures are independently parsed from coherent TSI reads. Original 9's3,929
memory,100 NoC,15,500 VA and15,500 VA2 lines are byte-equal to the preserved
original diagnostic. The independently handwritten local component also
replays unchanged and matches 52,806 common edges/237,123 physical checks.
Seven malformed/undeclared input cases and five output-field corruptions are
rejected. Source identity, raw captures, binaries, runtime/ELF, compile commands,
annotations, routing tables, source citations and per-run digests are frozen.

The direct SDK benchmark times `step()` plus output-vector stores, with parsing,
digest computation and all text I/O outside the timer. Seven full-reset repeats
per capture have identical defined-output digests matching independently parsed
whole-SoC outputs. Observed medians are approximately 1.13–1.18 million router
edges/second (about 0.85–0.89 microseconds per complete router edge) on this host.
This is component throughput, not simulated MIPS. The initial public-flat/debug
variant measured 246,038 edges/s; O3 and port-only changes are combined, so their
individual effects are not separated. Text-driver end-to-end cost remains
about four times the direct loop cost. No idle skipping is implemented.

The ground truth here is the exact saved standalone FIR
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`,
lowered with native FIRRTL memories and a two-state Verilator harness. The
read-only preload adapter/compact CRT changes loading/startup timing. Association
with the current Chipyard source checkout or Ethan's deployed image is not
attested by these captures. The finite starvation behavior is evidence about
this saved reference, not a claim of infinite deadlock or a deployed FPGA fault.
