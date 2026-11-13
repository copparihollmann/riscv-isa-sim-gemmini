# Counter reads and measured regions

The current primary5e6 and frozen646 pipeline prototype do not yet reproduce
the Shuttle counter-read behavior established by the independent
[CSR unit proof](../pipeline/CSR_READS.md). Native correction and whole-CPU phase
validation are in progress. Nothing here qualifies hardware timing accuracy.

Writable `mcycle`/`minstret` reads on Shuttle pass an S/C command to CSRFile.
Their writeback of the old value suppresses the same edge's counter increment.
Rocket rewrites encoded zero-operand reads to R. The C00/C02 read-only aliases
have no counter write case. Consequently visible `mcycle` cannot always be
derived from elapsed model time and a fixed offset. Architectural retirement
also differs from the visible `minstret` count in these cases. Full pins, source
lines, paired actual SV and4,582 checked transitions are preserved in
`build/pipeline-csr-proof-closed`.

The profiler accepts a native observation block:

```json
{
  "counter_read_observations": {
    "schema_version": 1,
    "complete": true,
    "source": "actual model capture location and phase provenance",
    "reads": [
      {"sequence": 0, "node": 42, "hart": 0, "pc": 2147483648,
       "raw": 2952798963, "csr": 2816, "destination": 5,
       "result_discarded": false, "value": 100,
       "read_cycle": 120, "read_phase": "named actual model phase"}
    ]
  }
}
```

The example only illustrates the schema. Native instrumentation must capture
actual non-peek guest getter results, buffer them until successful retirement,
and discard observations from trapped instructions. `complete` means every
successfully retired guest counter getter evaluation is covered. Per-hart
sequences are contiguous and include discarded rd0 evaluations. Internal/debug
reads do not enter this block. The phase identifies what the model actually
does; it does not claim a validated hardware phase.

`iris_model.counter_regions` checks the decoded CSR, destination, actual
executable ELF/ROM bits, completed instruction event, hart, PC and read timestamp.
The timestamp can precede the instruction's COM completion, but must lie between
its submission and completion. Guest `IRIS_REGION` values must each match one
unique non-discarded captured cycle read. Missing, partial, forged, ambiguous or
out-of-order evidence is refused. No guest console or Merlin launch change is
required for uniquely identifiable boundaries. Graphs without captures retain
the older, explicitly limited constant-counter proof path.

The resulting JSON uses `observed_regions` for read-delimited measurements.
Their `cycles` are elapsed base-clock ticks; `guest_mcycle_delta` is the
unsigned64-bit subtraction seen by the program. Counter writes, wrap and stopped
counters do not redefine elapsed time. The original dependency events and their
full spans remain intact. Unit and ELF-function occupancy intersects those
spans with each region; nested regions are supported and are not additive.
Perfetto receives both counter-read instants and measured-region tracks.

Operation wait statistics intersect submission-to-start intervals with the
region, including waits that continue beyond its end. They include dependency
and resource delays and do not claim an additive CPU stall breakdown. Completed
payload/MAC counts require explicit instrumentation and completion strictly
inside the timestamps. A nonzero payload ending exactly on a read boundary is
unavailable until ordering within that edge is captured. Unfinished operations
receive occupancy but no completed work. Missing arithmetic/traffic/peak
evidence stays unavailable, and no calibrated roofline is inferred.

The parser/intersection tests use synthetic fixtures and cover nonlinear counter
values, differing read/COM timestamps, discarded destinations, two harts, waits,
crossing events, nested regions, counter wrap, incomplete operations and forged
evidence. Native integration and real guest demonstrations are separate gates.
