# Disabled column readout depends on issue history

The observed image accepts the column-select tile move, but its configured OPU
has no horizontal readout. The backend captures the vertical readout pipe. The
captured words depend on the controls present when that capture occurs, including
later issues and idle cycles. A mathematical column lookup cannot reproduce it.

The [managed FPGA observations](actual-vme-column-observation.json) retain all
384 column attempts, covering both compute harts, 32 indices, two linear tile
patterns and three trials. None trapped; none returned a mathematical column.
All 768 surrounding normal-row checksum controls passed. These controls preserve
row checksums, rather than individual row words.

[Source characterization](../build/disabled-column-source-characterization-v1/report.json)
matches all **12,288 observed column words**. It uses the source sampling geometry,
without an index-to-observed-values table. For this isolated VL32 fixture with
eight contiguous issues, destination group `g` and cluster `c = index & 3` sample
controls from issue `q = g + 3 - c`. The source move latency is `5-c`; the OPU
output register and backend control/capture registers determine that offset.
After the final issue, idle controls select tile0/subtile0/cell0. The backend still
samples the last vertical cluster row. The report and its CSV identify every
sampled cell and observed word. This formula applies to that fixture and issue
history; it is not general instruction semantics.

The [independent RTL history proof](../build/vme-column-history-proof-v3/report.json)
couples the saved sequencer and full OPU array to backend register assignments
extracted unchanged from the co-located generated RTL. It covers 1,216 scenarios,
41,643 source edges, 80,256 checks and 45,056 known consumed output words. All
4,096 MRF words are initialized through public input controls and scanned back.
The backend register differential adds 2,935,276 comparisons. Four reset-prefix
capture words remain unqualified and are never consumed.

**288 comparisons changed output when external availability changed while the
instruction index stayed fixed.** This demonstrates why the contiguous-issue
formula cannot be installed as a functional shortcut. VRF availability is an
explicit fixture input in this proof; it does not reconstruct the whole physical
arbiter or arbitrary application execution.

The [frozen closure](../build/vme-column-history-closure-v1/report.json) binds the
exact model objects, source cut, stimuli and consumer. Archived replay reproduces
stdout and stderr byte for byte. Five corruptions are rejected. The exact source
snapshot is Saturn `536774bd4c5e3bcd7813a4a0dc72fc87e5818532` plus the recorded
working-tree changes. Its OPU snapshot has SHA256
`be2f6842fc72538ef7b458e22e0f3a3668a58ae3038d03a5deea47f629adf3ff` and an ungated
clock. The cloned OPU source differs in clock gating; the proof preserves this
distinction. Full source-to-loaded-image association remains unverified.

Spike continues to report `IRIS_UNSUPPORTED_COLUMN_MOVE` for this capability.
It supplies neither a fabricated transpose nor an architectural illegal trap.
Enabling electrical emulation requires the actual issue/capture history and its
definedness to flow through the timing model. Normal row moves retain their
separate functional checks. No native instruction implementation was changed by
this characterization.
