# Gemmini timing reference audit

The requested libgemmini commit `20961076afc2b83655e534d9b1e9fa3b81c83eeb`
was available in the local Git object history even though Ethan's checked-out
libgemmini is `ea8f7ed7afd68e001fb06ddccad9a023c990961d`. An independent clone
at `third_party/libgemmini` is checked out at the requested commit. No source
tree owned by Ethan was modified. The other requested repository,
`copparihollmann/riscv-isa-sim-gemmini` branch
`feat/megaphase-feedback-integration`, has not been fetched or verified because
network/DNS access is unavailable. These are separate references.

The requested libgemmini revision already contains a substantial event-based
performance model; it is more useful than merely a functional RoCC example:

- [Event queue, lines 16–24](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/perf/sim/event_queue.h#L16-L24)
  distinguishes evaluate and commit phases. Registered state updates cannot
  affect decisions in the same cycle. Events have stable order within a phase.
  This is a useful pattern for Iris register-file arbitration and simultaneous
  multi-hart requests; arbitration policy must still come from Iris RTL.
- [Reservation station, lines 14–40](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/perf/control/reservation_station.cc#L14-L40)
  creates dependency edges for overlapping spans with a write, then wakes
  dependent queues when operations complete. Iris needs analogous scalar,
  vector-register-group, tile and shared-memory dependencies using Iris-specific
  hazards and queue behavior.
- [Shared port, lines 8–27](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/perf/sim/port.cc#L8-L27)
  arbitrates eligible resource requests by priority and age. Resource service
  is scheduled in simulated time rather than reserving far-future bandwidth
  in instruction submission order. This helps avoid a common multicore modeling
  error where the first host hart to run claims an entire future memory stream.
- [Instruction serialization, lines 39–51](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/gemmini_perf.cc#L39-L51)
  documents Spike's batched `minstret` updates and serializes intercepted
  operations before reading them. Any Iris hook must respect Spike retirement
  bookkeeping; the instruction count itself is not the modeled clock.
- [Memory-tracer registration, lines 181–188](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/gemmini_perf.cc#L181-L188)
  attaches before guest execution, avoiding loss of CPU stores before the first
  accelerator command. Iris tracing likewise must start at reset, including
  Zephyr initialization and synchronization traffic.

Several parts cannot be adopted as Iris's implementation contract:

- [Global model/tracer state](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/gemmini_perf.cc#L28-L64)
  includes a single `g_model`, `g_trace_proc` and RoCC-handler state. Iris
  requires explicit per-hart state plus a shared SoC event scheduler, so
  registering another extension must not overwrite another hart's state.
- [Counter interception, lines 191–201](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/gemmini_perf.cc#L191-L201)
  hooks one `csrrs rd, cycle, x0` encoding and fence. That does not implement
  Iris's full counter/CSR aliases, `mtime`, timer interrupts, counter writes,
  atomics, or Zephyr SMP execution. Those belong in the integrated Spike fork.
- [Performance-only mode](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/gemmini_perf.cc#L142-L176)
  deliberately skips data operations. Iris's normal timing mode must retain
  bit-exact functional effects so data-dependent control flow stays valid.
- [Dummy accelerator counters](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/gemmini.cc#L3067-L3075)
  use random increments. They must not become utilization or timing evidence.
- [Parameter defaults](https://github.com/ucb-bar/libgemmini/blob/20961076afc2b83655e534d9b1e9fa3b81c83eeb/perf/params/config.h#L34-L41)
  include both measured and assumed values for a different design. Reuse the
  provenance discipline, not Gemmini latency/bandwidth values.

The clone is an inspected reference, not a built Iris dependency or accuracy
oracle. Its build also references sibling `gemmini-rocc-tests/include/vpu_ref.h`
(`gemmini.cc:12`), so an isolated `make` is not certified here.

## FireSim source preservation

`third_party/firesim` is independently cloned at
`69b17767e0b227e31ea341c50899e49f02d6f5ea`. Its source is clean. The observed
external workspace's tracked changes are preserved separately in
`firesim-observed-dirty.patch`, with the patch digest and untracked file digests
in `source-clones.json`. This captures the current workspace, and cannot prove
that the same dirty contents produced the existing image. The image's metadata
states only the revision plus `-dirty`; build-time full input provenance remains
unknown.
