# Current isolated continuation

Parent assigned a NEW epoch from frozen778: correct legacy domain metadata;
implement actual source CSR WFI/counter edge policy; then exact Rocket frontend,
IBuf/branch/cache/fetch coupling so all3 cores have source frontend/pipeline.
No primary359/globalboard/CRT/frozenmodel/FireSim edits. No hardware actions.

Frozen778 is build/frontend-live-frozen-778db044; manifest73f9d9eaa6a39e8ab43b3f02879283a2523eb8b453dbfda290a7cf826bab31f9,
6055files/5904objects, verified. Native778db04433e2b8c8a6b29ae9bab20c5c07864f69b0ae6d6d10046d8d118c19fc,
ABI4UARTdb399b6f488ebc60e16143bdd9b63018a8494a76bb852ebe1a793303157d99c5,
overlay1fb9d1657d5feb0b28c1ced6ae94dc9a9d8aec8ad8091ad52f50b5508dfe0da0.
Full13-module Shuttle frontend integrated; actual3hart Zephyr6+9 and strict9ROI
profile,32functional,24legacyexact,control7,IRQ/context allpass. Full2%/RTL/
imagecertificationfalse, externalmissservice unknown(defaultrefusal) or explicit
synthetic3/1 or11/2 fixtures. See FRONTEND_LIVE.md. Don't mutate778 source/build.

New source tree CREATED: pipeline/riscv-isa-sim-source-frontends,729base+exact778
overlay. Only native edit sofar: iris_shuttle_issue.cc domain chooses proper
experimental-source-Shuttle-frontend-RV64IC-ALU-counter-CFI whenenabled.
No new native build launched. Old frontend-live source/build remain untouched.
New owned header pipeline/source_counter_clock.hpp is a first draft, untested.

WFI source proof is frozen build/frontend-wfi-clock-proof-v1/results.json,
SHA2d1abe9ed68828bef039420c4265f03322616b1ecf6ff630685754442b88fc26:
38actualCSRFile/CSRFile_2 transactions. CSR.scala650 increments reg_cycle on
UNGATED edges with pre-edge !csr_stall and old CY inhibit. csr_stall is reg_wfi
or sticky cease(1231–1233). WFI entry counts; parked/wake edges hold; nextedge
resumes. Locallyenabled pending interrupts(read_mip&reg_mie,CSR.scala670) clear
WFI regardlessglobalMIE(1093–1095). Pipeline clock heldlow alone doesn'tstop
mcycle. ShuttleCore62 wires CSR ungated_clock:=clock; RocketCore172gate only
pipeline, ungatedcounterindependent. Native old numeric count_wfi is synthetic.

Critical additional exacthart2gap: RocketCoreParams.haveCease=true(lines58/242),
customIsaExt xrocket(line83); actual elaborated hardware/evidence/firesim-dts.dts92
and board/evidence/firesim-dts.dts92 advertise _xrocket ONLYhart2. Encoding
CustomInstructions.scala10=0x30500073. Shuttle decode table has noCEASE row.
Current359/778 CLIomitsxrocket and noCEASEhandlerwasfound. Do NOT inventillegal
architecturetrap; audit savedRocketdecoder+actualCSRlegality, implementinnewtree
whenqualified or emit explicit modelrefusal. SourceCounterClock draft includes
sticky cease state(IRQ/exceptionclearsWFI butnotcease), notyetnativeconnected.
Parent informed.

Proposed source-counter integration:
- New explicit profile counter_policy source-ungated-stall plus hartidle field
  source; old numeric0/1 remain legacy synthetic. Reject ambiguous mixing.
- Separate SourceCounterClock perhart, explicit resetfalse WFI/cease; sample
  pre-edge localpending before advancing device time; oldstall controls existing
  mcycle.advance_time. CY and explicitwritepriority remain existingcounterowner.
- WFI COM completion setsreg_wfi except same-edge sampled localpending wins.
  Exception clearsWFI. Wakeedge blocksRRD and count; nextedge resumes.
- Tick EVERY sourcecounterhartedge, includingparkedh2, no idleskipping. Add its
  nextedge to globalstep deadlines. Avoid old is_waiting_for_interrupt proxy.
