Current prepared fitting batch: runs/fpga-memory-footprints-mtime-v1-001.
ActualELF072aa7b6f5d073b5d8ac8c8493a7b53b5b6951e0ea6eb7602943a29660c67e9c.
Reviewedready build/memory-footprints-mtime-reviewed-v6/ready.json
df680b313af34ae970f8df18f75d661299bae1e37b925d7f063a298bd1d86b7a.
This memorypacket's reviewversion is unrelated to Zephyr's globalheldoutv6.
No globalheldout reference timings were accessed or used.

Original105cohorts, all7nonemptyhartmasks,3trials,2passes and footprintprotocol
remain unchanged. Sizes2KiB,16KiB,128KiB,1MiB,4MiB. All3harts initialize private
windows at0x90000000/0x92000000/0x94000000 oncepersize/trial, then execute masks1..7
with two ordered traversals each. No cacheflush. Preparation, earlierpasses and
earliermasks affect cachehistory; firstpass is not assertedcold. The64Bnode
footprint is addressgeometry. RequestedLDbytes=8*N, not physicalmemorytraffic.
No actualL1/L2/DRAMhit/miss attribution follows from footprint size alone.

Each activehart samples actualCLINTmtime MMIO0x0200bff8 before its beginmcycle
read and after its endmcycle read. New80B recordlayout:
case_index,pass,hart,start,end,instret,checksum,expected,mtime_before,mtime_after.
The exact16B dependentLD/decrement/BNE/RET function is retained. The compiler
instruction witness checks beforemtimeLD80000640 <beginCSR80000646 <call8000066c
<endCSR80000678 <aftermtimeLD80000682. This proves actualinstructionordering,
not RTLcyclephase fidelity. The newcode/layout means a NEW hardware reference;
oldv3/v4 counterlabels must never be transferred.

Wirefields: mtime_before,mtime_after,mtime_hz=500000,
source_core_cycles_per_mtime_tick=1000,
mtime_scope="encloses_CSR_ROI_with_sampling_overhead",
mtime_quantization_error_bound_core_cycles=1000.
The globaltime interval includes sampling overhead outside the rawCSRROI.
No overhead is subtracted. Equal timestamps are accepted for sub-tickintervals.
The quantized sourcecycle duration is delta_mtime*1000 with strictlylessthan
one-tick (1000cycle) endpointquantization error in eitherdirection. This is not
a +/-2% globaltime guarantee, exactkernel duration, or wholeprogramendtoend.
Raw mcycle/minstret are retained separately; inactiveWFI may gatehartcounters.

The105cohorts are flattened into210 declared hostcases named originalcase.pass0
and .pass1, retaining independentperhartpointergoldens. Guestterminal cases105
means cohorts; hostcase count210 means passes. Both contain360 measuredrows.
The pointer permutation is bijective; afterN dependentloads it returns the
initialnode. All3preparewindows are disjoint and avoideveryELFPT_LOAD extent.
IndependentELFproof checksactual105x24Bcompiledtable/order/IDs/N/masks/trials,
16Bkernel,360x80BrecordABI, count/sentinelobjects and filebackedUINT64_MAX sentinel.

Functional359seed0/17 passall360 in3.97/3.52hostseconds. Actualomittedkernel
control failsall360 and exitsnonzero.25parsercontrols include typedCLINTfields,
reversedtimestamps, sourceHz/ratio/scope/quantizationcorruptions; an equal-subtick
parsercontrol passes.45bijections/758304indices remainproved.8compiledtable/
layoutmutants and10managedadmission/archiverole controls reject corruptions.
This is fitting-only/globalheldoutfalse, with no source/imageattestation or
physicaltraffic/accuracy certification.

Lineage: frozenv3 originalCSRonlyc08ELF and originalbenchmark sources unchanged;
reviewedv4 was metadata-only and neverprepared. Newbenchmarks/
memory_footprints_mtime_v5 owns newsource/ELF/globaltime records. Reviewed-v6 adds
independenttable/layout proof without changing that newv5ELF. Only the newmtime
preparedjob is current for this globaltime collection.

Rootalone launches through completefreshownership/idleinspection/sharedlock and
kill->infrasetup->runworkload->kill, ownedcleanup and quiescentarchive. Prepared
with actualstandingauthorizationv4, original8fdriver, TSI128,1200sguestforeground
wallwatchdog/1380sphase bound and reviewedread-onlyFASED observation. No target
maxcycles, because the loadercanexceed5billioncycles and the olddriveratoi32
option is unsafe. Allsource/helper/jobinputs are frozen through capture.

Postcapture:
python3 firesim/analyze_memory_footprints_mtime.py \
  runs/fpga-memory-footprints-mtime-v1-001 \
  --output build/fpga-memory-footprints-mtime-v1-001-analysis

The analyzer checks exactarchivedbytes/ELF/table/layout/globaltimeorder,
210flattenedcases/360typedROIs, rawCSR+CLINT windows, actualnumericalchecks and
allfourmanagedphases/cleanup. It reports rawfields and quantizedglobalwindows
without fabricating cachemisses, subtracting overhead or claiming2% accuracy.
