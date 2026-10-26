# LOOP_WS execute generator

`loop_ws_execute_test.cpp` implements the selected LoopMatmulExecute
idle/PRE/COMPUTE state machine (LoopMatmul.scala335–497) for non-transposed
panels inside the selected SP/ACC capacities. Original loop CPU identity
travels separately from each generated primitive's funct/register fields.
The actual i-fastest/j/k iterator, padded dimensions, garbage-D weight reuse,
first-k accumulation flag, output-ready and source RS-utilization gate all
affect emission. Load-ahead tests use the selected RTL expressions, including
its `ld_ka` comparison in the second B predicate.

This is one of six generators. It supplies no LOOP_WS runtime selection or
opaque loop latency. Full support still requires the two original contexts,
configuration/finite input queue, remaining load/store generators, source
weighted/global arbitration, and actual `from_matmul_fsm` RS-completion
feedback. Generator idle means emission ended; it does not complete pending
memory or mesh output. Unsupported wrapping storage and transpose require
separate source modeling rather than silent packet rewriting.