- Sourcependinglinephase must be explicit. Current sim.cc iris_advance_clock
  counts first, then clockeddevices and CLINT. Don't guess external interrupt
  synchronizer delay. Snapshot localpending beforedeviceupdates, defer unknown
  pending-state diagnostics until WFI needs it; existing core.iris_validate_interrupts
  validates CLINT/PLIC knownness. GlobalMIE must not gate WFI wake.
- New sourceMode dispatch onlyatownhartedge and blockwakeedge. Architectural
  Spike in_wfi can clear only aftersourcewakeup; sourcehelper exceptioncapture
  currently restoresin_wfi and must not lose IRQs. Counterread records stay actual
  get_csr/retiredCOM observations, per-root profiler API.
- sourceCounterClock header needs independent actualCSR differential using SAME
  input commands as frozen38proof, not injecting expected readiness/state. Can
  create NEWv2harness addingbusinputfields+hostclass+CEASEcases; leaveoldproofalone.

Other agents:
cache agent spike_finish owns NEW timing/cache_hierarchy* source hierarchy only.
zephyr_port owns timing/saturn_timing* actual source cuts. SDK ready at
build/saturn-timing-sdk-v1/sdk/{saturn_timing.hpp,libiris_saturn_timing.a},
phase evaluate/sample/commit; compute207modules96ports andRocket153modules129ports.
ports.json under build/saturn-timing-source-v1/{compute,rocket}. BothtrueEXcandidate
vs EXfire, MEMkill, S2/COM tokens, replays/late-retire/scalarresponse, allTLbeats
are distinct. Two-state reference scope only, production-knownness uncertified.
User/parent own all FPGA actions. Latest broadmanagedv12 completed6750regions,
cleanup/archive; root handles duplicateidenticalcopiedUARTroleanalysis, no rerun.
Primary359/ABI4 SDK4 nowpublished; oldspikebackup under
build/primary-sdk4-activation-v2/rollback/spike. Our frozen helpers/profiles hold
oldbytes under build/frontend-live-778-publication-input-hold/manifest.json.

## Progress after initial draft

SourceCounterClock class independently matches actualCSR units in NEW
build/source-counter-clock-component-v1/results.json (44transactions, including
stickyCEASE and exception/IRQpriority). Native source policy is implemented in
newtree iris_source_counter_clock.cc +sim clock/adapter hooks, counterreadfinish.
Profile syntax: counter_policy source-ungated-stall; eachhart idle='source'.
Numeric0/1 oldcount_wfi stays legacy synthetic and mixingisrejected. Nextedge
foreachhart addedtoglobalclock; noidleskipping. SourceWFIpreedge seeslocalenabled
pending beforedeviceupdates; sourcewakeclearsSpikewaitingflag immediately but
blocksRRDonwakeedge. Sourcecounterpost-WFIentrypendingwins; exceptionclearsWFI.
CEASE sticky modeledincontroller, buthart2decodedhandler remains a DEFERRED
namedIRIS_UNMODELED_ROCKET_CEASE refusal at execution (not eagerdecode/illegal).

Build/currentprivate: build/spike-source-frontends-v1, builder
pipeline/build_native_source_frontends.py. First0c76 nativepassed all3WFI+timer
and shortpulse,32qualifiedfunctional+24legacybyteidentity; notfrozen. New stricter
hart0CEASEillegal testexposed existing778 conservative-trap duplicateRASredirect:
normalboundary redirect(savedRAS) andtrapredirect(RAS0) conflicted. Newtree fix
runs boundarycompletiononlysuccessfulretire; trapownsitssole RAS0redirect.
Current rebuilt native69e76045546a65ef164ddec7dd1799fc71ee4049469f5b0b3482987607b09f95;
formal pipeline/source_counter_native_check.py oldv1 failedatthat
witness; NEW build/source-counter-native-gates-v2 running session71404. Do not
mutatecurrentbinaryduringgates. Allold0c76rawreceipts preserved.

Prototype positive evidence:
- build/source-counter-native-v1: actual3hartClintsleep6–7ticks whilemcycleadvances
  only22/22/20localcycles; already-pendingMSIPWFI9/9/7cycles. allpass.
