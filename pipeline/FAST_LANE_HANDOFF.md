# Followup — store same-edge annotation fix E244 is frozen

1aa full32 passed but two of five rootOS groups failed the strict CPU squash
annotation guard. This is preserved at build/owned-store-1aa-positive-OS-v1.
Exact diagnostic at build/owned-store-squash-diagnostic-v1 proves node87958488
was already evicted by bounded base87958491 at cycle32501443. The lookup
returned the completed-prefix sentinel, not a real memory actor. The entire
summary and stdout are byte-identical to the original failed run.

NEW build/empirical-owned-store-frozen-e2444578 manifest
 a7959c3ea84c37a6dce5df3eabc0261563b08bc22129022970529a9fdf4b4b71
binds nativee2444578c676dcbc758e219b1a213913353671e9ba397d81799cae282cfe4245
and UART6fb702be0534b10fe8c099815a75db4740d097bf51565ba16c9ac41ebdf8745a;
all2024native/4065inputs reconstruct. The original mark_squashed ownership
and completion guard is unchanged. A separate typed API uses actual successful
cancellable nonphysical CPU completion receipts from the current global cycle
only. It can account for an evicted node without mutating a sentinel; pending,
canceled, memory and older-cycle IDs still refuse. Receipts clear on time
advance. The producer validates owned CPU work before deferring annotation.

Same failing VME4 now exits0 with all four migrating/timer contexts and
hart2producer/refusal goldens (qualification0fedf3dc...); actual annotationcount1,
146.75hostseconds/25.84M retired (~.176MIPS).31unitchecks and three meaningful
mutations pass, including prior-edge EX/source-MEM handling and memory/old
receipt refusals. Directed full/bounded/OFF parity and nine fault controls pass.
Root owns newall5/32 QA. Fitter owns NEW FADD+shape+store composition/fitting;
no old coefficients or full timing qualification transfer.

Cleanfix on1aa: build/store-completion-companion-on-1aa-v1/
completion-receipt-on-1aa.patch SHA
b07ba1cb6228095be0f9e984485a9d5f82f6a51f5aa6a723daa6c1987b163bd3,
report695d27bf...; six native files plus seven exact helpers at
pipeline/store_front_completion_runtime. The parent1aa positiveQAfixture works
unchanged; this binary still has no new scalarFADD/shape flag composition.
The reviewed combined source also needed one missed shorthand pure_decode
call fixed: (...vector_fadd,scalar_fadd,stores), not (...vector_fadd,true).

Earlier lane records follow.

# Latest lane checkpoint — 2026-11-07 00:30 UTC / Nov6 16:30 PST

Parent/root remains sole hardware coordinator and release owner. Full goal,
source/image association, heldout2% and speed acceptance remain incomplete.
Do not mutate any frozen source, native, fixture, board/CRT or activehardware
input. The final working selected package remains root-owned; read
CURRENT_STATUS.md before choosing any release artifact.

Optional owned scalar stores are frozen at
build/empirical-owned-store-frozen-1aa8ca00, manifestb764e72dd5dd7441b012af8e0430db402aa399ca0d05783a6482fc1250710fee;
native1aa8ca009f0c4c7b54ebe8dd31ede47fab4151e40658ed78ee70a31707c9d903,
UART8e4457812b3279072a03377f6301357f4a19d4fc02e0fbb2f53d184981cd4259.
It is a defaultOFF successor of523, NOT a525/shape-enabled build. Directive
`empirical_store_front owned-dirty-L1-COM-v1` admits finite aligned M-mode
SB/SH/SW/SD/RVC on V6 approximate dirty-private DRAM tags. Typed effects occur
once at COM, or on a retained noncancellable response after ownership loss or
positive configured service. Younger CPU work is annulled; accepted memory
actors survive. Cache/family priority, shared fractional accumulators and
configured issue intervals are honored. The only private-runtime addition is
completion-owned payload publication; all523 scheduling source bytes match.

