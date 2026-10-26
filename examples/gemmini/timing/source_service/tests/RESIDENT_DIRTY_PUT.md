# Dirty resident Put MSHR retirement

Selected `MSHR.scala` initializes all wait predicates true and schedules SourceD for an A request. A resident Put with an already dirty Directory entry, no private probe, no outer acquire and no inner GrantAck does not clear `no_wait` or require a Directory write. Scheduler can reload that MSHR when its SourceD request is actually captured. The later S2 payload pop, S3 ACK and S4 bank publication keep their own original transaction and pipeline owners.

A clean-to-dirty Put differs: it sets `s_writeback := false`, requiring a Directory write. The write port shares admission with Directory reads. Absence of an outer miss alone does not justify early retirement.

V9 captures the exact native pre-mutation hit+dirty state once and carries the original V6 transaction effects unchanged. `resident_dirty_no_probe` is true only after successful original admission with no miss, private probe or victim. The opt-in `source_resident_dirty_put_request_retirement` reuses the original finite MSHR reservation and releases it at the actual full-packet SourceD request-capture token for that premise. All other requests retain the original publication/source-closure retirement bound. Cache value visibility and command completion continue to wait every actual S4 write and the original ACK. No physical MSHR, payload or pipeline capacity is increased.

Native controls distinguish cold, clean-resident and already-dirty resident packets, retaining exact byte/traffic counts. The pooled/mixed writer integration control exercises the V9 premise with shared finite S2/S3/S4 stages and confirms real early-retirement events alongside final command completion. Public exact-ELF before/after receipts are retained with the prospective export.
