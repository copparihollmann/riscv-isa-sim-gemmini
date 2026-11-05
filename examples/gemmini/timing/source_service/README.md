# Experimental source-service provider

An explicitly selected alternative to the adjacent original Gemmini provider.
Its source ancestry is separate; it must not replace the original provider or
remove independently developed optional modes. Default profile files, prices,
original source export and active runtime selection remain unchanged.

The model separates finite reader transaction credits, registered identity scale
and pixel handoffs, local scratchpad bank ports, operand consumption, late ACC
writes and readout queue/response phases. Individual modes require explicit
matching RTL/fact assumptions. Unsupported partial output transactions remain
UNKNOWN. It is provisional, with unresolved response ordering and joint CPU/DMA
arrival composition. No fitted coefficients or benchmark-specific dispatch.

Use export_source_service.py to export this exact source family independently.
Runtime review and selected hardware/domain admission remain caller obligations.
A source bundle grants no qualification. gSIM external-memory service does not
imply FireSim DDR3/FASED timing equivalence.

Bounded WS execution uses actual accepted command arrivals, ready next-PRELOAD
operands, separate row-consumption/ACC-result ownership and unchanged RS/controller
limits. It never pairs an unarrived command or credits its completion early.
Short single-MUL feeds additionally require current A/B/garbage/transpose fields
and an exact immutable-ELF suffix through a genuine full fence, validated against
actual subsequent commits. A future PRELOAD can require MUL_PRE D input; without
closed context the conservative full-row feed remains. Source trace evidence is
not hardware cycle qualification.

### Wide source-row publication

Opt-in `wide_scratchpad_row_publication` requires selected mvin column/row field
widths7/5 and the original identity packet pipeline. The selected StreamReader
accepts at most16 source rows and a7-bit column count; each actual Get remains at
most64 bytes. Packet payload fragments map to `row + band * block_stride`, with
original row-offset masks and BeatMerger's useful-byte validity predicate. One
Get can publish several rows, yet owns only one reader transaction until its
incoming last beat. Row readiness, reader credit, controller occupancy and final
command completion are separate. Final command publication must not overwrite
earlier completed rows. Destination aliases and unsupported bounds refuse.

Source anchors: LoadController.scala request geometry; DMA.scala entry addr,
block_stride and spad_row_offset; BeatMerger.scala bytesSent/valid/mask/out.addr;
Scratchpad.scala registered identity/pixel handoff. No hardware resource or timing
price changes. Coverage boundaries16/17 and127/128 are tested explicitly; exact
alignment/pitch/mask tests include5,760 geometries. The row-publication regression
also checks original narrow behavior, actual bank-port write count, and stable
early row readiness after command completion and a full fence. Existing FIFO
response and narrow-row aggregate publication assumptions remain provisional.

Native feature reports expose `target.load_publication.packet_per_row`,
`packet_command_boundary`, `row_stream_command_boundary`, `aggregate_fallback`
and `unsupported`. These are selected source-path counts, not a grant of physical
accuracy. Aggregate fallback and command-boundary publication must remain visible
when comparing variants, even if numerical execution and model timing complete.
Unsupported source geometry also preserves the normal UNKNOWN/unresolved reason.

### Optional posted source timeline

`diagnostics.posted_source_timeline.enabled` selects the separate
`spike_timing_create_posted_provider_v1` factory when the observer and this bundle
both provide it. It requires an exact counter-PC scope and
`diagnostics.stop_after_selected_scope.enabled`. The original factory, provider
and profiles retain their existing behavior.

The observer admits the in-order CPU source through the same bounded timeline as
target actors. Native cache/TLB lookup happens at source acceptance rather than
when a future DMA operation is described. The provider separates RS admission,
finite controller input queues, local row generations, operand consumption,
accumulator publication and final command retirement. Actual controller heads
are required for PRELOAD lookahead and MUL_PRE pairing. Reader return credits
are global, and the selected identity Queue2, input register, completed ring3
and pixel register backpressure the BeatMerger. The last output can hand off its
request on the same edge permitted by BeatMerger's `io.req.ready` logic.