Consolidated proof build/owned-store-publication-proof-v1/report.json SHA
3d43e242d856c22771e22aa37065127ce753884678de79ecca729b18ab9fef27
binds2024native/4053inputs, allwidths/fourRVCforms/opaquebytes, peer-before/
afterCOM, all3 pendingIRQ, nine recoverable storefaults, three unknown-address
refusals and three wrongpath non-observations. Full/bounded traces and OFF523
bytes match. Synthetic fractional/II/priority and20,013runtime checks pass.
Own1008 numerical baseline passes15.94s under explicit postROIdebugger stop;
actual finite fullELF checks achieve.146-.151MIPS. Full32/fiveOS finalepoch,
new calibration and physical coherence/PMP/translated-path qualification are
still false. Clean523 delta is
build/owned-store-companion-on-523-v1/owned-store-on-523.patch SHA
72be305d86e5a34f542591d8e21155903b7b83c3c111531b3ad1f3ac42d3dc8f.
Fitter owns NEW FADD+shape+store composition, currently under independent
hook review; never copy mutable source without coordination.

Tiny VMEwork-only525 is frozen separately (manifestecfae957...): optional
`empirical_vme_work source-shape-subtiles-v1` makes zero work activeM/N16x16
subtiles, empty0; MMunchanged. Own1008 baseline/all10240directedcells pass.
Root525realMerlin scalar twins refuse strict unreset RAS at0x80000598. This
is preserved, not seeded/fixed. Diagnostic capsule
build/merlin-RAS-diagnostic-frozen-eda658b8 manifest6a995520... reconstructs
2023native/3950inputs. Acontinuous1,300,498edge savedfrontend RTL replay
matches38,463,800outputs and independently observes unwrittenRAShead3.
This uses nativeCPU physical controls, NOT an independent wholeCPU run.
Boundary report build/merlin-RAS-source-boundary-v1/report.json SHA
6b211edb3c9ddd78dfa1a3a6f7ed234b1a73920f2b5f23350d5b0ad5c753c50c
binds actual480synthesizedRASFDREINIT0bits/Qnets/hierarchy, actualbitfe3e and
implementation logs. ALLimplementationDCP EDIF uses unsupportedXlxV18EB;
onlyVivadoLab was found locally/remotely. No routed preservation, logical
encoding or bitstream RAS initialization is inferred. Keep the unknown guard.

Earlier checkpoints below are historical.

# Fast native lane checkpoint (2026-11-06)

Latest (23:11 UTC): final candidate523 combines cdee Rocket replay fix with
the sibling's source-owned trap RAS metadata and no-spurious-trap correction.
Frozen `build/empirical-rocket-RAS-frozen-52314001`, native
`52314001a8697ecf10caf93468b9dbdd351f2d5b92df911cec7d04eed5394773`, UART
`fd96047017209889d97e0cccfb7f964005bdaef7029f4c6128d46f1842051d96`,
manifest `2109308bfca85b8a052aef712a87fb334cc45bcf301dc3217a94031a6f2fc184`.
Actual NEW1008 compute corpus completed all independent goldens/CSR joins in
16.74s BEFORE fresh reference timing, immutable raw prediction archived in
the capsule. Root full32 PASSd2327464... and all5 positive-cost realOS groups
PASS1080f7f6... (23.66/119.86/132.75/137.60/155.13hostseconds percase).
No new native/helper changes are planned. Root/fitter own finalcost selection,
actual FPGA labels and finalprovider; fullcert/heldout2pct remainfalse.

Exact RAS correction: sourceaccepted COM/exception parcel's ras_head now
travels into queue_trap; currentqueue/zero defaults are not substituted.
First boot MSIP traps as well as runtime IPIs previously lost that metadata.
A source issuearm merely schedules/waits, so its empty boundary retry must
not call queue_trap without ever synchronously stepping the processor. The
sourceRAS array reset/knownness/prediction policy is unchanged. Genuine
unwritten required entries remain strict refusals. Original901/cdee failures
are preserved. Sibling owns broadmemory-return checkpoint proof.

Source523 IRQ temporal coverage: old4 per-case async tests now all exit0 and
their values/owner ledgers pass, but oldphaseaggregate correctly refused
because its timerphase missed TWO simultaneous owners. Preserve that failure.
NEW `build/empirical-rocket-RAS-scalar-IRQ-phase-v2/report.json` SHA
`25629a4237b6978d62fa10aa9da1bac4fc93c969a026cebb63f21c6f6b3c5ede`
closesactual all3two-owner timer coverage using explicitNOPphases0..8,
fixedphysical500kHzRTC andsynthetic3cycleinteger backend. Everyjob checks
all3 values4099/IRQ1, priorCOM/publication before successorEX, and complete
begin/publication/cancellation ownership. No native policy/guard weakening.
An earlier RTCdivider1 test was correctly refused by physicaltimebase guard;
it is preserved as a failed stimulus, not enabled as a workaround.
All18FADD/sourcecontext guards pass. Actual523 CPU2304/4608CSRjoins pass10.63s,
same development accuracy as cdee (all128warmRocketwide<.52%; all512warm
Shuttlewithin2; coldshort errors retained). Full/bounded K1 prefix/packet/
guestcounter byteparity passesdab62699..., with actualsampled4/unissuedfinalD.

