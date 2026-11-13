The new controlled pair is build/phase-watch-byte-pair-v1. The two ELFs differ
at exactly fileoffset55624/address0x8000d808, the1-byte retained
iris_diag_watchdog_enabled symbol. It occupies allocated, file-backed,
NONEXECUTABLE data. Enabled=1; disabled=0. Every other filebyte, instruction and
ELFsymbol/instruction address is identical. This is a single compiled ELF with
a data-byte derivative, not separate compilations that happen to look alike.

Both variants keep the same two phases, original compute worker/thread/stack
reuse and FP ownership API, actual compiled MLIR/descriptor objects, generated
VME/scalar-twin kernels, quantization, poison stores and goldens. Hart0 computes,
hart2 is the original RVV producer; only the watchdog's creation and finaljoin
are conditional on the byte. Its static object and stack still occupy the same
addresses in both ELFs. Main may schedule differently when the watcher exists;
that scheduling/context effect is the intended control.

All four359functional positives (enabled/disabled × seeds0/17) pass32regions,
30jobs,122880INT32 and122880W8A8 embeddedword checks plus independent host whole
outputhashes. The separately compiled forced-stall control reachesphase1stage1.
With its watcher enabled it prints the last three mailboxes and exitsHTIF1.
With its watcher disabled it emits no targettimeout/normalcompletion within a
five-second owned host bound. This proves bounded control behavior; it is not
an infinite-stall claim. Forced negative ELFs are excluded from hardwareadmission.

Ready: build/phase-watch-byte-pair-v1/ready.json
SHA256 8b4d35f5d8137729b205de1a7678fb19bee8b8572d6a77a43cddd2d4d2e4227f.
EnabledELF58280c6159245bac12cebbe1f0caa664ef7dd2d6e55502b86d4509a4cab5d444.
DisabledELFee034bfcd6f20e1bb6dabf7e0f4c647da67d51609ec3cce44c54ce2d9193961a.

Prepared coordinator-owned jobs:
runs/fpga-phase-watch-byte-enabled-v1-001
runs/fpga-phase-watch-byte-disabled-v1-001
Both use actualstandingauthorizationv4, original8fdriver, TSI128,600sforeground
wallwatchdog/780sphase bound, read-onlyFASED observer, and no targetmaxcycles.
Preparation and independentverification from/tmp pass. No hardware action was
performed by this author. Rootalone must recheck complete actualownership and
idleinspection, holdsharedlock, and execute kill->infrasetup->runworkload->kill
with ownedcleanup+quiescentarchive. Never mutate the frozenjobs between runs.

Analyze each captured job with firesim/analyze_phase_watch_pair.py. It verifies
the actualarchived flagbyte and variant policy, source identities, typed
numerical output/normalcompletion or separately bounded targetnonprogress.
A disabledwatcher cannot emit a targetwatchtimeout. A hostwalltimeout is not a
successful normal workload or proof of a rootcause. Passing these controls
cannot establish a fix for the originalv6stall: the original remains distinct,
and staging instrumentation/newlayout remain in BOTH control ELFs. No v6timing
labels were consumed or used for tuning. Neither pair is a timingholdout or
calibration input, and source/image association remains unverified.

Plan for a later full8phase diagnostic (NOT BUILT):
1. First compare both controlledhardware outcomes and retain any exactstage
   frontier. If watchpresence changes the outcome, it isolates that perturbation
   under this fixedlayout; repeat/control evidence still cannot identify the
   hardware/softwarecause without an architectural or acceptedoperation witness.
2. Expand stage ownership before expanding phases: mainchannel0, worker0channel1,
   worker1channel2, producerchannel3. The currenttwo-phase workerchannel must NOT
   be shared by two writers. Keep atomic64-bit source-stamped records and
   explicit unwrittenzero states; never guess a missingPC or unitowner.
3. A two-worker phase has no unusedhart1. Start the full8phase diagnostic with
   watcherdisabled and the ownedhostbound. An optionalwatcher-enabled variant
   must explicitly describe contention/preemption on an occupiedCPU and use the
   same one-byte ELFproof; no claim of an unperturbed watchdog is appropriate.
4. Reuse all original compiled GEMM/convolution objects, shapes, poison/golden
   checks, work/started/completed/finished accounting, joins and FPcontext APIs.
   Do not silently add floatdisable, freshworkerobjects/stacks, fences or integer
   quantization as a proposed fix. Such controls need independent newidentities.
5. Require fresh all8phase numerical checks at seeds0/17, actualwatcher policy
   positives/negatives and source/ELFproof before newhardwareadmission. Preserve
   originalfailedv6 and its predictions; no timing transfer/fitting follows.