This route currently supports identity INT8 scratchpad loads, non-transposed
unit-stride WS computation, and full-transaction raw accumulator readout.
Unsupported primitives, mappings or missing source premises refuse. It is an
experimental composition model: native memory still supplies an aggregate
packet-completion bound, ready responses use provisional FIFO ordering, and the
raw writer retains aggregate memory service. It does not establish an MSHR/RR
response schedule, exact readout backpressure, global timing accuracy or a
FireSim memory domain. Reports identify these approximations and remain
unqualified. No source price or hardware change is implied.

The optional bounded modeled-event trace requires explicit original actor
custody. The observer checks the posted provider capability before accepting
this diagnostic. Owned stages retain original accepted PC, instruction bits and
stage role through deferred issue, memory, operand and result callbacks. CPU
stages also retain their actual committed instruction index; target stages do
not invent one. Bookkeeping records are labeled separately. Any unbound posted
stage is reported rather than retagged with the current CPU site. This changes
no timing, hardware or prices. Scoped resource accounting remains available;
modeled queue waits are diagnostics, not physical stalls or utilization.

### Registered raw-command ingress

Within the posted route, optional `target.scheduling.source_raw_command_ingress`
separates CPU raw-command acceptance from subsequent RS allocation. This mode
requires selected hardware facts for four two-entry, non-flow, non-pipe queues:
`raw_command_queue`, `loop_conv_command_queue`, `loop_matmul_command_queue`, and
`unrolled_command_queue` (each `_entries`, `_flow`, `_pipe`), plus
`selected_has_loop_conv=1`. Missing or different facts refuse the selection.
The selected Controller/LoopConv/LoopMatmul passthrough chain supplies these
registered stages; loop-FSM commands and result-returning instructions remain
unsupported. This adds no new hardware capacity.

The scalar CPU stalls only when raw enqueue cannot accept. Four finite actors
then carry the original accepted PC, instruction and operands to RS allocation;
a later CPU instruction never supplies a deferred command's provenance. A full
queue cannot use a dequeue credit on the same edge, and an empty queue cannot
flow through. Architectural counts remain at original CPU acceptance while
timing decoding occurs at actual RS allocation. FLUSH follows the source bypass
without a fabricated RS entry or TLB-response acknowledgement. Full fences drain
all upstream queues and all allocated controller/memory actors. Existing
`modeled_cpu_rs_wait_cycles` describes direct-RS mode;
`modeled_raw_source_wait_cycles` describes optional raw-enqueue backpressure.
Neither is a physical stall measurement. Source and scope qualification remain
independent of these diagnostic counts.

### Software observation bounds

The posted observer defaults to1,048,576 lifetime completion identities and
8,000,000 dispatched callbacks. Large exact ROIs can prospectively select
`diagnostics.posted_source_timeline.completion_token_budget` (maximum16,777,216)
and `dispatch_budget` (maximum64,000,000). These protect software memory/work,
not target queues, hardware capacities or timing prices. Reports expose the
selected software bounds. Exhaustion remains an explicit refusal. Completed
command drain-history references are reclaimed without erasing token history,
changing row generations, crediting early completion or enlarging live queues.
The65,536 outstanding-command protection applies to live custody, not to total
workload command count.

### Pending memory visibility

Optional numeric `diagnostics.posted_source_timeline.pending_memory_visibility=1`
keeps accepted cache/memory writer generations pending until their actual lazy
Engine stage completes. CPU fetch/data and target Get/Put consumers use the same
source timeline. A cache tag classified at source acceptance is not automatically
a completed fill: a later hit must retain the preceding fill dependency even
when that writer is waiting for a real memory port. Existing read lifetimes,
WAR/WAW, independent values and actual source arrival order remain intact; the
mechanism reserves no future port and supplies no guessed response milestone.
This is a visibility correction, not a replacement for unresolved LLC/MSHR
response arbitration or a grant of timing accuracy. Defaults are unchanged.

### Optional selected-TSI loader initial state

`memory.initial_state` schema `merlin.tsi_elf_cache_bootstrap.v1` is an
observer-only, source-reviewed initial state. It requires an ELF64 little-endian
RISC-V EXEC image, PT_LOAD physical addresses, selected TSI alignment 4 and chunk
size 1024, shared cache `l2`, replacement scope `one_loaded_line_per_set`, and
an exact `source_receipt_sha256`. The normal review binds the selected gSIM
invocation without `+loadmem`, cache-flush or extra payload options to the actual
loader sources. The observer reopens the executed ELF and reproduces file/BSS
write address coverage, including memif edge read/modify/write ordering.

