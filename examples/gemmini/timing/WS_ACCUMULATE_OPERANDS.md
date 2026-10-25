# Accumulating WS operand lifetime candidate

Status: inactive, opt-in, provisional structural approximation. No prices,
physical observations, hardware configuration, or current selected runtime change.

Select `target.scheduling.split_ws_accumulate_operands = 1` only with staged v5
and its conservative accumulator storage holds. Default behavior is unchanged.
This flag does not enable earlier reservation/FIFO retirement, MUL/PRE pairing,
accumulator overlap, or earlier result readiness for accumulating commands.

## Selected RTL basis

The audited Gemmini Scala sources are from the selected
`phase1-harness-v2/.tmp/chipyard-fire-aligned/generators/gemmini` tree:

- `ExecuteController.scala`, SHA256
  `59b068a79d6063d283561813f7fb65c3503e94d5923334e553ab5d42e2692e8c`:
  lines 405–444 end the SRAM operand stream at `about_to_fire_all_rows`;
  lines 639–681 pop consumed commands; lines 947–966 drive the accumulator
  write from mesh response, including `bits.acc := w_address.accumulate`;
  lines 971–990 separately retire the output tag at the last mesh response.
- `AccumulatorMem.scala`, SHA256
  `ff56017f84d6b72ad4ee84e311a714e27e3f8d2085d37d61b6a0985fd5070ae7`:
  lines 113–129 capture accepted writes and drive the accumulation adder;
  lines 381–388 protect pending same-address reads/writes. Accumulator RMW
  therefore does not require retaining scratchpad operands until result arrival.
- The selected gSIM elaboration SHA256 is
  `6748b9756799c086a6fb06e6d80b4b052f2771f9eb1858c172e14dcf441ba149`.
  ExecuteController feed logic appears directly at FIR line 299012 onward,
  retaining the Scala 405 source annotations. Accumulator output logic retains
  Scala 950–955 annotations. The previously retained 252-module exact relation
  covers AccumulatorMem and Scratchpad, not ExecuteController. This audit uses
  the selected gSIM ExecuteController directly; it asserts no complete gSIM /
  FireSim top-level or clock equivalence.

The existing full-tile feed occupancy remains the approximation of operand
consumption. It is not a newly measured latency. Accumulator service keeps its
existing full-result reservation, including the same-address spacing obligation
noted at ExecuteController lines 293–301. No fitted correction is introduced.

## Admitted effects

Only full-tile, untransposed WS COMPUTE_PRELOADED with unit A/C strides,
non-garbage scratchpad A and preload source, and accumulating ACC output can use
this rule. ACC read tokens must equal all output ACC tokens exactly. No retained
scratchpad reader is permitted. Other commands retain their previous conservative
rule (and existing unsupported-protocol/unknown-price handling).

The first event consumes SP operands at the unchanged compute occupancy. It
reserves the ACC conflict resource for the unchanged full result latency.
The final event publishes every result and holds every non-SP dependency through
that original completion. The following PRELOAD still waits for the result;
existing accumulation and memory hazards remain. This can permit input DMA to
reuse consumed SP rows while the accumulator result is propagating.

## Checks and remaining gates

`tests/staged_test.cpp` checks default-off versus selected behavior, exact SP
reuse boundary, unchanged ACC port/read/result/configuration/PE lifetimes,
following compute ordering, and conservative fallbacks for tails, transpose,
strides, extra ACC reads and retained SP reads. Missing latency remains UNKNOWN.
The full focused staged test passes; `bridge.cpp` passes strict C++17 syntax
checking. These are model invariants, not physical timing qualification.

The retained deep-K public trace that motivated the investigation remains
39,404 modeled versus 27,910 measured cycles under the previous candidate.
Its 256 accumulating computes held SP operands for the full 56-cycle result
latency instead of the selected 17-cycle feed occupancy. This observation
identifies the old model rule; it does not establish that all physical residual
comes from that rule. No new same-ELF replay has been performed for this change.

Activation requires a separately pinned provider/model revision, unchanged-price
review, complete-output retained-ELF replay, and continued qualification denial.
Independent physical validation remains necessary before accuracy claims.

## Resident pairing after FIFO admission waits

`StagedObserver::pair_preload` previews the two actual controller FIFO admissions.
A slot unavailable at CPU submission may become available before the already
reserved operand feed. Both command issue beats must still finish before that
feed starts. The observer does not move the feed, backdate commands, extend FIFO
capacity, or shorten operand/output hazards. A late admission retains the
separately scheduled fallback. Queue preview does not mutate ownership when a
hazard or residency check refuses the pair.

The focused eight-tile regression compares ten FIFO entries against a wider
FIFO when every required admission can legally finish in time. The previous
implementation fails that regression by introducing an extra PRELOAD feed at
tile seven. Existing tests retain refusals for late arrival, insufficient FIFO
capacity, different weights, shared banks and output hazards.

An isolated public replay on 2026-10-23 changes queued drain from 146 to 129
cycles against a retained 130-cycle gSIM interval. The complete unfenced call
changes from 1717 to 1700 against 1740 cycles; its total error increases because
readout was already underpredicted. Fenced execution and readout are unchanged.
These developmental observations justify investigating this structural rule;
they do not qualify a fitted model or authorize replacing a selected runtime.
The exact public inputs, outputs, model and native source identities are recorded
in Merlin's `public-ws-current-residuals-20261023` curated evidence.
