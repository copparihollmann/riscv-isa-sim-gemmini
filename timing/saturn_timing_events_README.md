# Typed Saturn physical events

`build/saturn-timing-events-v3/sdk` supplies `saturn_timing_events.hpp` and
`libiris_saturn_events.a`. Link it with the frozen Saturn timing SDK/library,
using C++20. This is a read-only projection, not another scheduler or a source of
memory timing. It accepts complete settled physical input/output frames once
per committed source edge. It requires actual reset history and checks every
field width. Snapshot seeding is deliberately unsupported.

The projection preserves EX candidate identity, actual EXfire, source MEMkill
and S2 front token. It emits source late-retirement, replay, exception, scalar
response and flag updates separately. Command metadata includes hart, raw
instruction, PC, actual vector/tile configuration and an optional caller-owned
configuration epoch. The epoch never affects unit state or acceptance.

Every accepted TL A/D beat carries real source ownership, transaction size,
beat index and first request edge. Put payload has per-byte protocol masks; Get
request payload is unqualified. Sub-beat Get response masks select only the
requested address lanes. The legacy `data_defined_mask` field describes those
protocol significant lanes; it does not certify memory initializedness. A
consumer must intersect it with the functional/memory producer's known mask.
Scalar/vector shared-FPU requests retain all
three65-bit recoded operands and physical mode/type controls. These events do
not invent a PC owner for TL/FPU work. Proving internal VAT/LIQ/tag correlations
and exposing internal VRF/issue/OPU utilization are further source-observer
work. A COM front token does not mean asynchronous vector effects completed.

The C++ projection matches the independent Python stage/protocol ledger across
all12 whole-runtime captures:932,079 actual source edges,8,093 command identity
checks and15,906 accepted TL beat checks. The command hash includes actual EX
configuration, identity, stage edge and caller epoch. Seven meaningful
corruptions/refusals cover wrong A size, unowned D source, missing output edge,
wrong hart/profile, input/output width and missing reset history. This evidence
does not establish whole-SoC timing or performance accuracy.

The final receipt is `build/saturn-timing-events-v3/report.json` SHA256
`49891339a502da809325f8d377cfa635a23d5d88c7c4eb172774466645baa5cc`.
It depends on both immutable Saturn capsules, which preserve the independent
whole-SoC captures and exact SDK source/port identity. The source and native
artifacts are copied into the events directory. Verify and replay it with:

```sh
python3 timing/saturn_timing_events_verify.py
```

`events-v1` is preserved before the added width/reset admission guards.
`events-v2` is preserved with its incorrect full-bus sub-beat response mask;
the independent data/mask hash in v3 detects it without changing instruction
identity or event counts. The explicit old-library witness is built with
`saturn_timing_events_mask_witness.py`. Primary
Spike, the shared engine, frozen reference/fast SDKs and FPGA inputs are unchanged.