- build/source-wake-pulse-v2: hart2parkCOM12834, h0set12911, sourcewake12912,
  h0clear12914, firstRocketID12914 whenMIPalreadyclear. Positive repro for source
  waitingflag clear+wakeedgeRDDhold. Newinitialpulsev1compiletypo preservedfailed.
- pipeline/source_counter_native_check.py formal6runs: WFI all3,pulse,legacy
  syntheticcountWFInegativecontrol,badpolicygrammar,ShuttleCEASEillegal,
  RocketCEASEdeferredmodelrefusal. Depends on sourceCounterGuest/Pulse/CeaseC+S.

Need next: finish formalnewgates, negativephasecontrols ifuseful, fresh32/24 and
Zephyr6/9+profile under sourcecounterpolicy, freeze beforeRocketfrontend epoch.
Then compile actualFrontend.sv+IBuf.sv as exact sourcepeer forhart2. SourceFrontend
ports32-bitfetchdata(two16bitparcels), BTBentry5bits/history8; D64/8beatrefill+
corruptbit; might_request, take_pc req(valid,pc,speculative), progress, BTB/BHT
updates. IBuf gateswithRocketpipelineclock, frontend hasitsownsourceclock; doNOT
collapseclocks. BothCSRungatedclock separatecounterpolicy. RocketCore.scala:
MEMtake_pc659, WBtake_pc793, IDkill1099, frontendredirect1101–1103, BTB1124–1135,
BHT1137–1142, RASupdateDontCare1145, pipelineclockgate1222–1233. Auditbeforecoding.
ActualRocketPMP8entryinputs mustfollow currentstate/knownness; doNOTtieofflocked
PMPs or inferMmodeignoresallPMP. VM/debug unsupportedcanstayexplicitrefusal.

Cache agent SDK frozen build/cache-hierarchy-native-v5/sdk with
sourceID6ffdc95e187a44c0d509ee05017223e272941354bb4872c591345250e4b24575.
L2inner auto_in0..3 pins afterbuffers,64bitdata/source10/address33. Icache MUST
route actualtile/fabric/bankbinder/sourceIDremaps; directsyntheticsource0shortcut
notqualified. L2outer AcquireBlock/GrantData/E beforecork/MBUS/serial, external
service unknown. Agent nowrooturgentofflineFPGAZephyrhart2vectorhangtask; preserve
all frozenSDKsources. No hardware operations byus.

### CEASE correction / current build
Actualexisting execute.cc46–49 alreadydeferred-refusesM-modehart2CEASE via
IRIS_UNSUPPORTED_CORE_INSTRUCTION … halt-until-reset notmodeled. My earlier
processor.cc-onlysearchmissedit; parentcorrected. Removedmy redundantnewdecode
handler(whichwouldhavebroadened refusalintoS-mode). Formal sourceCountergatev2
passedallotherfivecases butexpectedwrongnewdiagnosticforhart2; nowcorrectedto
existingguardprefix. Newbuildstartedafterremoval, sameisolatedbuilddir (development,
notfrozen). Native69e and0c76 raw receipts preserved; upcomingbinaryidentityneeds
reading pipeline-build.json afterbuild. Newformaloutputmustbe v3.

### Current stable new counter candidate (awaiting profile parser)
Native1d521b4a916899db2dc497ee0dc8dd791bd914cc547aded79bf4333a6c7fd245
in build/spike-source-frontends-v1 is nowstable. Formal6 PASS at
build/source-counter-native-gates-v3/results.json;32functional PASS at
build/source-counter-functional32-v2;24legacyexact PASS at source-counter-legacy-v2;
actualZephyr6scalar+9mixed PASS at source-counter-zephyr-{scalar,mixed}-v1.
Root is updatingowned iris_model parser for hart idle='source' and requiring
actualcapturedCSR observations with sourcecounterpolicy. Profile initialoutput
build/source-counter-mixed-profile-v1 failedonly int('source'); noactive profiler.
Root requested native/fixture/mixedgraph/stdout/receipts remainSTABLE untilhis
profile/review closes. Do not modify source_counter_clock.hpp either (nativeinput).