The loader's completed TileLink writes seed shared-cache dirty lines before
CPU timing begins; private caches and all prices remain unchanged. No guest
work or resource occupancy is invented. Any two distinct loaded lines mapping
to one set refuse the bootstrap and make timing unresolved, even when they
could fit multiple ways: the selected directory uses random replacement rather
than invalid-way-first allocation. Supporting those cases requires a checked
selected replacement/loader event model. Feature counters report applied state,
loaded lines/chunks/bytes, or explicit unsupported coverage. Absence of the
selection preserves cold initialization. This is a gSIM loading-domain option;
it does not establish FireSim bootstrap or external-memory equivalence.

Prospective schema `merlin.tsi_elf_cache_bootstrap.v2` additionally requires a
source-reviewed `directory_read_contract_sha256`, replacement scope
`serialized_tsi64_directory_reads`, and an explicit
`memory.caches.l2.replacement` object. That object selects
`merlin.read_stepped_lfsr_replacement.v1` with source widths, taps, reset seed
and receipt binding. The loader replays every 64-bit masked Put and edge RMW
Get, including cache hits, then preserves the resulting replacement state for
subsequent modeled directory lookups. Unlike v1 it can represent conflicting
sets. It is a separate source contract; v1 reviews do not admit v2.

The native L2 replacement selection is optional and defaults to the existing
policy. A reviewed source profile must establish that each accepted memory
callback corresponds to its directory lookup and that pre-program loader
traffic is serialized without extra directory actors. A warm-all address hint,
miss-only LFSR advance or per-unique-line replay is not equivalent. The initial
state report identifies total loader bytes/chunks, all directory reads, final
resident-line count and the post-loader replacement state separately from ROI
feature deltas. This source coverage is not an accuracy qualification.

### Registered reservation/controller visibility

Optional `target.scheduling.source_controller_visibility=1` requires explicit
selected hardware facts: one registered RS entry-valid stage and controller
input visibility stages `{load:1, execute:2, store:1}`. The execute path includes
the transpose-unroller queue and multiheaded command queue even for the admitted
nontransposed WS form. The existing issue latency must be exactly one.

RS allocation, RS issue, controller credit and visible command head are distinct
moments. The source actor waits for the registered RS entry, releases issue
ordering at the real handshake, reserves downstream credit immediately, and
publishes the command only after the queue stages. Pending entries count toward
finite controller capacity and full fences drain them normally. Absence of the
selection preserves the earlier experimental route. The selected source
contract and exact public actor/handshake traces justify these stages; they are
not fitted per-command fees or a change to hardware capacity.


### Optional registered reader transport

`target.scheduling.source_reader_registered_path=1` selects a separate inactive
source-law increment; it does not change the original provider or any prices.
The required hardware fields are `reader_translation_queue_{stages,entries,pipe,flow}`
=`2,1,1,0`, and `reader_tl_buffer_{stages,entries,pipe,flow}`=`3,2,0,0`.
They describe the selected two registered translation queues followed by three
non-flow TileLink A buffers; the same three D buffers carry individual return
beats. The RocketTile local boundary is transparent in this selected source;
the TilePRCIDomain boundary contributes the third registered buffer. Flow buffers
at the inclusive-cache exterior add no fixed empty-path latency.

The selected cache-hit front end has `inclusive_hit_directory_stages=1`,
`inclusive_hit_plan_stages=1`, `inclusive_hit_source_d_stages=2`. Its four-cycle
Directory/MSHR-plan/SourceD pipeline includes the existing scalar lookup cycle
(`memory.l2.hit_cycles=1`); the transport adds only the other three stages.
This is pipelined latency, not a four-cycle initiation interval, and is not a
fitted per-command charge. The source-stage extension is admitted only after the ordinary memory callback
and its read-only `MemoryMilestoneQueryV2` prove the SAME exact request's
resident, ready cache line with no probe or eviction, and scalar lookup service
of one cycle. The selected finite XactTracker chooses the first free source;
that source and its reuse generation remain distinct from cache/fill/MSHR IDs.
Missing native queries, mismatched requests, pending fills, misses and coherence
paths explicitly make this increment UNKNOWN rather than adding three cycles
to a potentially overlapping composite service. No repeated cache access is
used to obtain that observation. Aggregate packet completion and response
ordering in that service remain provisional; these stage facts do not establish
complete MSHR/cache arbitration or independent timing accuracy.