Current owned private source is `pipeline/riscv-isa-sim-empirical-rocket-ras`;
its builder is build/spike-empirical-rocket-ras-v1. Keep it stable while
root/fitter consume the frozen pair. Companion to901 is generated under
`build/rocket-RAS-companion-on-901-v1`; no primary/board/CRT/FireSim changes.
Earlier entries below preserve exact historical epochs.

Latest (22:54 UTC): Rocket packet epoch cdee is frozen and under root's full32
and five-positive-cost-OS QA. Exact pair:
`build/empirical-rocket-packets-frozen-cdeeca09`, native
`cdeeca09924c14ee77aa3ef39f28ceda02555fbe699062fdb13affde5afeecb7`, UART
`9c36f387d54bd6c06ecf2202d963736628eb93e75747c525423e01a0fbb6c155`,
manifest `73e0fa43421413b15c107cf0f519cde4024210f8702bb136a074803b7592bd68`.
Source reconstruction verifies all2023 native files. Do not mutate it. Current
owned private source is `pipeline/riscv-isa-sim-empirical-rocket-packet-repairs`;
its diagnostic build directory contains the same final pair, but consumers
must use the frozen copy. Exact901 companion is
`build/rocket-packet-companion-on-901-v1`, report8345448b..., patch66a9f32d...,
11native files and5 external helpers; every target native file reconstructs.

New opt-in is `empirical_rocket_packets source-IBuf-demand-4B-v1`. Runtime
four-byte word delivery through exact source IBuf fixes warm-wide Rocket
development rows without PC-cycle rules:128/128 within2%, medianAbs.259%,
p90.516%, versus901's64/128. All512 long-warm Shuttle development rows remain
exact. All2304 numeric/instret/PC rows and4608CSR joins passed on firstc67;
cdee only adds the actual load-replay redirect and diagnostics. Cold/short
errors remain and fullRocketBTB/RAS/front-end translation is not claimed.
Component closure: `build/fast-rocket-ibuf-component-v1` a592782c...,
300kcontinuous RTL edges/6.3M output checks/exhaustiveRVC/3mutation rejects.
Producer proof `build/fast-rocket-packet-flow-proof-v1` bdadddba...,
64literalELF streams/229376physical+owner checks/65guards perhostbuild,
17refusals/two realcorruption rejects. See FAST_ROCKET_PACKETS.md.

Preserve firstc67 failures: all32off pass, K1pass, but4/5 positiveOS groups
refuse strict Rocket head mismatch. NEW readonly diagnosis proves scalar
case: LW0x8000796c accepted281657; ANDI796e accepted281658, actual coherence
fallback281659 annuls that younger row/restarts796e; IBuf had already advanced
to7970 and guards at281695. Newcdee redirects only speculative IBuf on the
actual load fallback; it does not repeat/cancel the accepted load. Regression
proof `build/rocket-packet-replay-repair-proof-v1/report.json` de9265b4...:
exact negative parcel sequence and same-case1M-instruction-cap control
progresses2.438Mcycles/999974 retired, correct796e refetch281695, no repeated
load, stderr0. Cap is not fullOS exit. Root owns all5 realOS rechecks.

c67 source-Shuttle+Rocket18 FADD guards pass; explicit legacy-Shuttle+Rocket
22FADD/two-owner guards pass. A source-Shuttle longintegerIRQ witness refuses
unknownRAS at0x80000448/head0. Source901 broadpriority also refuses0x80007ee0.
Zephyr sibling independently owns the proved trapRAS-head transport bug and
new narrow fix; no RAS value/initialization fallback is permitted. Its pending
delta should compose with cdee (ours changes no queue_trap signature).
Source fetch observer v2 is included: actual K1 bounded/full guestcounter,
prefix and packettrace bytes exactly match, parity report19cbb8c...;
185active sourcefetch observations inCPUcorpus. No older-end/off-edge held-D
phase witness exists, so that phase remains unqualified.