ActualsavedRocket clockgate correction: RocketCoreParams.clockGate defaultsfalse
(RocketCore.scala51); emitted Rocket.sv hasIBuf.clock(clock)1363 andCSR.ungated_clock
(clock)1415; nooptionalrocket_clock_gate/clock_en_reg/gated_clock logic. ICache and
Frontend similarlydirectclock. Earliergenericgatingdiscussionconditionalonly,
notactiveinIris. WFIcounterstop isCSRstall, notphysicalclockgate. Parentinformed.

Rocket passive source unit NEW files rocket_frontend_unit_check.py and
 test_rocket_frontend_unit.cpp, wrapperactualFrontend.sv+IBuf.sv wiring. Failedv1
missedlastuncommaedmoduleportio_inst_0_bits_raw; parsernowlimitedheaderandcaptures
allports. v2compiled butlegitimateIBuf.replay onIcachemiss broke naive sink.
 v3nowusesexplicitSYNTHETIC one-edgebackendreplaycorrection (notactualCPUreplay
latency), consumesonlynonreplayparcels. Tests512mixedRVC/32b, carryacrossfetch32,
8beatline fills+backpressure. Running build/rocket-source-frontend-component-v3,
session4948 (queryresult). PassiveunitdoesnotclaimnativeRocketintegration.
RealRocketfrontendintegrationMUSTtransportreplay token EX->MEM->WB and redirect
atWB; noobservedready/state injection. SourceMEMwrongNPC comparesEXPCelseIBufPC,
notShuttlepredictiontags. RocketJALR link selectedmem_int_wdata at654 (targetEX,
linkMEM; auditbypassreadyforID beforecoding). RocketBTB5bitentry/history8,
noBHTcountervalueport; separateactualschema. PMP8entrydynamicstatusmustnotbetied
offiflocked; MmodeVMdisabled initialinactivePMPonlyinpassiveunit.

### Frozen source-counter successor and current Rocket work (2026-11-06)
Counter successor is FROZEN/verified: build/source-counter-frozen-1d521b4a,
manifest8c8f802e2bebff10893f42a3c9e939e7645b5eb800bd671b9629b858b691e0ad.
Native1d521b4a... /UART914819ff..., overlayecf74b29...,6118files/5947objects.
Minimal source-counters-on-frontend778.patch applies cleanly to unchanged778.
Includes root123-test profiler sources/logs, actual mixed9 profilev2,44actualCSR
transactions,6WFI/wake/negativecases,32functional,24byteidentity,context,Zephyr6/9.
Strict IRQ originalv1 guestpassed butclear13074 followedCOM13073; preservedraw+
witness-failure.json+originalrunner. NEW owned precisionfixture shortens exact
synthetic peer-clear opcode only: v2capture13070,clear13072,COM13073; unchanged
IPI/timer/accessfault/illegalguestgoldensPASS. No hardwarelatency/fitclaim.
Doc pipeline/SOURCE_COUNTERS.md. Oldnumeric count_wfi remains legacy synthetic.

Source WFI code/fixtures/native1d52 are IMMUTABLE now. No stale profiler blocker:
root sourcepolicy parser and actual mixed9 join PASS; allgraphs/helperbytesclosed.

Verilatorcontext successor component PASS build/frontend-owned-contexts-v1:
new pipeline/frontend_rtl_peer_context.cpp and rocket_frontend_rtl_peer.{hpp,cpp}
select owner before constructor/evaluate/commit/internaledge. Exact frozenmodel
archives unchanged. 2Rocketseeds1/17+Shuttle7 standalone vs3varyinginterleave/
constructionorders compare10800physicaloutputrows over14400edges, foreignactive
context beforeeveryphase.4stalecommitguardsPASS. Scopedreset/activeoutputs only;
notproof arbitraryunreset RNG histories commute. No oldwrapper/source edits.

