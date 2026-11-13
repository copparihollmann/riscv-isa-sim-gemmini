# Source-specific counter reads

The source-specific policy, actual guest read observations and further
whole-CPU validation are now implemented in an isolated review epoch. See
[COUNTER_POLICY.md](COUNTER_POLICY.md). The component analysis below records
the original discovery and preserves its historical failure evidence.

The frozen646 candidate and5e6 primary do not reproduce the source Shuttle
counter-read behavior described here. Do not publish a correction by adjusting
an expected count or a global offset. Original scalar RTL validation failures
and both frozen packages remain intact.

`build/pipeline-csr-source-proof-v2/results.json` passes4582 independent CSR-unit
edge checks. The paired modules are the actual saved-Iris `CSRFile.sv` and
`CSRFile_2.sv`, regenerated from FIR SHA
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
The input wrapper explicitly ties every unrelated input to zero. A separate
Python oracle checks decoded commands, access legality, every register transition,
reset/state continuity, wrap and read data. The proof records exact SV, C++,
wrapper, tool and Scala evidence hashes/full repository SHAs. This is a counter
component proof; source-build association and Ethan-image equivalence remain false.

## Why the read is destructive on Shuttle

Pinned Shuttle `Core.scala:1082-1088` passes the scalar decoder's CSR.S/CSR.C
command to CSRFile even when the encoded rs1/uimm field is zero. Its
`MicroOp.scala` read-only predicate correctly suppresses write-illegal traps and
frontend flushing, but does not rewrite the command sent at COM.
`IDecode.scala:118-123` supplies those S/C commands.

Pinned Rocket `RocketCore.scala:353-354` explicitly rewrites these zero-field
read commands to CSR.R. This is a real difference between the harts.

`CSR.scala:1293` treats S/C/W as write commands. For S/C with operand zero,
`readModifyWriteCSR` returns the current register value. The later
`writeCounter` assignment overrides the same edge's ordinary increment.
`Counters.scala:41-69` exposes the old registered value before the edge.
The actual saved SV has the same wiring and update priority.

For a clock edge with old values MC/IR and retirement count R, the default
updates are MC+1 unless CY is inhibited, and IR+R unless IR is inhibited.
A writable counter operation replaces the addressed update with its explicit
write value. Therefore:

| Counter read form | Shuttle B00/B02 interval | Rocket B00/B02 interval | C00/C02 interval, either hart |
| --- | ---: | ---: | ---: |
| CSRRS rs1=x0 | 256 | 257 | 257 |
| CSRRC rs1=x0 | 256 | 257 | 257 |
| CSRRSI uimm=0 | 256 | 257 | 257 |
| CSRRCI uimm=0 | 256 | 257 | 257 |

Each interval contains an opening read,256 single-retirement body edges and a
closing read. On Shuttle, the opening B02 read physically retires but its
counter writeback suppresses that retirement increment. B00 readback similarly
suppresses a cycle increment. The read-only aliases have no counter write case.

A source-level replica of the two-counter measurement macro—B00 read, B02 read,
256 body edges, B02 read, B00 read—produces component deltas258cycles/256instret
on Shuttle and259/257 on Rocket. These component values do not include real
frontend/pipeline overhead and are not substituted for the full-CPU measurements.

Nonzero rs1 fields containing the value zero remain writes on both cores.
CSRRW rd=x0 and CSRRWI uimm=0 also write; the write overrides same-edge counting.
Writes to read-only aliases are rejected by the source core decode and are not
committed to CSRFile. All these distinctions are checked in the40-case command
matrix. The corpus also checks CY/IR inhibit set/clear edge behavior, explicit
counter writes while inhibited, and a two-lane retirement wrap on Shuttle.
Mcountinhibit's writable mask is5; counteren's separate7/7/5 support masks must
not be confused with it.

The whole saved-Iris scalar experiment independently observed256 on both
Shuttles and257 on Rocket, matching this causal explanation. Its original strict
collector still fails and its cycles remain an unqualified fitting observation:
dependent263 versus candidate267, independent136 versus140 on each Shuttle.
See `build/scalar-rtl-observation-v1/report.json`; do not relabel that failure.

## Read phases and profiling

The unit proof establishes pre-edge CSR read data and write-over-increment
priority. Shuttle selects CSR read data in COM and writes the RF in WB. It does
not establish how the current model's COM event boundaries align to absolute
whole-CPU counter edges. That alignment needs an explicit implementation and
further source/RTL validation. A guessed minus-one return value is insufficient.

Visible mcycle after B00 reads is not always a constant offset from elapsed
model ticks. Visible minstret also differs from the number of architecturally
retired instructions; both quantities must be retained separately.

Future native instrumentation should buffer actual non-peek guest counter read
evaluations, then emit them only after successful architectural retirement:
hart, PC, raw instruction, CSR, value, per-hart sequence, owning completed node,
read cycle and a named actual model phase. Record destination and whether rd=x0
discards the result. Internal reads and trapped instructions must not create
successful marker observations. The profiler can then match guest values to
unique actual observations, including writes, inhibits and nonlinear offsets,
without deriving read values from the event clock. Ambiguity must fail closed.

This proof is limited to counters. Shuttle's unchanged S/C routing also reaches
other CSRs; simultaneous asynchronous flag/CSR write interactions require their
own audit before broad source emulation is declared correct.
