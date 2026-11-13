# Bounded live private values

This new epoch derives from the immutablef451 private-value model. It preserves
that source tree and package. The only native changes are
`riscv/iris_forwarded_values.h` and the explicit capacity argument in
`iris_shuttle_issue.cc`.

Only uncommitted records remain in the private map. COM checks the first map
entry in constant time, verifies the real architectural value, and erases that
record immediately. Reference-counted result cells keep already latched
operands valid after retirement. Completion releases its source handles;
rollback marks canceled cells so stale handles fail explicitly. Future issues
read committed architectural snapshots when no younger writer exists.

The native capacities are8 live records per Shuttle and3 on Rocket, matching
the current source pipeline admission limits. Live cells have a separate3×cap;
a forgotten external consumer cannot silently accumulate unbounded history.
These are storage/admission bounds, not invented hardware latencies. The map's
lookup cost is bounded by those fixed capacities; COM never scans retired
history. Future branch integration must retain/release its operand handles at
the source stages and cancel only younger uncommitted work.

The100,000-instruction host stream stays at most3 records/6 cells and drains
both to zero. RAW/WAW/late-counter/unknown/constant controls and explicit
capacity refusals pass.32,768 independent integer values and65,536 actual saved
ALU outputs pass. The native gates repeat the entire previous scope, including
5,790 per-instruction guest values and real three-hart Zephyr6+9 regions. All35
complete graphs across directed/memory/live/UART/Zephyr are byte-identical to
f451, including cycles and private values. This is equivalence of the modeled
schedule, not a new RTL timing accuracy result or host-speed comparison.

Full frontend/branch/RAS/cache timing remains separate work. No primary
publication, hardware action, calibration, full RTL certificate or held-out2%
claim follows. See FRONTEND_VALUES.md for the precise private-value semantics
and preserved historical failures; its linear-history limitation describes the
olderf451 epoch and is resolved in this successor.
