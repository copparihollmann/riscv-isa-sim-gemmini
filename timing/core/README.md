# Portable timing tools

`merlin-timing` provides a C++17 streaming timing engine and Python tooling with
no runtime dependencies on the compiler. ISA decoding and target policies are
supplied by separate observers. Every timing price is an explicit input.

## C++ engine

Include `merlin_timing/engine.hpp`. `Engine` consumes ephemeral `Event` views;
it retains fixed scoreboard entries, resource lanes and bounded waiting queues,
not an instruction trace. `ResourceSpec` declares capacity and waiting-request
capacity. `Demand.occupancy` reserves resource units; `Event.latency` controls
result readiness independently. The stream's issue frontier advances through
dependencies and queue backpressure, without automatically advancing to result
completion. Declare an issue resource to model issue throughput.

Tokens represent mutable storage. Reads wait for their latest writer; writes
wait for prior writers and readers. Set `hold_reads_until_ready` for asynchronous
reads whose input storage remains live through completion. Ordinary operands
are consumed at issue. `retained_reads` holds a separate operand set until
completion, allowing captured CPU registers and live memory to share an event. `reset` refuses live or unknown tokens. `barrier` drains
all modeled work without assuming a fence-instruction price. `publish` attaches
an already scheduled asynchronous result to a completed token without advancing
the issue frontier; it refuses live tokens and backdated results.

Unknown prices or dependencies produce incomplete accounting and propagate to
subsequent affected work. Reports contain a modeled makespan and descriptive
reservations/busy-unit counts; these are neither qualified hardware cycles nor
correctness evidence. Callers must supply complete resource/alias relationships.
The reservation model assumes greedy capacity admission and does not discover
hardware arbitration, speculative execution, coherence or memory consistency.

`SetAssociativeCache` classifies bounded LRU hits, misses and dirty evictions.
It assigns no hit, miss, writeback or coherence cost. The caller owns those
policies and must not assume absent observations are free. `probe` observes
residency/dirty state without filling, counting accesses or changing LRU;
`invalidate` reports whether a dirty line was removed. `clear` removes residency
without erasing the access census. Access results and hit probes expose the
bounded physical slot index (`set * ways + way`), allowing callers to attach
pending-fill dependencies without retaining every accessed address. These
mechanisms assign no coherence price.

## Experimental cache response timeline

`cache_response_timeline.hpp` is an inactive, explicitly called planner. It
separates accepted request, response beats, line visibility, replay admission,
and lookup response. It supplies no target constants, cache hit classification,
retirement estimate, or default backpressure assumption. Every response beat
requires a caller-supplied receiver/arbiter admission bound; missing replay state
keeps the lookup result unknown even when the response is complete. A flush
inside the refill prevents publication of the line.

The memory observer can explicitly select the provisional
`memory.fetch_refill_timeline` schema `merlin.provisional_fetch_refill.v1` with
assumptions `demand_only_immediate_replay_no_backpressure`. It replaces the scalar
price only for private first-cache misses with a modeled second-cache hit. It
preserves slot dependencies, reports response/visibility/lookup milestones and
counts legacy miss/immutable paths separately. It does not model speculative
fetches or shared response contention. The profile supplies `beat_bytes`,
`first_response_cycles`, `beat_interval_cycles`, `line_visible_after_last_cycles`,
`lookup_response_cycles`, and `request_accept_cycles`; none has an implicit
default. The response component replaces both old cache prices, avoiding double
charging. Unsupported geometry or incompatible byte service refuses selection. Observed response service parameters are provisional
calibration inputs, not an independent validation result. Neither speculative
fetches nor frontend replay can be reconstructed from retired PCs alone.

## Build and export

```sh
cmake -S . -B /path/to/build -DBUILD_TESTING=ON
cmake --build /path/to/build
ctest --test-dir /path/to/build --output-on-failure
```

`merlin_timing.export.export_cpp_core(destination)` exports only the canonical
header, native test, CMake file, README and license into a fresh directory, with
per-file SHA-256 identities. The same source payload is included in the wheel,
so export works without a compiler checkout. `verify_cpp_core` detects changed,
missing or additional files. Build outside the exported source directory.

## Target provider bundles

