# Rocket four-load capacity probe

This is a bounded source-unit experiment, using the unchanged saved
`SaturnRocketUnit` model objects. Four actual unmasked `vle8.v` commands run
through the external scalar EX→WB vector interface with VL and LMUL matching
four restore-sized groups. A real reset and32-edge VRF scrub precede them.

The external fixture accepts actual ATL requests, withholds every D response,
holds the reached occupancy for512 further source edges, then supplies ordered
matching four-beat64-bit responses for each32-byte Get. TLB service is an
explicit one-cycle identity mapping into the aligned DRAM test image. These
are synthetic external conditions, with no physical memory-latency claim.
No queue state, tag, readiness or reservation is written into the unit.

|Control, seeds0/17|Four load bytes|Peak reserved/outstanding|Reader counter at peak|D beats|Drain edge|
|---|---:|---:|---:|---:|---:|
|LMUL4|512|16|16|64|597|
|LMUL8|1024|32|0|128|677|

At LMUL8 the actual five-bit reader counter wraps to zero. The actual backend
busy signal remains asserted throughout the512-edge no-response hold, as does
the source RocketCore vector-CSR stall predicate derived from
`backend_busy || trap_check_busy`. All four loads retire through WB before the
hold; there are no WB replays, lost outstanding source IDs or early backend
idle events. After release, all256 physical VRF words match independent address
bytes. LMUL4 provides the smaller occupancy control.

The cut does not contain the scalar RocketCore, so it does not execute a scalar
CSR instruction. The derived CSR gate is labelled as such and bound to the
actual saved Rocket.sv stall equation. The source Xbar maps the reader's five
internal tag bits to external sources32–63; that mapping is explicitly cited.
An early v1 harness assumption about that prefix failed and is preserved.

An independent transcript reader reconstructs EX/WB ownership, accepted A/D
source lifetimes, all D bytes, held physical busy/counter/reservation signals
and post-edge drain. Across four cases it checks2,048 held edges and1,024 VRF
words. Seven deliberate corruptions are rejected: wrong/unowned source,
wrong D data, wrong VRF data, WB PC, premature idle and capacity counter.

The final raw probe is `build/saturn-timing-load-burst-v3/report.json` and the
reader is `build/saturn-timing-load-burst-reader-v1/report.json`. A frozen capsule
binds both to the immutable full Saturn reference:

```sh
python3 timing/saturn_timing_load_burst_package.py --verify
```

This finite experiment bounds the counter-wrap/premature-idle hypothesis for
this configured source unit. It does not reproduce or diagnose the physical
FPGA timeout, simulate the whole memory fabric, test interrupt-time restore,
or establish additional-request admission beyond these four loads. No FPGA
contact, primary source or shared-engine changes occur.
