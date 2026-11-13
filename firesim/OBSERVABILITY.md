# Candidate image observability

The selected inventory is `build/firesim-observability-archived-driver-v3/report.json`,
SHA256 `e0cefa3a9fc03e40755eea4b89cd9970ad75690f361bf400a5f9887fea68d712`.
It binds image archive `9bbe1f12...`, original archived executable `8f78167b...`
and its new runtime bundle `5457de1e...`, source snapshots and regular archive
members. The image's bitstream bytes match the archived build's `.bit` exactly.
Co-location with generated RTL and Vivado collateral does not establish all
original source inputs, runtime libraries or the currently loaded image.

The old `candidate-v2` inventory and `64b1b64f...` executable remain preserved.
That executable changes the TSI loader from `has_host_mem=false,offset=0` to
`true,-0x80000000`; only its `entry()` function differs. Initial managed jobs
select the original executable rather than silently changing loader behavior.
The current generated header also has the changed loader arguments. Constructor
classes are independently visible in the archived executable's entry callsites;
its MMIO map has not yet been independently matched to that header. These
differences and unknowns are explicit in the new inventory. Neither inventory
certifies a loaded image or timing calibration.

The generated header constructs eight widgets: master, peek/poke, reset pulse,
UART, TSI, FASED memory model, clock and loadmem. It constructs no TracerV,
AutoCounter or synthesized-print bridge. Generic implementations of those
classes occur in the driver binary, which does not prove their instantiation.
Do not enable nonexistent hardware instrumentation through runtime flags.

FASED exposes sixteen aggregate read-only values: ten outstanding-request
histogram buckets, read/write beat and request totals, and read/write response
errors. The inspected driver supports periodic `+profile-interval=` samples
written to `memory_stats0.csv`. New private jobs propose an interval of
1,000,000 target cycles, recorded in their actual configuration/launch arguments.
These are aggregate samples, not exact per-hart or per-region traffic attribution.
Their timebase must be interpreted using the actual clock bridge configuration.

The inspected register map has no latency-histogram or address-range-counter
ports. An empty `latency_histogram.csv` created by the generic driver is not a
measurement. Writable read/write latency and outstanding-limit settings are
excluded from the periodic CSV: that file cannot establish selected runtime
memory latency. Source defaults and previous invalid/all-ones MMIO reads remain
unqualified. No clock or memory timing setting is changed for observability.

Before setup, freeze this audit and the job capture checklist with the exact
runtime/HWDB/plusargs, ELF/toolchain/source identities and fitting/holdout role.
Capture all raw manager streams, UART, per-region guest counters/checksums,
completion/failure markers, trial samples/variance, phase times, available
driver/statistics files and explicit missing instrumentation. Preserve the
full owned lifecycle and archive after cleanup under CAMPAIGN_POLICY.md.

`prepare_managed_campaign.py` freezes an augmented checklist, actual configs,
source snapshots and the private setup observer into each new job. The current
campaign is `runs/fpga-managed-batched-v5/campaign.json`: first the 12-region
smoke, then one 6,750-region fitting ELF with five trials. `run_campaign.py`
verifies both jobs before execution, uses the allocation-checked runner and
allows the broad run only after smoke cleanup, archival and guest validation
pass. Its default invocation verifies locally and does not contact hardware.

The observer times actual rsync calls and the fixed installed programming
helper separately. The latter includes transport, reset and Vivado; the outer
flash method also includes unpacking and script transfer. Nested times must
not be added. No staging optimization has been justified by measurements yet.
`analyze_campaign.py` verifies the archive and every inventoried member, checks
guest phase/parent/trial/completion identities and retains all trial samples in
a separate output directory. Capture and guest failures remain distinct.
