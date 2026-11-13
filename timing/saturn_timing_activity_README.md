The Saturn activity interface observes the source-generated timing unit without
adding model inputs. It distinguishes scalar EX/MEM/COM, dispatcher acceptance,
sequencer beats, finite execution pipes, VRF scrub/writes, physical OPU MACs and
VMU/shared-FPU handshakes. It does not assign a nearby PC to memory or FPU traffic.

`build/saturn-timing-activity-schema-v1/schema.json` binds 2,726 compute fields
(2,788 words) and 1,282 Rocket fields (1,375 words) to exact saved-SV declarations
and generated members. The whole-RTL observer reads the same semantic signals
independently. The SDK provides `sample_activity(optional_uncore_tick)` after
`evaluate`, before `commit`; repeated sampling adds no edge. Each public phase
selects its own Verilator context and restores the caller. The timestamp is
caller metadata; source clocks and rates are never inferred from DLEN.

Raw visibility does not make unreset data known. The reviewed contract is
`build/saturn-timing-activity-contract-v2/contract.json`: 921 compute and 225
Rocket field rules select reset-controlled state and valid-qualified payload.
Every other activity word remains unknown. A reset edge must actually be
observed. Unreset OPU RegNext enables require a subsequent known control edge;
inactive geometry, queue payload, numeric VRF and tile data do not become known
because Verilator returned bits. Actual VRF scrub (64/32 source edges) is separate
from reset and caller-defined warmup. Earlier source proofs preserve the
compute early-load/scrub overwrite counterexample and tile unknownness.

State sampled before edge E describes the interval since the preceding supplied
edge. Handshakes and physical writes commit at E. Consumers must keep these
conventions and must not add edges. The first sample has no preceding modeled
interval. Busy fractions use boolean unions. Accepted operations, completed
operations and live pipe stages are separate counts; VAT slot release occurs
at tail issue and can precede physical completion.

For VME, macro acceptance is `vos.io_dis_valid && vos.io_dis_ready`; a microissue
is `vos.io_iss_valid` (the configured source downstream is always ready). Busy
includes sequencer occupancy, FP8 history, tile-readout valid stages, registered
array operation enables and all physical FMA valid tails. `vos.io_busy` alone
omits those tails. The array accepts up to 256 physical cell MACs per compute
source edge when legal full row/column enables and operands are available.
This is an eligible physical peak, not guaranteed sustained throughput. The
FP8 same-entry issue distance is three; different entries can overlap. Integer
cell writes complete on acceptance; FP8 completion counts the actual source
second-stage valid, rather than attributing a fixed cost to an instruction.
Vector per-op/dtype eligible peaks remain unqualified. In particular Rocket's
shared scalar FMA is not a DLEN256/SEW-wide parallel FMA.

The compact projection is gzip NDJSON arrays, with layout and meaning frozen in
`build/saturn-timing-activity-replay-v2/projection-schema.json`. Each line starts
`[hart,source_edge,tb,known_mask,...27 named values...]`. Bit i of `known_mask`
qualifies value i; the zero placeholder for an unknown value is not known zero.
The stream contains unit busy unions, dispatcher/VME accepts, separate INT8/FP8
physical accepted/completed MACs, VRF write-mask bits, real VMU/FPU handshakes and
selected queue occupancy. VRF write bits are not external memory bytes. External
memory bytes use the separately qualified PhysicalEventLedger v3 protocol-lane
masks, intersected with producer-knownness masks when certifying values.

The independent observer format is gzip little-endian u64. Its header is
`[0x314e494254415349,2889,2889,1513]`. Each frame has
`[tb,source_edge,hart,word_count]` followed by physical inputs, physical outputs,
then activity words. Physical word ordering is the frozen per-profile
`ports.json`; activity ordering is the schema's word index. This observer uses
actual whole-RTL source-clock edges and the TestDriver TB stamp. It does not
drive clocks or internal state. The physical-only native replay computes all
queues, pipes and hazards continuously; activity words never drive the model.

The initial visibility-only fast model refused seed0 because random unreset OPU
controls called the strict FP8 numeric helper with a reserved rounding mode on
a reset edge. That failed run remains in
`build/saturn-timing-activity-proof-v2/vme-seed0.stderr`. The derived compute
variant omits only the reset-time numeric stage0 write: both result-valid stages
are synchronously cleared by that reset, and a future valid result requires a
fresh nonreset operation to overwrite the numeric value. It retains the source
valid/index/MRF/write-priority state and does not initialize any tile. The proof
at `build/saturn-timing-activity-reset-numeric-v1/report.json` checks 262,144
symbolic reset/fire histories and reruns the independent cell/physical-array
corpus. Reserved rounding on a nonreset accepted operation remains refused.

Fresh whole-RTL captures are under
`build/saturn-timing-activity-capture-v1/{vme,rvv,fpcomp,shared-fpu}`. Each finished
with exactly the frozen architectural guest signature. The VME guest checks
1,472 values on each compute hart and the real hart2 decoder refusal. Its
independent source-shape counts are 4×17×31×2 = 4,216 integer MACs per compute
hart and four FP8 formats × that count = 16,864 FP8 MACs. These captures use the
saved standalone IrisConfig FIR and an explicitly documented preload harness;
they do not attest Ethan's loaded image or certify full-system timing/±2%.

These components remain reference/integration tools. The earlier fast active
compute result near 23k unit edges/s and full numeric reference near 5k edges/s
are not SoC MIPS or a finished compiler-iteration performance result. No idle
skip, observed readiness injection or numeric initialization is used.