NEW development worktree pipeline/riscv-isa-sim-rocket-source, build
build/spike-rocket-source-v1, builder pipeline/build_native_rocket_source.py.
Base729+exactfrozen1d52overlay. ActualRocketFrontend+IBuf typedpeer, explicit
rocket_frontend saved-rtl-M-mode flag, sharedresetknobs, sourceEX/MEM/WB replays,
sourceMEMnextPC compares actualyoungerEXPC elseIBufPC, sourceBTB/BHT, JALRlinkMEM
bypass andsourceEX-onlyinterlock (RocketCore1041). CSRinterlocksEX+MEM.
Native Rocket MEMcontroldeferreduntilcurrentfrontendprepare; WBredirectpriority.
AllacceptedIcacheDactors remainuncancelled. Missingservice namedrefusal; existing
external servicefixture stays explicitlysynthetic. Hart2 customCSR0x7c1 actual
reset0x208 input; guestaccess explicitlyrefused until nativefunctional CSRexists.
No claim wholevector/FP/VME/memorypaths pipelined; remain conservativeboundaries.

Firstnative0e5a refusedPMPADDRESSWIDTH beforeguest. Rootnotified real cause:
upstreamSpike reset installs PMPCFG0 RWX/NAPOT+allonesPMPADDR0 compatibility,
which differsfromsource CSR reset A=0/L=0 and33-bitaddress. NEW epoch removes
thatfactorycompatibilityinit ONLYinIris mode and usesactual35-bit physicalwidth;
other/sourceunresetPMPRWX/addressknownness stillunqualified, nostateclipping.
SourcecfgPMP8/granularity4 guard plusdynamic8PMPtransport intoactualfrontend.
Rebuild currentlyrunning session18262. Preserve failedfirstcontrolrun
build/rocket-source-control-v1 andoldbinaryreceiptifneeded; builddirdevelopment
notfrozen. Next runtonewoutputv2 afterbuild, then fixactualintegrationbugs, source
branch/control differential andallfunctional/context/IRQ/WFI/Zephyr gates before
newfreeze. No primary359/globalboard/CRT/FireSimfiles touched. Parent soleFPGA
coordinator; no childhardwareactions.

### Final all-three frontend epoch2539 FROZEN (2026-11-06)
CAS snapshot build/rocket-source-frozen-2539e85c is closed:
manifestec79c830575a7909842834d445ec2b85779ea370ece3ae50933edc0242fd73d5,
6399files/6097objects. Native2539e85cfa5defb3835d9f74ea8ed645dd935767e2326d13f6b1017cd9f884c9;
UARTba59d430bfe0c23737828f4a9f13bcb9a0ac66e1c494ef56ab2ab3f9d77173f1;
overlay484a9dc28894bef43d88cacd4db8fafd199d5c51ee6e9aea4209f2e58f3617d5.
Minimaldelta rocket-source-on-counters1d52.patch SHA
dd91b06367866b3d9e5ba8159f8dfb58e77294d9b492dc6c0769bc8573f7698f.
Verification and minimal-patch apply-check both PASS (session20300 complete). Exactpair alsoin
build/rocket-source-2539e85c-candidate forimmutableconsumers. Native/sourceworktree
pipeline/riscv-isa-sim-rocket-source +build/spike-rocket-source-v1 STABLE now;
no edits thereafterfreeze. Docpipeline/ROCKET_SOURCE.md, freezerfreeze_rocket_source.py.

SourceRocketintegration passesactual3hartcontrol7cases (fast/byte-repeat/slow/
seed17/missingservice/wrongreset/zeroseed), source-exact200kMEMcases/2Mchecks,
32unchangedfunctional,24legacyexactgraphs, actualcontext/PMP+capturedIRQcompletion,
all3WFI/wake6cases, liveIRQ/accessfault/illegalgoldens, Zephyr6scalar+9mixed. Final
mixed9capturedCSRprofile PASS build/rocket-source-mixed-profile-v2;summarySHA
ccc0613c3d282d7425f525037c9eda16c4a1ce07ba0574daedc0a68560611981. Snapshot
includesexactprofile/toolmodulebytes andallnativeMMDdependencies/realcompiledRTL.

