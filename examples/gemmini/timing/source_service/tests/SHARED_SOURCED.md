# Selected shared SourceD pipeline

Source: the audited local Chipyard `rocket-chip-inclusive-cache/design/craft/inclusivecache/src/SourceD.scala`, the complete exact source hash is retained in the runtime `source-inputs.json` manifest. The selected generated FIR is SHA256 `6748b9756799c086a6fb06e6d80b4b052f2771f9eb1858c172e14dcf441ba149`.

SourceD S1 sets busy on a valid request and clears it on `s1_valid && s2_ready && s1_last`; `io.req.ready := !busy`. This allows another original request on the following edge, independently of the previous S3 response or S4 write. S2, S3 and S4 each have a single full bit. Their ready equations permit same-edge replacement, with S3 waiting for D acceptance and S4 waiting for its real bank write. Reads also enter S4 because `s1_retires := !s1_single`.

The opt-in `source_d_shared_pipeline` uses one set of these three finite stage credits for original masked/full writer packets and original read allocations. S1 ownership ends at final S2 acceptance, never at a guessed fixed latency. Native cache-line publication still waits all real bank writes; fills, MSHR ownership, response acceptance and packet ACKs retain their existing owners. Legacy one-beat routes remain on their explicit conservative contract and cannot select this mode without the unified packet path.

`posted_shared_source_d_test.cpp` holds the first store's D acceptance until cycle20 and its S4 storage credit until40. A subsequent read enters S2 before that write publishes, cannot bypass the store's D response, and prevents the next store from bypassing the held S4 credit. Each stage peaks at exactly one. `ordered_pool_readout_test.cpp` also exercises selected shared stages across pooled partial packets, raw packets and i8 packets.

This removes a source-inconsistent cross-opcode serialization. It does not close eager native cache classification, forwarding/bypass coverage for arbitrary concurrent same-line accesses, scalar writeback arbitration, or LOOP_WS expansion.
