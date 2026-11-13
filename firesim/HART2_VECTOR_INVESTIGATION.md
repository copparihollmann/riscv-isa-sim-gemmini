# Reproducible hart2 completion failures

The FPGA is operational: the12-region smoke,6,750-region broad campaign,
four285-region diagnostic Zephyr images and120-region baremetal vector batch
passed. The failures below concern particular programs. All printed results
have correct independent checksums; the missing result is completion. No
instruction PC or failing internal component has been identified. The image
has no TracerV/AutoCounter/SynthPrint instrumentation.

## Two current reproducers

| Program | Actual FPGA result | Same-ELF native359 result |
|---|---|---|
| Original patched Zephyr training image | Two runs complete25regions, then stop before `zephyr.fit.vme_or_copy.mask4.trial.0` | All285regions pass at seeds0/17 |
| Baremetal page/CSR diagnostic | Two runs complete1,174regions, then watchdog at `rvv.page.hart2.store.g0.before128.mode0.pattern0.trial.4` | All2,550regions pass at seeds0/17 |

The first program uses ordinary RVV on hart2, not VME instructions. The OS has
all three harts online, pinned workers across all seven nonempty hart subsets,
normal idle/timer activity and repeated scalar/VME/vector-copy kernels.
The original ELF is
`cb4907f1ab776506fdfc93e2f60df33b3bd2b4492a0d4025742dc64901b1f32e`.
Its source is `zephyr/firesim-fit-app`; the shipping patched kernel is
`third_party/zephyr-iris`, not the untouched upstream `third_party/zephyr`.

The second program is bare machine mode. Hart0 initializes buffers and polls
completion with sparse bounded CLINT checks, hart1 waits in WFI, and hart2
executes all vector traffic. It independently varies which of four256-byte
LMUL8 groups crosses a4KiB boundary and all seven32-byte split positions,
load/store/both sides, zero/varied data and fenced/plain/CSR-restore modes.
Each case has five trials. All three actual runtime `vlenb` values are32.
Its ELF is
`a6db1d96312a279e3b1c8a5b001f66972423a81259b792ec616d17c9812a55f5`.
Source is `benchmarks/rvv_page_transport`; build/gates/22negative controls are
under `build/rvv-page-transport-v2*`.

Both page runs stop at the same fifth repeat, after four successful repeats
of that case. Every field in all1,174printed region objects is identical
between runs, including absolute mcycle boundaries, minstret, checksums,
addresses and guards. The completed prefix includes850fenced-mode regions and
all unfenced load-crossing cases. Later unfenced CSR-restore cases are untested
because execution never reaches them. This does not prove that the page and
Zephyr failures have the same cause.

Independent repeat proof:
`build/fpga-rvv-page-repeat-comparison-v1/report.json`, SHA256
`6ee3deea1101888c9f4072166f89a569b3d53a817171c5895721f51f7b499fb2`.
Both raw external archives are verified:
`31e92e0610a950d14f36b3e4a319b534256eeefeeb5a8c41415fc924dd65b39b`
and `a9774d6b05bf6f2ebb194cdbcde07343c0009b4cecff618c9a65e5ab23afbff2`.
The guest CLINT watchdog exits1; it is not the host wall watchdog expiring.
Original Zephyr runs instead hit the180s foreground host watchdog, exit124.

## Controls and limits of their conclusions

| Zephyr variation | FPGA result | Interpretation |
|---|---|---|
| Instrumentation plus kernel/app fences | All285pass | Several factors changed |
| Same instrumentation without added fences | All285pass | Instrumentation/layout can mask the failure |
| Original app, ten kernel fences only | All285pass | Still changes code size and placement |
| Exact-layout ten-NOP control | All285pass | Fences are not necessary for these matched ELFs |
| Original layout, only two ADDI offsets40→104 | Stops after25 | Moving saved-vector cursors alone is insufficient |

The minimal fence/NOP pair has identical load segments, ordinary symbols and
data addresses; only ten instruction words differ. Both move the hart2
saved-vector buffer64bytes relative to the original. The last control instead
preserves the original load segments, allocated section/BSS/worker addresses
and complete symbol table. It shifts all three cursors within their owned
8192-byte vreg arrays, changing exactly two ADDI immediate words and adding
no instructions, fences, observer or metadata writes. Source/native context
checks and physical touched-byte/page tables are independently frozen.