`merlin_timing.provider_bundle.export_bundle(payloads, destination,
entrypoint="observer.cpp")` packages a caller-selected map of filenames to source
bytes. The manifest declares the translation unit and complete source roster;
the builder contains no accelerator name, instruction semantics or hardware
parameters. Exports are limited to one MiB and 64 files.

The export includes the canonical `build_provider.py`, which runs independently
of this package using Python's standard library:

```sh
python3 /path/to/provider-source/build_provider.py --verify-only
python3 /path/to/provider-source/build_provider.py \
  --spike-root /path/to/annotated-spike \
  --output-library /path/to/libtiming_provider.so
```

Compilation uses one C++17 compiler process, pins the source bundle and generic
runtime headers before and after building, and publishes a new library inode.
Target simulator sources and facts belong in the simulator repository's examples,
independently of the generated OOT compiler. The shared builder supplies no
kernel, schedule, timing prices or calibration evidence. Candidate grants expose
reviewed runtime endpoints through the broker; simulator sources remain operator
build inputs.
# Asynchronous reservation APIs

The additive `Engine::submit_detached` API schedules a controller effect without
advancing CPU admission to its future completion. `advance_issue` separately
applies explicit frontend backpressure. Original `submit` and `barrier` behavior
is unchanged. Adapters must establish actual dependency and completion effects;
these APIs supply no physical timing qualification.

`ReservationWindow` tracks bounded entries by generation and keeps each owned
until its explicit release stage. Allocation can wait for a known release;
unresolved releases cannot become zero cost or free entries. A selected adapter
may exclude an exact outstanding ticket from its drain predicate only when its
original hardware/software completion contract allows that exception. Waiting
resource queues and completion-owned reservations are different abstractions.

The portable source export now emits version 2, including the reservation header
and its executable checks. Version 1 exports retain their exact original roster
and remain verifiable without being rewritten. The simulator's source package
must retain the manifest of its exact canonical export; copied vendor bytes are
a versioned source snapshot, never another maintained implementation.

## Optional modeled-event diagnostics

`Engine::trace_sink` installs a synchronous opt-in observer of actual scheduling
constraints and results. Submit records include the prior token writer/readers,
resource lanes and queued starts, earliest/frontier bounds and issue/start/ready.
Detached issue restoration and explicit advance/publish/reset/barrier operations
are recorded separately. No sink means no trace capture or trace allocations.
Callbacks must not mutate the engine; callback errors fail the diagnostic caller.
These are modeled dependencies, not measured hardware stalls. A selected-window
consumer must retain unknown, tied and outside-window predecessors explicitly.

The Spike observer's `--timing-event-trace=<jsonl>` requires an exact counter-PC
scope, records that selected window only, and caps collection at 32,768 events
and 16 MiB. The final row identifies truncation and normal execution completion.
The normal report remains authoritative; tracing changes neither prices nor
scheduling. Diagnostic runtime/library identities must be pinned separately.

## Inactive arrival-port prototype

`arrival_ports.hpp` provides `plan_arrival_ports` for a bounded, closed set of
ready/valid FIFO arrivals. It keeps future idle gaps available, preserves explicit
dependencies, arbitrates by supplied strict priorities, and propagates occupied
port intervals and FIFO head backpressure. An item occupies one acceptance cycle;
this describes a row port, not a DMA latency, response queue or complete device.
Inputs are limited to 4,096 rows, 16,384 dependency edges, 128 ports, 256 sources
and 4,096 occupied intervals. Missing arrivals, unknown predecessors, dependency
cycles and ambiguous priorities refuse a complete plan. Partial diagnostic rows
must never be treated as a complete schedule.

This prototype is not selected by an existing provider or canonical standalone
export. Upstream response arrival/credit production, exact alias dependency
binding and downstream completion publication remain required before integration.
In particular, do not divide aggregate memory latency by rows or replace a
request-wide hold with an unbound late write. Explicitly supplied busy intervals
must include all other port users, including reads. The planner does not infer
hardware arbitration or cache behavior.

Focused standalone check:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Werror -I timing/core/include \
  timing/core/tests/test_arrival_ports.cpp -o /your/task/.tmp/test_arrival_ports
/your/task/.tmp/test_arrival_ports
```
