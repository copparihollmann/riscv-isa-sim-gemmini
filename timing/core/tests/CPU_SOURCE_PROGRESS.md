# Original scalar completion as a software work checkpoint

The posted work guard counts callbacks since the last actual original source
completion. A scalar initialization prefix can contain millions of ordinary
instructions before the first accelerator command. Bounding its entire history
because only target commands were registered confuses software work with a
hardware queue or a stalled source.

The native committed instruction path now registers the token already owned by
its original execution/result stage. Only that token's actual dispatched
completion advances the existing work checkpoint. Fetch fragments, admission,
partial responses, polling and time do not advance it. The CPU's modeled
latency, scalar in-order admission, values, writeback assumptions and resources
are unchanged. No result is completed early and no hardware capacity changes.

The source ingress diagnostic likewise counts acceptance only when the original
request actually accepted, rather than incrementing after a timeline failure.
Architectural command counts remain independent.

`test_cpu_source_progress.cpp` exercises a long ordinary scalar prefix with a
small software work guard, asserts completion is unavailable at admission and
before its ready edge, and preserves exhaustion when callbacks poll without an
actual completed result. It does not qualify physical CPU timing.
