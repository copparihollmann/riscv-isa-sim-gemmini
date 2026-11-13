# Context-safe Saturn host wrappers

These are new host-only derivatives of the frozen reference and first numeric
substitution SDKs. Every generated RTL/model object and Verilator runtime
archive member stays byte-identical. Only `saturn_timing.o` changes. The old
capsules and their single-instance qualification remain preserved.

Verilator5.052 context construction changes the thread's active context, while
generated `eval()` does not reliably select the model owner. A composed host
must select and restore the owning context explicitly. The new wrapper scopes
construction, evaluate, sample, commit, diagnostics and destruction. Failed
construction/phase validation also restores the caller. No source edge is
added. The implementation initializes each context's own command arguments.

Use the new SDK pair in either
`build/saturn-timing-context-fast-v1/sdk` or
`build/saturn-timing-context-reference-v1/sdk`. Existing four-argument
construction remains available. A new overload accepts a span of source
plusargs. Host `+verilator+...` controls are refused there; the explicit seed
and reference reset policy retain their meaning. `context_argument(prefix)`
queries actual own-context argument matching without advancing source time.

Each variant passes five three-unit interleaving scenarios with RVV and VME
whole-SoC traces, reversed/shuffled construction and execution/commit order,
foreign active contexts and distinct seeds/arguments. Per variant this covers
1,200,555 source core edges,18,890,437 qualified output fields and3,629,775
caller-context preservation checks. The original wrapper fails the directed
construction-context control. Both derivatives also pass constructor-error,
default-argument isolation, move-assignment/construction and destruction tests.

This does not isolate Verilator's global/thread RNG stream: its implementation
caches a per-thread RNG under a global seed epoch and assumes a single context
per thread. Unreset concrete bit patterns can remain construction/evaluation
order-sensitive. The tests qualify actual initialized active fields after real
reset and explicit operand/tile initialization. They do not constructor-zero
unknown state or claim raw unreset-bit invariance, general definedness or
whole-SoC/held-out timing accuracy. The source-reset scrub caveats remain.

The wrapper is suitable for composing source peers using repeated same-edge
evaluate/sample and exactly one source commit. It still requires exact peer
ready/data/credit/clock connections and closed knownness. It supplies no memory
service, state checkpoints or fitted delays. The fast numeric variant's
previous approximately23k compute edges/s remains a component measurement;
the host context fix is not claimed as a new production-speed architecture.

Freeze and verify commands are:

```sh
python3 timing/saturn_timing_context_package.py
python3 timing/saturn_timing_context_package.py --verify
```

The context capsule explicitly depends on both immutable Saturn reference and
numeric-substitution capsules. Primary Spike, the shared engine and all FPGA
inputs remain unchanged.