Each queued payload keeps its original command identity. Request cache lookups
occur only after the actual request transport accepts. Return queues carry beats,
not whole packets disguised as single entries. The reader transaction credit is
released at the actual final D-beat acceptance; the merger waits for both its
useful outputs and remaining packet beats before accepting the following packet.
A stalled consumer holds its finite downstream credit. Missing selected facts,
unsupported transfers and exhausted event budgets remain explicit failures.

The preferred general composition sets
`target.scheduling.source_reader_memory_owned_cache_pipeline=1` together with
the native `memory.device_read_pipeline` selection described in `timing/README.md`.
The provider then adds **no** post-`SharedEffects` cache extension and needs no
resident-only observation exception: the native cache owner places the source
stages before its miss recursion and coherence max joins. It checks that the
selected Directory/MSHR/SourceD/scalar component facts match this target source.
The finite translation and A/D transports remain separate. Default source
choices and prices are unchanged; neither route promotes a model.

### Optional full aligned INT8 readout

`target.scheduling.source_aligned_i8_readout=1` admits unpooled accumulator
INT8/ReLU exits only when each original output row is one full aligned16-byte
client transaction. It requires the already selected passthrough normalizer,
8-stage elastic scale pipeline,5 issue-metadata entries,16 writer transactions,
and translation-hit assumptions. Partial rows, pooling, nonlinear normalization
and multibeat INT8 transactions retain explicit refusal.

The actual consumer now accepts `store_act1` through the same source scale
pipeline. ACC response ownership, normalizer visibility, finite issue metadata,
writer request capture, translation and return acknowledgment are separate
actors. Reader and writer share the selected two common A and D queues; each
has its own client queue. Writer credits release on D acknowledgment, with
next-edge reuse when the bitmap was full. No queue depth is interpreted as a
per-row latency, and no guest work or hardware capacity changes.

The cache owner still supplies aggregate write service. A four-cycle
Directory/MSHR-plan/SourceD **minimum** is applied with `max`, preserving larger
coherent/miss service rather than adding a second fee. This does not establish
storage publication at D acknowledgment: SourceD forwarding, late physical
writes, finite LLC arbitration and masked write response remain separate
coverage gaps. The route provides provisional cycle/resource feedback, not a
new accuracy qualification. Full-width raw readout retains its prior route.

### Optional full-width accumulator MOVIN

`target.scheduling.source_full_accumulator_load=1` adds a separate source-bound
route for nonzero-memory INT32 accumulator loads, up to16 rows and
16 elements per row. It requires explicit selected facts: separate accumulator
scaler, absent scale arguments, Queue2 input, one replaceable input register,
zero scaler pipeline stages, two-port accumulator storage and two write stages.
Shrunk input, zero filling and pixel repeats do not inherit this route.
Accumulating loads additionally require selected physical accumulator-bank
read/modify/write arbitration. They retain the old row value as an input and
wait for its publication before the write handshake. Without that selection,
accumulation remains unsupported. A nonzero-memory stride-zero load uses the original
`LoadController.scala:76,105` rule: fetch one input row and retain it for the
declared number of output rows. The scaler register decrements `repeats`, emits
rows in descending order and cannot release/replace its input until the last
actual write accepts. Requested DRAM bytes count the fetched row once; local
write accounting still covers every original output row.

`reader_packets` retains its16-byte scratchpad default. The optional64-byte
local row maps actual INT32 bytes and masks to one accumulator row; a64-byte
response waits for all four returned beats before the merger can publish its
fragment. Source selected `Scratchpad.scala:412–455` connects this path directly
from `mvin_scale_acc_out` to accumulator arbitration, bypassing PixelRepeater.
`VectorScalarMultiplier.scala:51–62,65–101,193–205` supplies the finite input
storage and latency0 path. `Scratchpad.scala:776–872` preserves execute-port
ownership and the SP-last suppression condition; `AccumulatorMem.scala:113–118,
180–184` supplies the two-stage overwrite publication. The consumer waits at
the actual port and leaves same-row dependencies intact. Aggregate memory
response ordering and the shared combined ACC resource remain provisional;
this is coverage expansion, not an accuracy qualification or a price change.

