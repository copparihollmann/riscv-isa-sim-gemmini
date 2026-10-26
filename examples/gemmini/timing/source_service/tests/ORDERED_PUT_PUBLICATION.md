# Ordered resident full writes

`source_ordered_resident_dirty_put` requires the selected resident dirty/no-probe
MSHR retirement law and the shared SourceD S2/S3/S4 FIFO pipeline. It applies only
to original Put packets whose every beat mask is full. Partial writes, probes,
evictions and a different physical cache line retain full publication waits.

MSHR.scala's `no_wait` reload is independent of final SourceD SRAM publication.
SourceD accepts the next request after its predecessor has entered that FIFO;
S2/S3/S4 preserve actual payload/write order under backpressure. A full writer
does not read old payload bytes. Thus a second full write to the same physical
line can pass coarse value custody at the predecessor's actual SourceD request
capture. Waiting for the predecessor's final S4 publication adds a false WAW
serialization outside the real pipeline.

The provider records the original physical line, predecessor publication token,
and its actual SourceD request-capture token. The generic deferred-value API
matches that exact predecessor. It keeps all independent readers, leaves final
publication pending, and leaves unmatched writers unchanged. Downstream readers
wait for the new final publication; ordered S4 writes also precede it. Pending
handoff records are deleted only when their actual publication completes, with
original identity checks. These records are software custody, not new queues,
credits or MSHRs. The original packet, masks, byte count and one D ACK remain.

Selected source: inclusive-cache MSHR.scala `no_wait`/reload and SourceD.scala
registered S2/S3/S4 handshakes. This selection does not weaken external-reader,
partial-write RMW, set/way eviction, probe or source-frontier dependencies.
