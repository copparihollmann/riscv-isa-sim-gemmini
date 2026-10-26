# Original private writeback and read-allocation publications

The native cache walk can observe two writes to one LLC slot in one original
CPU request: a dirty private victim is written back, then the incoming lower
read allocation reuses that slot under the selected stepped LFSR policy. These
are different publications. The old residual parent held both writes until all
children returned, causing a child to wait on its own enclosing completion.

Snapshot revision5 captures the actual private writeback address,64-byte span,
position before the lower child, and original write values. Its service,
bandwidth and traffic remain included once in the existing parent residual
bound. Its writes are removed from the late private-fill/CPU destination set.
The provider binds both owners at admission, publishes the captured writeback
only when that original parent prefix finishes, and gates the child on that
publication. Private fill and CPU destination publication still await every
original child; the CPU receives one completion. No queue, MSHR, credit, lookup,
DRAM transaction or service price is added or removed.

The admitted extension is one observed private writeback before one original
CPU allocation, with disjoint early and late parent values. Multiple writeback
phases, a different phase position, or early/late parent overlap remain
UNKNOWN. The old untagged child/late-parent alias guard remains. Native and
provider must use revision5 together; revision4 is rejected.

This is an ownership and phase correction. The existing aggregate CPU private
writeback service remains provisional: this change does not claim a new
source-closed voluntary ReleaseData beat/ReleaseAck controller. The source
ordering is retained from the original native private-victim writeback before
its incoming lower read (Rocket DCache.scala dirty victim and release state
logic, especially601–605 and808–912); no benchmark-derived latency is inserted.

Focused tests:

- `test_write_transaction.cpp::parent_phase_checks`:115 scalar stores using
  the selected8-way stepped LFSR law reproduce LLC-slot reuse with separately
  captured original prefix and late writes.
- `posted_full_raw_readout_test.cpp`: captured slot publication at original
  prefix-ready, child/final publication later, one CPU completion, and refusal
  of an untagged alias, an early/late alias and a reordered phase.
