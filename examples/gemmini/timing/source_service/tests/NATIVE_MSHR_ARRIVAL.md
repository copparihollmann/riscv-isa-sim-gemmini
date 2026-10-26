# Native MSHR request arrival

`PostedColdWrite::admit` is called both by dispatched device actors and by the
native scalar-memory service outside a timeline callback. Admission formerly
called `wake` immediately. A native arrival could therefore wake an older device
request on the host stack, where that request's classification published an
admission token outside dispatch.

Offer admission as a source-arrival event at the original requested cycle. An
available physical MSHR still accepts on that same cycle. The ten-MSHR pool,
same-set exclusion, upstream transaction custody and source/publication release
conditions are unchanged. This also prevents a future native arrival from
becoming visible to an earlier pending wake.

The focused test requires that an external request at cycle7 neither invokes
its callback before dispatch nor appears before7, and can complete its original
acceptance token at7 without weakening the completion guard. Existing finite,
dirty victim, first-beat and nonzero-offset tests remain in the same executable.
