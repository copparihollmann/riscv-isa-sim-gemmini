# Shuttle warm-load forwarding phase

The opt-in successor in `build/warm-load-phase-frozen-16184afc` corrects a specific early bypass in the fast model. It does not add a per-load fitted penalty. No default, frozen predecessor, timing coefficients, FPGA input, or reserved hardware timing label was changed.

Select it with:

```
empirical_load_front dram-L1-hit-Shuttle-COM-forward-v2
```

The old `dram-L1-hit-latched-response-v1` selector remains available. The source-derived correction affects harts 0 and 1 only. The new native binary and its matched ABI4 UART library must be used together. The library was rebuilt against this isolated tree; the UART/device source was not changed.

The saved Shuttle DCache returns an actual warm hit in S2, two edges after an accepted EX request (`DCache.scala:483–518`). Shuttle Core enables the integer COM bypass from that hit (`Core.scala:1142–1155`). The consumer reads that bypass at RRD and enters EX on the following edge. The former model latched its private load transport in MEM and exposed that transport to RRD on the same edge. An ordinary dependent ALU could consequently enter EX two edges after the load, one edge too early.

The new mode preserves that private transport latch and the original COM-owned functional load. It suppresses only the warm-hit pre-COM bypass. The source-ready condition is a phase gate, not a delayed architectural memory operation. Coherence-fallback/late responses retain their separate existing path. Rocket remains unchanged: its source has `fastLoadWord` and a distinct MEM word-bypass path, which does not justify copying the Shuttle correction.

The graph's historical `LD.result-ready` node still denotes the **private transport latch**. Under the new mode it is not a claim that the source integer bypass is available at that node's end. The policy is explicit in `load_front_forwarding_policy`; consumer admission is held until the load's own COM edge. Functional XPR publication remains at COM.

The finite source and native results are:

| Continuous body | Saved Core input delivery | Saved load EX spacing | Former native | New native |
|---|---:|---:|---:|---:|
| `ld a0,0(a0)` | one lane | 3 | 4 | 4 |
| repeating `ld a0,0(a0); addi t0,a0,0` | one lane | 4 | not the native delivery contract | not the native delivery contract |
| same repeating load/ALU pair | two lanes | 3 in the steady stream | 2 | 3 |

The original one-lane observer could not establish two-lane throughput. A new observer supplies the actual two-lane prefix boundary continuously and records accepted RRD handshakes. It shows that the older ADDI can share a packet with the next load: the source permits one ordinary memory operation anywhere in the packet. The first source load/ADDI packet uses the configured late ALU. The native path still conservatively splits that particular packet; this work does not qualify that initial late-ALU packet as exact.

The straight-load native control still takes four edges because its unresolved effective-address admission drains the existing cohort. That separate conservative boundary is preserved and reported, not hidden by a blanket load penalty. The source instruction-cache supply and memory/coherence state can also add real delays. The strict issue-phase comparison therefore uses an explicit constant functional instruction-supply fixture (empirical Icache flag off); separate runs preserve the selected instruction-cache service costs. Neither fixture is an actual whole-SoC warm-cache guarantee.

The source proof uses the unchanged saved `ShuttleCore` cut and a separately qualified full cache/NoC source System. Both configured Shuttle tiles instantiate that same Core module. The cache witness performs actual reset and 64 accepted initialization loads per Shuttle, then measures real hit/tag/data handshakes without additional TL traffic. It never seeds internal arrays, the replay queue, or an observed readiness trace. The Core witness receives a two-edge external response contract independently demonstrated by that cache witness. The outer fixture's explicit synthetic service parameters do not contribute a request during these four hit intervals.

The exact saved Core source is `build/shuttle-lsu-phase-source-v1/rtl/ShuttleCore.sv` (SHA256 `8867c4d3942cf2fe6b5b413c3c01007ac530cd3c9983ed261309d10843009a2f`), derived from the archived Iris elaboration. Its build receipt binds all 56 RTL modules and the compiler. Associated Scala and current source overlays are separately hashed; the source pin alone is not substituted for the actual saved bytes. Relevant pins are Shuttle `a536ed1df91a0f65770e36758291d02a8cb929c4` and Rocket `fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0`.

Reproduction artifacts:

- `timing/warm_load_phase_shuttle_v1.cpp`, `v2.cpp`, and `v4.cpp`: source straight-load, single-lane pair, and corrected two-lane observations, seeds 1 and 17. The failed intermediate v3 assertion is preserved.
- `timing/warm_load_phase_cache_v1.cpp`: four actual L1 hit observations across two seeds and both Shuttle ports.
- `build/warm-load-phase-native-constant-fetch-proof-v2/report.json`: independent typed source transcript and actual native COM/RAW graph joins, with seven corruption controls.
- `build/warm-load-phase-successor-QA-v1`: four numerical, normally exiting three-hart executions with the original selected cache costs.
- `build/warm-load-phase-parent-OFF-parity-v2/report.json`: exact former-selector parity against frozen 2b8, including all 1,555,905 graph nodes, CSR observations, console bytes, and all predecessor JSON fields. The sole new field labels the unchanged legacy forwarding policy. The prior reader's wrong JSON-key failure is retained.
- `build/warm-load-phase-guards-v2/report.json`: actual three-hart coherence/opaque-copy control, three undefined-consumer refusals, and duplicate/unknown selector refusals. The first guard reader's wrong diagnostic-name expectation is retained.
- `build/warm-load-phase-functional32-v1/results.json`: all 32 canonical functional cases, with each test's fatal-PC environment preserved; timing is off for this compatibility group.
- `build/warm-load-phase-ON-five-OS-v1/report.json`: all five real three-hart Zephyr timer/context/ownership gates with the new selector and source H/S/D FADD enabled. This is functional mode-activation QA, not hardware timing validation.

Native time uses the source counter policy and the fixture's explicit 500 MHz base/clock dividers. Source witness timestamps are numbered physical source edges. A hart's inhibited `mcycle` cannot globally align the multicore graph; the phase proof joins actual COM/RAW nodes instead of treating per-hart cycle reads as global timestamps.

There was no hardware contact, no reserved hardware timing consumed, no parameter refit, no full-SoC or loaded-image association claim, and no accuracy certification. Known Zephyr/hart2 and page-store hardware divergences remain unresolved. This component correction and passing OS tests do not establish a universal ±2% bound.