The pointer-only control's comparison is
`build/fpga-zephyr-vreg-shift64-v1-comparison/report.json`, SHA256
`e412ea0ac169ef1553f72f69f7b6455e483481bc35e86c11f75bec5d7078f5e2`;
its failed run archive is
`2f85ce2694138a0613caa46b251c83819116de41c1e0d430fc21813f10f46527`.
It is a control, not a software fix. Code spacing, frontend placement,
timing/history and other coupled state remain unresolved.

The original hart2 vreg start is `0x8001dce0`: the fourth256-byte group crosses
a page32:224. The minimal fence/NOP pair starts at `0x8001dd20`, so its third
group crosses224:32. The previous passing baremetal transfer batch used
page-contained input/output arrays and did not cover this distinction.

The shipping context copy uses `vsetvli ...,x0,e8,m8,ta,ma`, unmasked four-group
`vle8.v`/`vse8.v` transfers and three byte-cursor adds. It then restores saved
VL/vtype, vstart and vcsr. Its cursor is correctly declared `+&r` in the
shipping patch. An input-only operand seen in the upstream tree is a different
source epoch and must not be diagnosed as the current compiled program.

## Available memory evidence

The guarded read-only observer actually sampled startup readLatency30 and
writeLatency30 on these runs. Units are FASED memory-model target-clock cycles,
before driver initialization. Generic presence was checked before/after and
both parameter samples agreed. See `MEMORY_OBSERVATION.md`. No register writes
or clock/memory override was added. These values do not establish CPU/SoC
latency, selected runtime max-requests or relaxed-mode settings, full
source-to-image association or independent loaded-image readback.

Archive-bound raw FASED summaries for the original Zephyr, pointer-shift and
page failures are `build/*-fased-summary-v2/report.json` for those run names.
Near the end, transaction-register readings are constant while the two
histogram_0 counters advance. Readout is32bits, timestamps/atomicity and
general wrap alignment are unavailable. No bandwidth, exhaustive occupancy,
per-hart attribution or latency distribution is inferred. The inspected source
also has a non-counting final histogram bin, so summing bins is invalid.

An independent source SaturnRocketUnit experiment proves that four LMUL8
loads can reserve all32requests, wrap the five-bit reader count to0 and still
hold busy for512edges without responses. Matching128response beats drain
correctly with complete VRF goldens. Counter wrap alone is not proof of
premature completion or the physical cause. Store page fission, coherence,
ROB/queue lifetimes and scalar/vector control require separate examination.

## Reproduction and continued work

Use the current working recipe and AGENTS/OPERATING_RULES. Root alone coordinates
hardware. Every attempt gets fresh complete inspection, current user
authorization, the held shared group lock and the full
`kill -> infrasetup -> runworkload -> kill`, followed by owned cleanup and
outside-job capture. Never execute an old run directory or a stale prepared
receipt, use a direct driver, retain an image across runs or bypass a refusal.

Fresh page preparation takes the exact V2 build, seed0/17 gates, acceptance
receipt and optional reviewed memory observer through
`prepare_rvv_transport.py --page-boundaries --acceptance-report ...`.
Fresh pointer-control preparation uses `prepare_zephyr_fit.py` and
`build/zephyr-hart2-vreg-shift64-v1/ready-vreg-cursor-shift64-all-harts.json`.
Both then use the standard `run_prepared.py --execute` path. Raw failed logs,
timeouts, configs, source/tool/ELF/image/driver identities, phase times and
partial regions are retained. A separate repeat attempt was correctly refused
before the first kill when a process started during inspection; it is preserved
at `runs/fpga-rvv-page-transport-repeat-v2` and did not run hardware.

The CPU agent is joining source retirement/late-load behavior to the memory
fabric; the memory agent is qualifying the actual archived FASED pipe without
skipping SerialTL/Bringup boundaries; the Saturn agent is adding qualified
internal protocol/activity tracing. Existing frozen held-outs remain separate
and have not supplied timing data for fitting. No root cause, production fix,
complete functional certification or held-out±2% timing result is claimed.