### Conditional masked one-beat INT8 writer

`source_masked_i8_readout=1` uses an optional typed native write service. The
original transaction address/size/mask and actually useful byte interval stay
distinct. A one-column store modifies one byte, even though its client packet
contains16 bytes. Sparse/empty masks, multibeat packets, unavailable ownership
and unsupported cache regimes explicitly refuse; the v1 service ABI and full
aligned writer retain their defaults.

The initial native admission covers an already resident cache line without a
private-cache probe or eviction. The selected Directory1/MSHR-plan1 replaces
the existing scalar lookup at its owner. SourceD is then a separate finite
S2/S3 pipeline: its2-stage SRAM read overlaps these registers, rather than
adding a guessed2-cycle partial-write fee. S3 holds D-valid until the actual
shared-D queue accepts. S4 then publishes only useful-byte/cache dependencies;
writer source credit releases independently at the later client D-ACK. This
conditional route requires an explicit no-external-BankedStore-stall premise.
Its limited retained bypass history never grants broader cache/coherence
qualification. The V1 side channel keeps private-cache coherent handoffs
refused, including when a newer service is installed.

`source_masked_probe_sinkc=1` selects an additional V2 side channel. It admits
at most one explicitly selected private probe with its own busy interval and
first/last C-response readiness. Incoming data uses SinkC's Queue1, not an
extra demand cache lookup. MSHR's registered `w_pprobeack` releases SourceD
after the first C beat at offset0, otherwise the last. Actual eight-bank SRAM
reservations preserve SinkC priority over SourceD reads; a colliding S1 read
waits for its real port. SourceD retains its one-request S1 register while
blocked. Its S2/S3 read and S4 publication still remain independent of D credit.

This source domain rejects other CPU/device shared-cache service during a
masked-writer epoch until its actual closing full fence. Cold/pending shared
lines, other probe geometries, multiple private responders and external SRAM
traffic are unsupported; enabling the route never confers universal coherence
or whole-SoC timing qualification. All existing prices remain unchanged.

### Conditional full-packet raw accumulator writer

`source_full_raw_packet_readout=1` uses a separate optional V3 full-packet
service. Original aligned PutFull16/32/64 packets retain one Directory/MSHR
request, one coherent probe and one D acknowledgement. Splitting a four-beat
packet into four independently priced writes is not equivalent. The selected
StreamWriter has one captured row and16 transaction sources; actual A beats
traverse the translation/client/shared queues. Selected SinkA has40 lists and
40 payload beats; each payload remains owned until its actual SourceD S2 pop.

SourceD reforms the original packet in S1, holds its payload in S2, emits
D only for its first internal beat in S3, and publishes each accepted SRAM
write separately in S4. Acknowledgement and final publication are independent.
Only the final publication closes the coarse native cache-line dependency.
Later writes to an already admitted packet's pending line wait that exact
deferred publication token; unrelated pending fills remain refused. The
selected eight-cycle accumulator scale pipeline also carries full raw data.
The source laws are in `DMA.scala:475–613`, `SinkA.scala:51–109`,
`Parameters.scala:160–165`, `SourceD.scala:83–294` and
`AccumulatorScale.scala:141–153`; queue geometry must be pinned to selected
elaboration, not inferred from defaults.

This domain retains the original full-packet sequence per row and an actual closing
full fence before another typed-writer route or external shared-memory
consumer. Masked packets, cold/evicted lines, unselected
probes, retries and broader cache/MSHR arbitration remain unsupported.
Without this opt-in the previous raw writer remains unchanged.

