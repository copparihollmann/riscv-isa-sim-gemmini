The next integration should connect the finite h0/1 VSE32 actor to the frozen
three-hart physical memory System, while retaining source memory-controller
ownership. Replacing the actor's synthetic ACK duration alone is insufficient.
No native, fixture, fitted parameter, selected package or hardware input changes
are part of this plan.

The first target is M-mode, bare translation, aligned, fully defined, unmasked
unit-stride nf1 VSE32 of at most 256 bytes. The existing original-handler COM
quarantine remains the functional admission point. It captures owned values and
known masks without changing RAM. A whole-register lease remains conservative
until all source store VRF-read handshakes have completed. Scalar ALU and reads
of permitted counters can overlap. Memory, state CSR, IRQ and context consumers
retain their existing conservative drains until separately qualified.

The physical connection is `shuttle{0,1}_tile` and
`_vector_unit_auto_atl_out_{a_*,d_ready}` in System v6. This bypasses the scalar
L1D. A scalar warm touch therefore cannot establish a vector L1 hit. The physical
boundary is 256-bit data, 32-bit mask, 35-bit address, 5-bit source; compute DLEN
and Saturn internal memory requests are 128 bits. A fully occupied 256-byte
store creates sixteen 16-byte requests, each one physical 256-bit A beat with
a half-word mask. It does not create eight requests merely because ATL is 32
bytes wide. Partial active payloads require the qualified compactor byte masks.

Reuse the *entire* saved `TLSplitInterface -> TLWidthWidget16 ->
TLBuffer_a35d256s5k4z4u` path from `SaturnShuttleUnit.sv`. The buffer is real
source state. Directly packing a half-word or assigning an arbitrary A-ready
delay would lose its handshake/phase behavior. The System v6 boundary starts
after this Saturn buffer, so it must not be duplicated in the System.

The configured split's writer is TLXbar input 1. Its external source is
`{1'b0, tag[3:0]}`; reader input 0 uses `{1'b1, tag[3:0]}`. Thus stores use 0..15
and loads use 16..31 before the tile's own remaps. Let the real tile/NoC/L2 path
perform all further source translations. A returned store D must be an accepted,
owned, nonduplicate AccessAck with matching hart and source, no denied/corrupt
bits. Reader D cannot release a store. Keep distinct `(hart, command generation,
request generation, ROB tag)` identities; the four-bit tag alone is not stable
across reuse.

The VMU reserves a *circular* ROB tag at the store-address sequencer request
handshake, before physical A acceptance. `store_req_q` has depth two and is
coupled to compactor and SIFQ readiness. D sets the corresponding ROB completion
bit. The SIFQ and ROB retire in source order; a later returned tag cannot be
reallocated merely because its ACK arrived. The ROB can forward a head ACK
directly into the same-edge dequeue without inserting another edge. Source
`maybe_full` distinguishes sixteen outstanding entries from empty after pointer
wrap. The old actor's lowest-free-tag set/free-on-ACK policy must be removed
when replacing this boundary. A first small reference component can translate
this exact ROB control and differential-test it against its saved SV; that does
not by itself implement AddrGen, SIQ/SIFQ or physical readiness.

`Mem.scala` clears an SIQ entry only when its final SIFQ entry is dequeued, after
its ordered ACK. `TLInterface` also retains an A-minus-D in-flight count. Full
Shuttle `backend_busy` includes backend busy, TL memory busy and VMU busy.
FENCE must therefore wait the actual modeled outstanding transactions and
source-ordered completion, including the pre-edge busy phase. VRF lease release,
CPU front retirement, physical A acceptance, D ACK, SIQ release and functional
publication are separate events. The COM-to-VU source phase remains explicitly
conditional in the current finite bridge.

For first single-writer functional integration, the quarantined Spike mirror
can publish only on the matching physical store ACK. That is an explicit
conservative mirror convention, **not** a proof that coherent visibility first
occurs at ACK. A physical cache may serve a probe/read before the original
writer receives D. Consequently, both-hart contention first uses disjoint lines
and validates returned data through the real fabric. Supporting overlapping
reads/writes requires the actual LIQ/SIQ dependency masks and source service
values; it cannot reuse ACK-time mirror publication as a global memory model.

Clock conversion is explicit. The qualified System v6 fixture uses a 1 GHz
master tick: uncore and both Shuttle memory paths every 2 ticks, Rocket every 2,
Bringup every tick, Serial every 10. The current native actor profile uses
500 MHz global source-cycle units. Native cycle N therefore corresponds to
master tick 2N. The intermediate Bringup edge at 2N+1 must execute. Serial's
period is five native cycles, not ten. Preserve odd-master-tick event timestamps
as half-native-cycle stamps rather than rounding an ACK early or adding a
handoff edge. Clock origins/reset waveforms are explicit caller inputs; the
fixture's aligned phase is not a universal image/CDC phase claim. Evaluate all
peers to one same-edge fixed point, sample handshakes, then commit the selected
edge set with no peer re-evaluation between commits.

FASED parameters are required external inputs, with source and unit provenance.
The existing read-only System fixture's 30/30/16/16 is synthetic: 30 refers to
Bringup/FASED target edges in that fixture, not 30 CPU cycles and not total
store latency. Its host service currently rejects outer AW/W, so it cannot be
used unchanged for vector-store traffic. A new external backing peer must own
independent AW and W handshakes, byte strobes/Wlast and matching B; own AR data
at acceptance and supply stable registered R beats at the actual selected
egress request. Dirty L2 writebacks and architectural mirrors remain separate.
No timing parameter is inferred from old startup or fitting observations.

The independent qualification order is:

1. Exact ROB control/clock stamp component: full capacity, wrap, out-of-order D,
   head same-edge forwarding, simultaneous reserve/dequeue, duplicate/unknown
   response refusal, separate h0/1 generations and source-ID direction checks.
2. Saved Saturn split/width/buffer connected to System v6, actual reset, external
   service with explicit parameters/backing. Drive real accepted stores/reads;
   verify A payload/mask/source and matching D under actual backpressure.
3. Two writers on disjoint lines, repeated tags/wrap, one withheld response,
   contention and dirty-owner probe controls. No observed-ready/state injection.
4. New native opt-in child retaining COM quarantine and guards. Compare full
   data/known masks, no early RAM write, killed candidate makes no A, FENCE
   cannot pass outstanding ACKs; OFF byte parity, 32 functional and appropriate
   OS/consumer guards. No automatic transfer of old coefficients/qualification.

System v6's default source-RPQ unknown-head refusal, actual metadata scrub and
TCM byte knownness remain enabled. Its 64 accepted loads per Shuttle are an
explicit component initialization stimulus, not constructor zeroing or normal
boot evidence. Full internal four-state knownness, FASED host-token ordering,
arbitrary overlapping backing transactions, complete CPU joins and deployed
FPGA-image association remain unresolved. This is a causal component plan, not
a complete SoC, multicore vector-memory or ±2% timing claim.