Root has working selected28 fit/package separately and an actual3633row
selected replay (CVmedianAbs6.11%, p9048.58%, fullclaimfalse). Do not transfer
those coefficients to source901/Rocket without explicit newbinding/replay.
Globalv6 heldout hardware timing remains unopened. Fitter owns cacheV6
owned_store_hit helper and residual memory-store floor audit; no native
storefront changes have been assigned to this lane yet.

Host-only cc94 optimization is frozen at build/empirical-optimized-frozen-cc94f9c2,
nativecc94f9c2aff0279de6858616e4d146590670b25531e1e085fc403fa06942b432;
memoized pure decode, cached device RTTI and onepass hazards; sim.hABI unchanged.
Exact temporal/numeric parity, all32/all5OS passed; ~1.2x measured host speedup.
Source901 already incorporates it. Earlier entries below are historical.

Parent /root owns all hardware, provider/release, profiler and global goal. No child hardware access. Deadline is Nov6 20:00PST/Nov7 04:00UTC. Full timing/source/image certification remains false. Global primary359 unchanged.

Active mutable source: pipeline/riscv-isa-sim-empirical-fast; build build/spike-empirical-fast-v1; builder pipeline/build_native_empirical.py. All publications are frozen separate directories; never mutate snapshots.

Latest critical CPU fixes: native0577556054038578e867c9b2902eae87dc15c71a4adf989b4a919544d34b888a +UART92f6168dadd84d18628e04281abd83d134efe022a3db2aae331673b0be6c5b03, frozen build/empirical-fast-frozen-05775560 (see manifest/verification). It adds a next-own-core-edge retry ONLY for a runnable, unblocked, non-stalled pure cohort with boundary=true, zero packets and last_attempt==current edge. No global per-cycle clock or changed WFI/counter policy. Exact prior OFF-mixed9 failure now exits0/all9 independent goldens in17.09s: build/empirical-boundary-retry-mixed-v1. It also marks pending speculative CPU-exception COM/WB cancellable in empirical mode, matching other CPU stages; strict memory cancellation guard unchanged. Narrow12smoke/3RVV/time-sensitivity, async/IRQ and CPU-vs-memory cancellation guards pass. Original6750 post-fix regression and fresh fullOS QA still required.

Actual failure evidence: build/empirical-old6750-cancel-diagnostic-proof-v1/report.json SHAec2ca7d75966588cd45c641ba28b70447ffdbfbae0ab933faa6da728ac9538a7 proves71 pre-failure CSR dictionaries exactly identical across9b/8f/0153. Concrete node132139440 name latched-RRD-exception.COM resource shuttle1.COM hart1 PC80000bfa issued0/completed0 reason source-MEM-mispredict. Missing profile_.empirical in iris_shuttle_issue.cc pure_exception was the culprit. My initial attribution to a load actor was wrong; retained-load lifetime fix is separate.

Calendar proof: build/empirical-mixed-premax-diagnostic-0153-v1/mixed9/stderr. At6586875 h2 runnable PC800089a4, WFI0 blocked0 pure1 boundary1 packets0 last_attempt6586875 recovery0 fetch0 stalled0 blocks_rrd0. All timedwork drained; next timer805306370126000. Thus one-per-edge RRD guard needed a next-edge retry. All old failures preserved, no max-bound increase.

Intermediate frozen epochs: 131c604e (compressed-store feature fix; nonzeroIcache livelock),54ab5d74 (V5 private-Ihit/touch fixes crossline ownership livelock),82307696 (vector memory directL2 bypass; source geometry),9b984bbb (asyncv2 two-owner+hotL1front+carry-in metadata; actual6750/OS failures),8f68cc7a (retained accepted-load owner +FENCE drain, did NOT fix actual6750 failure),diagnostic015320bd (pre-limit state and throwing-node diagnostics). All snapshots verified; history not overwritten.

Modes: baseline fixture build/empirical-next-queue2-first-v1/baseline.fixture enables sourcecounter, async integer-vme-nonmemory-v2, hotL1front, Icache tags and NO costs. mechanics-costed.fixture reuses131c coefficients only for mechanism QA, NOT new calibration. Parent/fitter select new fitted binding. Sourcecuts never evaluated in empirical path.

