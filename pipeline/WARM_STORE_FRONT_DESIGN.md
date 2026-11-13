# Optional warm scalar-store front: separate successor of523

This lane must preserve frozen523, its live fitting inputs and all prior
snapshots. The initial scope is aligned M-mode SB/SH/SW/SD and their integer
compressed forms to DRAM. Vector/FP stores, atomics, TCM/MMIO, translation,
watchpoints and uncertain address/permission state retain the ordinary path.
Cache V6 is frozen separately under empirical-cache-v6-qualified-v1.

The source places a Shuttle request in EX (Core.scala596), store data in MEM
(779), kill/nack handling at914/917 and COM replay at1106. DCache.scala291,
480 qualifies the masked write by a hit and absence of nack/kill. The intended
fast model uses source RAW/issue rules and an optional dirty-private-line
predicate; it does not claim physical cache or exact nack timing certification.
Rocket's separate single-issue stage path must receive the same architectural
ownership checks, without assuming the Shuttle issue width.

At candidate selection, require known base address, ordinary M-mode context,
no data trigger, valid PMP/PMA mapping and a V6 owned dirty private L1 line.
Base and store-data RAW dependencies remain the actual source decoder inputs.
The store gets an external shadow record with destination x0: it cannot
fabricate a GPR value. Partial store data remains opaque and is written by the
original typed instruction handler at architectural COM, after all older
architectural GPR writes. The decoder must distinguish stores from existing
empirical loads explicitly; MEM alone is not a load flag.

At COM, recheck the owned-line predicate. A successful zero-extra-cost store
begins/finishes the V6 intent within that callback and publishes exactly once
through the original handler. There is no functional write at RRD/EX/MEM.

If ownership changed, retain the store instruction and original operands,
annul only younger speculative CPU rows, and redirect their frontend state to
the successor PC. Begin a normal cache-owned write intent and create a
noncancellable conservative response actor with real pending-owner
dependencies. Rebind the store's COM to that response and add it as a WB
dependency before pending starts. Hold CPU/IRQ dispatch for that hart until
this accepted instruction completes. The response callback performs the one
architectural store, releases its cache owner and resumes the cohort. This is
an explicit conservative ownership-loss service, not an invented source nack
penalty, fatal COM guard, early write or lost physical actor.

Same-edge engine completion order is by node ID and skips canceled nodes.
Therefore an older store's COM attempt can annul younger same-edge CPU COMs
before they run; accepted load actors are retained by the existing squash
rules. Shuttle WB can receive a dependency on the replacement response before
it starts. Rocket COM/WB is the same node, so its replacement must update both
fields. No instruction-retirement, mcycle or source-counter completion occurs
on the unsuccessful COM attempt. The retained instruction's prepared fetch
already gives it priority over interrupts arriving during owned service.

Configured positive write/family costs must be charged explicitly through
owned response service, never ignored as an accidental fast-path shortcut.
Miss/outer resource selection retains shared launch intervals and dependency
ownership. A selected523 calibration is not transferable to this new epoch.

The final candidate preserves523's scalar DRAM rule priority: cache-service
rules supersede ordinary DRAM family costs. It uses the same per-hart
fractional accumulators and floors the accumulated residual, avoiding a
one-cycle charge for every fractional coefficient. A configured issue interval
greater than one reserves a response actor even when the added latency is
zero. Synthetic controls independently check fractional totals, interval-four
launch spacing and byte-identical guest/prefix/trace behavior when a superseded
family rule is added to a zero-cache-service configuration.

The private runtime copies preserve all523 scheduling source bytes. The only
API addition is completion-owned payload publication: a callback can annotate
its own live completing node after the typed effect. Calls outside that phase,
for a different node or with conflicting payloads refuse. A10,000-publication
bounded-history control drains with zero retained nodes. Shared runtime files
and all frozen epochs remain unchanged.

Required evidence: integer/compressed widths; independent and dependent base/
data producers; opaque-byte transport; all3 physical harts; actual dirty
private hits; real cross-hart ownership loss and wait dependencies; no write
on annulled stores; exactly one publication; a timer pending during retained
service; recoverable protection/misaligned fallback; functional-off parity;
full32 and five realOS groups. Measure all counts/elapsed and refuse unsupported
configurations before use. Keep every failed attempt and guard intact.

Actual directed evidence is in build/store-front-directed-final-v1 and
build/store-front-fault-final-v1. The former proves all integer widths/four
compressed forms, partially known bytes, wrongpath canaries, both directions
of peer-owner ordering, and a pending timer before retained publication on all
three harts. The latter recovers nine ROM/PMA, unmapped and misaligned store
faults. MPRV remains the exact existing translated-memory capability refusal;
PMP configuration and arbitrary translated/debug/watchpoint paths are not
qualified. Source store phase citations support the design, but no dedicated
whole-RTL store-only phase differential or physical coherence certification
is claimed.
