# Rocket IBuf retained parcel

The optional `cpu.fetch_parcel_buffer` selection names
`merlin.rocket_ibuf_retained_parcel.v1`, fetch_bytes4, parcel_bytes2,
retained_parcels1 and decode_width1, plus exact source and selected RTL hashes.

Selected IBuf.scala has `n = fetchWidth - 1`, `decodeWidth == 1`, and a register
holding at most one unconsumed16-bit parcel. A real32-bit fetch can supply two
compressed instructions. An instruction straddling two fetch blocks can leave
one parcel in the next block. Consuming that parcel does not perform a second
instruction-cache lookup. This implementation retains that single original
fetch owner, and clears it on redirects, branches, fences and aborts. A branch
is conservatively cleared even when its eventual prediction could preserve the
fallthrough parcel.

Actual new fetches use aligned4-byte blocks. A straddled32-bit instruction may
need two such blocks. Only actually accessed blocks populate this buffer;
there is no lookahead instruction, speculative memory lookup or extra queue.
The immutable instruction identity, numerical execution and original fetch
completion token remain intact. This closes parcel reuse only. Frontend's
s0/s1/s2 pipeline, five-entry flow FQ, BTB/BHT, redirect and replay behavior
remain unmodeled, as reported in `instruction_fetch_service`.

Selected IBuf.scala SHA256:
`63f5dfcd41565ec2711caa40c56286d3f1f3c1b2288e55723a31609d52721de6`.
Frontend.scala SHA256:
`d0a10809d2bf87a58ef35a54f7c2d8969af9381d0bf8cae8ebbb93d62d846a9a`.

`test_fetch_parcel_buffer.cpp` checks the finite parcel, block crossings,
partial parcel reuse, and redirect/fence reset without a simulator job.
