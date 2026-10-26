# Original stride-zero input loads

For a nonzero source address, selected `LoadController.scala` lines72–76 and
102–117 set `actual_rows_read=1`, one row request, and `repeats=rows-1` when
ConfigMvin stride is zero. Pointer zero remains the separate ZeroWriter route.
A non-null buffer containing zeros is an ordinary memory request.

The selected input scaler (`VectorScalarMultiplier.scala` lines65–96,105–145)
holds that original payload in its one input register. Each `in_fire` emits a
descending row tag into the existing three-entry completion ring; only the final
emission frees the input register. Scratchpad.scala lines420–440 adds this row
tag to the original local address before the existing PixelRepeater register.
Identity scale marks the ring entry complete directly. Source pixel repeats
remain one in this admitted domain.

The observer retains all original local destination rows and useful-byte masks,
but captures one source row and one original stream of Get packets. Every
original fragment emits one finite ring entry per destination row. The original
fragment completes only after all repeated local writes publish. Input queue2,
input register1, ring3, pixel register1, bank arbitration, packet/transaction
ownership and command dependencies remain unchanged. Ring-full backpressure
holds the original input register, rather than prebooking later writes or
creating independent memory requests. Singleton stride-zero loads need no
repeat and use the same ordinary packet path.

Admitted source domain: selected identity input ingress, scratchpad int8,
identity scale, pixel_repeats1, original rows1–16, columns within the selected
Mvin field and existing packet mapper. Nonidentity scaling, pixel repeats,
unsupported widths/rows and partially overlapping multirow source strides do
not inherit this route. The older synchronous StagedObserver explicitly refuses
row repeats; it has no register/ring repetition actor. Existing aggregate memory
response bounds and response-order qualification are unchanged.

`posted_input_broadcast_test.cpp` checks one original request stream, descending
row order, unaligned useful-byte masks, multiple column bands, finite capacities,
actual bank pressure and the unsupported cases above. This is component
correctness and coverage evidence, not physical timing qualification.
