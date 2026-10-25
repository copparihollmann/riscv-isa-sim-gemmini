# Optional scoped resource observer

Enable `diagnostics.scoped_resources.enabled` in the pinned model. Optional
`pairs` entries contain distinct explicit resource IDs `left`/`right`.
The exact selected counter-PC scope is required. Output schema is
`merlin.scoped_resource_activity.v1`; all aggregates refer to its half-open
`[begin_cycle,end_cycle)` model-cycle window.

This uses the Engine's existing Trace callback and leaves Engine layout, event
submission, provider ABI and reservations untouched. Capture starts before the
window to retain crossing activity. Endpoint processing advances only to the
known engine frontier; pending future endpoints remain available for clipping.
Every demand contributes `[start,start+occupancy)` resource units and
`[issue,start)` one modeled waiting entry. Resource demands are unique per event
under the Engine's existing validation. The waiting interval is not attributed
to a particular hazard or physical queue. Intersections are measured once.

65,536 pending endpoints and 32 pairs bound retained state. Overflow, unknown
cycles/occupancy, retroactive intervals and exhausted bounds make the capture
incomplete. Incomplete fields must not be interpreted as zeros. No guest code
or timing parameter is altered; model/source digests change normally.

Run the focused arithmetic check:

```sh
g++ -std=c++17 -I timing timing/tests/test_scoped_resources.cpp -o "$TMPDIR/scoped-test"
"$TMPDIR/scoped-test"
```

It covers overlapping capacity units, both-boundary clipping, pre-window active
work, modeled queue intersections, unknown events and endpoint exhaustion. It
is also registered in `timing/tests/run_unit.py`.

The real public queue-capacity probe tested by Merlin has 354 estimated cycles
with the prior selected observer, this observer disabled, and this observer
enabled. Features and functional stdout are identical; this proves neutrality
for that probe, not physical timing accuracy. The new capture's 19 named model
resources are complete. Receipts and exact source hashes are retained in the
Merlin companion `experiments/reference-data/scoped-resources-20261023`.
