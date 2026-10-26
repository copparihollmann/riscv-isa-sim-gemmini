# Posted source software custody

`PostedTimeline::Token` names one monotonic original completion identity. Its
record remains alive while any callback, dependency or source value holds the
handle. The timeline separately roots every unresolved record, including one
whose producer lost its last handle. Only an actual dispatched `complete()`
releases that unresolved root. Completed unreferenced records can then be
reclaimed; retained records still report their original completion cycle.
Tokens from another timeline and altered identities are invalid.

The configured token budget bounds live records. It is a software custody
limit, not an accelerator queue, MSHR or physical transaction credit. The
configured dispatch budget bounds consecutive callbacks without an explicitly
registered original source completion. Polling, intermediate beats and elapsed
time do not reset it. The target registers each original command's final
completion at admission; its existing retirement mechanism remains responsible
for completing it. Total dispatched callbacks remain monotonically counted,
with integer overflow checked separately. Missing producers and real liveness
failures remain unresolved. No checkpoint completes a dependency or releases a
hardware resource.

Native reports expose live/peak records and maximum callbacks between original
source completions. Native observer and provider must be built with matching
headers because token handles carry shared custody. This implementation changes
software representation and liveness accounting, not source timing or capacity.

Focused contracts are in `test_posted_timeline.cpp` (long stream, retained
cycles, lost obligations, reference limits, identity, actual completion versus
polling) and `posted_history_test.cpp` (66,000 original source commands with a
16-callback liveness bound and unchanged modeled queues).