Source frontend ownership was transferred to /root/zephyr_port. They own pipeline/fast_shuttle_predictor.* /test_fast_shuttle_predictor.cpp, fast_source_rvc_table.hpp/dump_fast_rvc_table.cpp and NEW fast_source_frontend* plus a separate private source tree pipeline/riscv-isa-sim-empirical-frontend derived from0153. Do not edit their files. They closed primitives at build/fast-frontend-primitives-v2/report.json SHAa561092a...:600k sourceBTB edges, ~2.04M checks,5 model mutation rejects; RVC262144 generator+262144 helper checks. Runtime plainC++, noRTL. They must receive the057 retry/exception delta before combined native publication.

Frozen source frontend oracle: build/frontend-alignment-source-proof-v1/report.json SHA080708132aec71f71354c12ffdccf4ebd5126e7b9aa28ab42bbf9cfd151597af,38cases with observer-byteidentity; source cold468 loop132mispredicts/64duplicateBTBclears/steady4cycles vs712 loop10/0/2cycles. New FPGA warmcompact offsets2cycles shows history matters, so noPC/modulo timing penalty. Files frontend_alignment_oracle* are frozen; do not edit.

Fitter /root/spike_finish owns calibration and empirical_cache_v1..v5 (V5 source frozen). Actual new buffered4050-region ELF/reference campaign is root-owned; old6750 timings cannot label newELF. Fitter has replayed old6750 failures and will own post057 capped regression. Globalv6 heldout timing remains unopened.

Required followup: send057 identities to parent/fitter/Zephyr; root runs fiveOS in parallel and full32; fitter replays exact old6750 past33-row failure with48M cap and compares old prefix. Keep results partial if capped. Then improve fast FP timing only after functional bugs close; all dtype functional guards stay strict. Never claim2% or full-model speed acceptance.

Finite FADD successor (frozen after057 closure): build/empirical-fast-frozen-28a0a52b native28a0a52ba04ca05aec01b1c1a9ca86becbd47336d4eec112873695cdb7ea6c50/UART92f6168d..., manifestd867b65fb51b3b37fc22892684f0a51230a70b94cb1363e72550f9c54c1abb92, independentverification75398682fcfba28bd8f9a9920e07a8851672291abaecddbaac13f89a10189ff1 (3879files/2017native). New optin empirical_async integer-vme-fadd-nonmemory-v3; zero-cost baseline build/empirical-fadd-first-v1/base.fixture. OnlyM-mode vfadd.vv withvalidconfig/vstart0/FS; exactlystaged VRF+bitknownness,fflags+knownmask,FS snapshot/restore and publication after COM+positive backend completion. FCSR/config/scalarFP/IRQ drain conservatively; work is computeDLEN128beats versusRocketVLelements, separate rvv.fadd.fp8/fp16/bf16/fp32/fp64 families. No oldFPcoeftransfer and baseline duration remains unfitted work proxy.18directed tests PASS at build/empirical-fadd-async-proof-v3/report.json SHA1b37b6417103e183909fee59aee7288c48203cb0fde30601e5e58356d603394a: IEEE sourceflags/FS, unknownflag0→raisedknown1/16 overdependentFADD and3fatalunknownconsumers, all3 pendingtimerIRQ+sharedscalarFP drain,16-optrueRAWchain, FP8E4/E5+BF16all5RMs. Existingv2 package/IRQ tests also PASS. Six-file exactdelta057→28a0 at build/empirical-fadd-companion-v1/fadd-on-057.patch SHA62445a5ec43f3f99366aecf9c372a5dc4c64ead1f95581194fb3a265a37251d1. Companion997841c6... preserves actualhostelapsed/retiredMIPS (0.116–0.184). Root owns freshwholeOS/full32; fitter recommends new28a0 actualfeaturebaseline while preserving057control. Bothflags/nonFPfallback behavior remain explicitly scoped, no timingcert.

057 actual regressions nowclosed: root full32 andALL5 positivecostOS pass, no boundincrease (OS103.54/18.70/145.63/177.77/264.68s). Fitter old6750 cappedcontrol passes beyondoriginal30.924Mexceptionfailure to33.295M; all71priorCSRprefixdicts EXACT, IPI8 all3 goldens,39validrows/stderr0. Explicit48Mcap isnotfullguestcompletion. Proof build/empirical-old6750-exception-fix-proof-v1/report.json SHAebb04f4d63089aeb21824bf5e318b265e4475bc101bac686ea14001e09692f56.
