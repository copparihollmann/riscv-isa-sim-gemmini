# CPU shared-cache request admission

Selected inclusive-cache `Scheduler.scala` drives a directory read from an
eligible MSHR allocation or reload. An upstream request cannot publish a new LLC
cache generation before that owner exists. This applies to native CPU Get /
AcquireBlock traffic as well as device requests.

The optional native V10 intake uses a read-only private-cache probe to identify
one or two adjacent original LLC line requests. It changes no tag, replacement
state, traffic count or dependency value. The selected private/LLC line sizes
are64 bytes, with one private level followed by the selected shared cache.
Larger or disjoint scalar request footprints remain unavailable.

Each request obtains its original finite MSHR/set lease before native LLC
classification. The captured V7 allocation children must match the previewed
line order exactly. They inherit those leases rather than charging a second
request. Their real publication/source closure releases each lease, and all
children join one original CPU memory completion. The scalar instruction still
owns its register result and instruction cost. No critical-word completion is
inferred for the selected blocking DCache.

If the native private controller accepted a probe during the LLC wait, a retry
retains the actual leases until that observed controller ownership closes.
This is bounded software polling, with no early completion or extra hardware
credit. The private prefix and two-child admission remain conservative bounds;
this does not claim a complete Rocket private-cache pipeline model.

Focused controls cover a same-set older device writer and a later CPU writer of
the same cache slot, a two-line CPU request with one final completion, and a
private-controller retry. Native controls verify that repeated previews consume
no state and retain the subsequent original cold miss, and that private hits
produce no LLC request. Existing read-allocation victim, beat and publication
checks remain active.
