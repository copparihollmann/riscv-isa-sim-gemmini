# Execute operand counters

`execute_operand_counters_test.cpp` covers the selected non-transposed WS/SP
counter equations in ExecuteController.scala310–409: A/B/D priority, actual
bank addresses, reverse D row order, padding, the one-row-ahead restriction,
and counter updates only on the real SRAM/control handshake.

Build this standalone component with strict C++17 warnings and the adjacent
source-service include directory. Its ready inputs belong to the original
finite pipelines. It assigns no latency, changes no queue capacity, and does
not enable the currently refused same-bank MUL_PRE path by itself.

Integration must preserve selected generated `Queue5_ComputeCntlSignals`,
`Queue4_ScratchpadReadResp` execute responses (non-flow, pipe), the SRAM
response Queue1 (flow, pipe), and MeshWithDelays operand registers/tag queues.
Those owners determine readiness and actual result-row bubbles; a doubled
DIM service bound cannot supply their handshakes.

`execute_operand_pipeline_test.cpp` composes those exact SP/control queues
with the operand counters and MeshWithDelays' three replaceable operand
registers. The request/tag queue readiness and actual SRAM port availability
are inputs. A quiescent DIM16 stream consumes source rows on edges0–15 on
distinct banks and edges0–31 on a shared A/D bank; mesh row0 fires on edge3
or4 respectively. The shared bank then feeds a mesh row every two edges.
All32 physical requests retain their original operand/bank/row/serial through
bank/tag stalls, with Queue5/Queue4/Queue1 capacities unchanged. These tests
cover the finite input pipeline, not the subsequent systolic/tag/output
schedule. A second original request may start after the source counters
consume their last row while the first request remains in the finite input
queues and mesh registers. The chained test retains that original ownership
and checks a subsequent garbage-D floor4 request without draining the old
pipeline or discarding its responses. Output-tag/row-count queues still
need to supply actual finite request readiness during integration.

`execute_mesh_tags_test.cpp` supplies those original two six-entry queues,
five wrapping matmul ids, and the selected response delay of16 mesh edges
+1 output register+15 deskew registers. Twenty floor4 requests exercise
finite full-queue backpressure, original prior-request tag association and
registered credit reuse. An unconsumed final real tag remains live: draining
software never invents the missing following mesh request.

`source_ws_operand_pipeline=1` connects these components to the posted
observer for non-transposed, unit-stride WS, SP inputs and ACC outputs. It
requires explicit selected queue/mesh geometry facts. Every physical SP row
arbitrates on its actual edge after the bank's higher-priority writes; no
future bank interval is booked for the whole command. The mesh output and
actual EX completion edges are visible before settled ACC/store arbitration.
Mesh last-response completion takes priority over the two registered pending
RS ids, which remain owned until their individual successful completion.

PRELOAD/COMPUTE source consumption, original tag custody, ACC row publication
and final fence obligations remain separate. The source mesh/register delay
replaces the old nominal compute result envelope in this explicit domain;
the nominal compute/preload prices are not used to manufacture these edges.
The new posted fixture exercises both legacy controls and the selected real
same-bank MUL_PRE path for rows1/2/3/4/5/15/16. Unsupported transpose, ACC
operands, SP result storage and LOOP_WS retain their existing qualification
limits; this selection supplies no CPU frontend or divider writeback model.
