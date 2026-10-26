# Weight-stationary output completion

Selected ExecuteController.scala285–301 carries `max(A_rows,B_rows,4)` as
`total_rows` for the non-transposed WS multiply with garbage D. A paired
MUL_PRE with real D retains its full DIM feed. MeshWithDelays.scala97 and198–205 propagate
that request's final input marker to `resp.last`; lines237–246 retain actual
row counts in the finite tag queue. ExecuteController.scala970–977 completes
the original output tag at that last response.

`source_ws_total_rows_completion=1` selects this law for the existing unit
stride, non-transposed WS source domain with actual ACC row ports. The existing
first-result bound and physical row publications remain unchanged. Only the
unconditional DIM-sized final marker is replaced by the actual input count,
including the four-row padding floor. All real result-row publication tokens
remain required before completion. This does not qualify a new first-result
pipeline latency, transposer path, or hardware-loop implementation.

The focused test covers one through five rows and the fifteen/sixteen boundary.
It verifies identical physical result rows and first-result publication, every
result visible before the fence, the selected minimum of four total rows, and
unchanged full-DIM completion. It uses the same source identity and actual
PRELOAD/COMPUTE controller path as other dependency fixtures.

`source_ws_garbage_preload_total_rows=1` also selects the actual single-PRELOAD
case: without transposition, A/B are disabled and garbage D means no physical
SP read, so `max(1,1,4)` gives four control/data rows. The original mesh request
and tag still exist. Paired MUL_PRE with garbage D instead uses the actual
active A/B row counts and the same floor four. The focused fixture checks both
ordinary and garbage PRELOAD, unchanged real result rows and identical first
result timing shifts derived from that source control feed.