Integrationbugsclosed: trueIBufready independentvalid (partial32b fetch crossing),
RocketJALRlinkMEM+EX-onlyinterlock, actualEXPCelseIBufNPCcomparison, source3stage
replayWBredirect, WBpriorityoverdeferredMEM, ownedVerilatorcontextperpublicphase,
sourcecustomCSR0x208resetinput/accessrefusal. Newfunctionalpaddrwidth35 andIrisPMP
A/Lreset sourcecorrect; upstreamfactoryall-memorycompatinit preservedonlynonIris.
PMPRWX/addresspoweronknownness remainsUNQUALIFIED; futuredefinednessepochmusttrack
unknownPMPfields/refuseactualobservation ratherthanclaimfullbitexactness. Native
configurationguard8PMP/granularity4, dynamic8PMPinputs, lockedwrites/WARL tests.

LegacyWFInegative initiallyfailedpreparedCOMzero-retire because directRocketpath
restoredSpikewaitingflag afterprobe, thenpreparedfetchskippedordinarypendingwake.
Final2539clearswaitingtransportbeforepreparedRocketissue whenlocallyenabledpending;
sourcecounterpolicy stillclearsatactualsampledwakeandholdsRRDonwakeedge. All6source
countercasesnowPASS. NewfrontendpostwakefirstID canbelaterthanwake+divider; failed
inheritedexact-nextedgecheckerretained, newtestrequiresnolssuewhileparked/wakeand
preservedwakeafterlineclear, recordsactualgap4 withoutfit. Source-wfivisiblecycles
22/22/26 vsCLINT6ticks andalready-pending9/9/11 fornewsourcefrontdomain.

LiveIRQpeerpulsegoldensPASS capture13396,COM13399,clear13404; reportexplicitly
`early_clear_before_COM_witness:false`. No falseclaimoldtemporalwitnesssurvived.
Separate actualnativeCOMhooktesth0/h2 capturesIPI,clearsline,step(1), verifiescause,
mepc/vector+zero-retire. ThisisCPUhooksemanticproof, noactualinterruptcrossingtiming
qualification. IRQtester inputguestgoldens unchanged; syntheticprecisionfixture
remainsnamedstimulus, no measuredpenalty. Hardwarelatency/timing/fullknownness/
fullfunctional/ethanimage/wholeSoC/2%allfalse.

Helpercollisionwasfixed: pipeline/frontend_context_check.py restoredexactoldhash
f96e... fromfrozen1d52 (actualprocessorguards). Newmulti-peercontexttool is
pipeline/frontend_owned_context_check.py, proofbuild/frontend-owned-contexts-v2.
Oldv1proofarchivedthetemporarilycollidingtoolbytes; currentbuilderusesv2proof.
Originalsource/frozenfixturesunchanged. NewRocketactualprocessor+PMPtool is
pipeline/rocket_context_check.py, test_rocket_context.cpp. No primary/globalboard/
CRT/FireSimchanges. Sourcecapturedprofilecurrentcodeunchangedrootowned.

NEXT usefulcausalcoupling: cacheagent froze actualMemoryFabric sourceSDK:
build/memory-fabric-component-v1/report.json (SHA8b2c64b1...); verifiedcompanion
memory-fabric-component-v1-verify/report.json SHAa5a12f40.... Header
 timing/memory_fabric.hpp exposes evaluate(span<Input{value,known}>)->sample()->
commit(ClockEdges{rocket,uncore}), explicitbothdomaincounts. 263externalfields,
730sourcejoins,1046outputs; sourceID6227466fbb9a064a12f322928adb9e9be21ed3a403d5fa5895cb026fd6feeb42.
SDK build/memory-fabric-coupled-native-v4/sdk +exactcontextderivatives
build/memory-fabric-context-sdk-v2/{cache,noc,adapters}/sdk. OriginalRocketIcache
arbiterinput `_frontend_auto_icache_master_out_a_valid/address` exposed, realsource
xbarassignsID; dirtyL1D→IcacheGetcoherence1805checks. ThisavoidsdirectL2/source0
shortcut. OuterMBUS/cork/serial service remainsEXPLICITUNKNOWN. AgentnotifiedIwill
inspectfrozeninterface/read-onlythennewisolatedepoch; requestedactualDreturnnames/
clockconstraints. Do notmutateanycache/SaturnSDKs orprimary. ParentownsallFPGAactions.