`source_multiblock_i8_readout=1` additionally admits unpooled narrow readouts
of 17–64 columns, with up to sixteen output rows. It requires the selected
masked-packet path, four StreamWriter block registers, a sixteen-row local
block stride and final-block-only `store_en`. Intermediate blocks fill the
original row registers without creating memory transactions. The final block
starts the bounded original packet sequence. StoreController requests remain
ordered and wait for admission, rather than using an enlarged synthetic queue.
Full-width multiblock readout and widths above64 columns remain unsupported.

### Opt-in cold output writes

`source_cold_write_misses` uses the optional native `ColdWriteServiceV4` ABI.
The native owner previews and checks the exact selected replacement allocation;
old V1/V2/V3 services retain their resident-only admission rules. Full cache-line
PutFull requests use permission-only AcquirePerm; subline writes use AcquireBlock
and one real line fill. The consumer models SourceA/Cork/SinkD/SourceE finite
queues, ten ordinary demand MSHRs (not the two reserved nested MSHRs), eight Cork
sink credits, and actual shared SRAM noop/data acceptance. Cache/DRAM dependency
values stay pending through the existing SourceD publication owner.

Current admission allows invalid or clean victims with no private client.
Dirty-victim releaseData and private-victim shoot-down remain UNKNOWN. Whole-line
fill readiness and clean-release acknowledgment are conservative boundaries;
this is not exact wormhole/cache-scheduler qualification. Lower-memory startup
retains the selected uncertain price; actual eight 64-bit response beats replace
its aggregate byte floor, rather than charging both. This local-source gSIM
model does not imply the deployed FireSim memory model is identical.

### Optional source actor activity

`diagnostics.source_actor_activity.enabled` enables observation-only lifetime
capture in a matching observer/provider build. It requires an exact original
counter-PC scope and the optional `spike_timing_provider_source_actors_v1` ABI.
`max_pending` bounds open actor identities and pending endpoints (default 65,536).
The capture tracks prefix actors across scope opening, clips unions to the
selected counter window, and discards completed histories at committed CPU-start
watermarks. It adds no timing events, tokens, resource reservations or prices.

`scoped_source_actor_activity` binds every report to the original ELF, model,
scope and counter-boundary receipt. It separates lane command envelopes,
combined RS dependency/admission waiting, execute feed service, reader source
slot residency, StreamWriter packet-state occupancy and writer source slot
residency. The two writer lifetimes end at different actual source events:
final client-A enqueue versus client-D acknowledgement. Readout reduction-register
activity, pure dependency-only wait and deployed DRAM activity are not supplied.
Unsupported routes, missing ABI, nonmonotonic callbacks or bounded-capture
exhaustion produce explicit UNKNOWN/null values, never inferred idle cycles.
These are provisional modeled source lifetimes, not measured hardware occupancy;
generic one-cycle controller reservations retain their separate dispatch meaning.


## Optional row ports, original masked packets and fill publication

`source_accumulator_row_ports=1` selects the two-port, latency2
AccumulatorMem actor using the existing bank geometry. It models per-row
RMW/read exclusion and registered write hazards, with Execute priority over
DMA. The existing mesh result envelope remains selected independently.

`source_masked_packet_readout=1` uses the V8 native packet interface for full,
partial, raw, i8 and pooled writes through one StreamWriter/SinkA/SourceD owner.
Every original packet retains its size, beat masks, useful interval and one
ACK. Partial packets read every original beat at S1; zero-mask beats still
retain payload/transaction custody. With `source_d_shared_pipeline=1`, S1 ownership ends at final S2 acceptance;
shared finite S2/S3/S4 stages retain response and publication backpressure.
Routes without that selection retain their existing conservative admission bounds.

`source_memory_beat_forwarding=1` requires explicit selected MSHR zero-offset
wormhole and SinkD first/last facts. SourceD may begin zero-offset reads after
the first GrantData notice, and each SRAM read waits its two actual outer8B
publications plus the bank exclusion edge. Offset requests wait last grant.
Cache-line visibility and MSHR retirement still wait all original fill beats;
the CPU/DMA subline response can precede that visibility. Ordered child request
admission replaces the prior whole-child completion chain. `source_deferred_read_lookup=1` defers device classification until its original
MSHR/set lease is admitted. The native V10 intake does the same for supported CPU
requests. Routes without these interfaces retain their explicit legacy bounds.
Lower DRAM scheduling and broader cache arbitration remain unqualified.
