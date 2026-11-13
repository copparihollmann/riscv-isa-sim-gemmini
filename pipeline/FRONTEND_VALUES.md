# Live private result values for future frontend integration

The sixth isolated native extends the frozen35901887 ABI4 source. It does not
activate frontend/cache/branch timing. An explicit fixture opts into private
values alongside the existing source pipeline:

```
pipeline_values private-pure-integer
```

Native `f451417e15bb7f0862b7519dbc2666c8b181cc90f6c1d8204ba62562899eba40`,
UART `2e205a24a07442a96f1703e3621df9c606db91b562787135f3dd4f253dcfa0e4`,
full source overlay `1b8cf55aa94eefb3162b9e6a2df4f17099cad5eb03c99998ab166b50d9129744`.
Build: `build/spike-frontend-values-v2`; source:
`pipeline/riscv-isa-sim-frontend`. The parent is frozen at
`build/combined-frozen-35901887`, overlay
`e33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060`.
Neither the primary5e6 package nor previous source epochs changed.

Private values are computed at existing result-ready EX/MEM callbacks on both
Shuttles and Rocket. Operand references bind the producer version at issue,
including source-permitted same-packet WAW and retimed RAW. Counter destinations
receive their actual value at COM/WB. Architectural register writes remain in
ordinary Spike execution at ordered COM/WB; each successful instruction then
checks its private known result against the actual destination. IRQ/trap/fetch
precision and every timing node/cycle remain the existing pipeline's contract.

The graph optionally reports `private_value_ready` and `private_value` for each
pipeline instruction. Null is unknown, not zero. Partial-bit knownness remains
owned by the inherited functional model. The private file transports completely
known values and recognizes selected source-permitted constant results; it does
not replace architectural unknown-state checks. Future branch consumption must
explicitly refuse an unavailable/unknown value. The standalone cancellation API
rolls back private versions and rejects already committed younger state; no live
graph branch cancellation is enabled by this epoch.

The independent value test covers32,768 instructions across all30 admitted ALU
names, integer goldens and65,536 outputs from the actual saved Shuttle/Rocket
ALUs. Host controls cover RAW/WAW version binding, result-before-producer refusal,
ordered COM, mismatch detection, cancellation, unknowns, source constants and
late external results. The native2048-operation corpus checks5,790 nonzero
register destinations across all three harts against independent per-instruction
integer values; all6,144 result nodes complete before architectural commit.

The actual native also passes directed11+3, memory6+7, initialized live8+3,
UART12, real three-hart Zephyr scalar6 and mixed9, and strict captured-CSR
profiling of all9 mixed regions. The exact32-case functional corpus uses the
already qualified combined359 argv/ELFs and preserves its expected diagnostics.
All timing clocks and latencies remain explicit uncalibrated fixture inputs.

Two old5e6 corpus runners were deliberately retained as failed controls: the
original FPComp guest observes unreset FCSR, and the original busy-peer guest
reads undefined s0. Both failures reproduce on frozen359. Their results are
`build/frontend-values-inherited-negative-controls-v3`; the initial comparison
without dtc on PATH remains separately preserved/inconclusive. The successful
current replay uses the **unchanged** corrected ELFs from combined359, not
weakened goldens. The ABI1 UART-source compilation refusal is also retained;
the matched build uses exact frozen ABI4 plugin source `pipeline/uart-plugin-abi4.cc`.
The UART negative check changes only the expected missing-symbol ABI suffix
fromv1 tov4, with its adapted runner archived.

Current limitations: full frontend/prediction/refill routing and speculative CFI
execution remain unimplemented. The private file retains a block's value history;
its current commit-order guard scans that history, so long unrolled blocks need
a bounded/constant-time frontier before performance-scalability qualification.
No calibrated cycle improvement, full source/RTL/image certification or held-out
2% claim follows from this private-value foundation. See `FRONTEND.md` for the
separately frozen causal cache/frontend components and required live interfaces.
