This successor emits results after each footprint/trial group. The fourteen
windows inside a group (seven hart masks, two passes each) contain no console
output. All three harts reach a barrier after the group, hart0 emits its24
buffered records and a group frontier, then all three continue. Fifteen groups
produce360 records. UART and its code/data traffic can affect the next group's
cache history, so this is a new ELF/reference and earlier timing is inapplicable.

Source: benchmarks/memory_footprints_mtime_groups_v7. The105 semantic cohorts,
three private DRAM windows, exact16-byte dependent-LD loop,80-byte persistent
records, file-backed UINT64_MAX completion sentinel, and CLINT sampling scope
remain explicit. mtime brackets the raw mcycle ROI and includes sampling
overhead. A500kHz timestamp quantizes global alignment to1000 source core
cycles per tick; equal short windows are valid. No overhead subtraction,
physical DRAM miss/traffic claim, or global2% claim follows.

ELF3e0d9747576916f61406266357224e202cfae8af575e60a5a61984a996a87333.
Reviewed ready: build/memory-footprints-mtime-groups-reviewed-v8/ready.json,
SHAe71d8b0e1cf1bd515d69ff685c6d98c6328ac8de3801fdb56262df7ae4c2d30b.
Thev7/v8 labels identify this footprint lineage, not protected Zephyrv6 data.
Seeds0/17 pass all360 records and15 frontiers. An actual omitted kernel fails
all360 regions and exits nonzero. Qualification retains25 typed/data controls,
45 complete bijection checks,8 compiled-table/layout corruptions and the exact
CLINT-load/CSR/call ordering proof. Managed helpers add10 admission controls;
15 additional controls qualify partial-group extraction.

Prepared root-owned job: runs/fpga-memory-footprints-mtime-v2-001. It uses the
original8f driver, TSI128, reviewed read-onlyFASED observer, user grantv4,
1200-second foreground wall watchdog and1380-second phase bounds, with no
unsafe target-cycle limit. Only the coordinator can launch after complete
fresh ownership/idle inspection and shared lock, using all four managed phases
and owned cleanup/capture. Previous footprint sources/jobs remain preserved.

Postcapture: python3 firesim/analyze_memory_footprints_mtime_groups.py JOB
--output FRESH_ANALYSIS. Full success still requires all360 records and normal
DONE. On a failed run the new analyzer can retain only complete24-record groups
as a qualified source-case prefix, with normal success and calibration usability
false. It preserves raw UART/ELF and never turns an incomplete batch into a pass.
