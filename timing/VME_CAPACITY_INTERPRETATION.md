# Reading the six-ROI VME capacity example

The [overlay](../build/full-graph-VME-source-capacity-overlay-v1/overlay.json)
and [standalone chart](../build/full-graph-VME-source-capacity-overlay-v1/overlay.svg)
compare logical model work with a conditional source ceiling. **The larger FP8
fraction is not evidence that Iris hardware runs FP8 ten times faster than INT8.**

The program executes UINT8 first and E4M3 later. Each compute ROI contains four
32×32×1 matrix operations, followed by row readout and output storage. Setup,
instruction-fetch/cache history, shared contention, scalar control, modeled
service costs and the selected fixture affect its window. This is one sequential
program, not a randomized or matched hardware INT8-versus-FP8 throughput test.
The full graph uses the preserved **28a0** native and
[`iris-empirical-priority-28a0-v2`](../calibration/empirical-priority-28a0-runtime-v2/runtime.fixture),
not the later hybrid7bd5 default. Changing the default does not change this proof.

The actual captured global windows are 2126/2101 model edges for UINT8 on
harts 0/1 and 213/210 for E4M3. Guest `mcycle` differences are separate quantities.
Each compute ROI has 4096 logical MACs, and all four credited model actors finish
strictly before its end read. Canceled speculative actors receive no logical
credit. Hart 2 runs an ordinary RVV producer and has no VME ceiling or fraction.

The formula is `logical_MACs / (256 × potential_core_edges_in_ROI)`. The
[source report](../build/throughput-limits-source-v3/report.json) establishes
256 cells per accepted array edge on each compute hart, subject to its recorded
operand, shape, acceptance, hazard and clock conditions. FP8 and INT8 share this
array; their ceilings are not summed. The fractions are conditional model-rate
coordinates, **not observed physical utilization**. A value above 100% must remain
visible as an inconsistency; the overlay does not clamp it.

The bound 28a0 [parameter packet](../calibration/empirical-priority-28a0-runtime-v2/parameters.json)
and [runtime binding](../calibration/empirical-priority-28a0-binding-v2/runtime-binding.json)
describe effective services. In that fixture, compute FP8 has an additional
setup 1/work 0 rule; INT8 has no explicit family override and retains its native
work-duration policy. Row moves use setup 1/work 0 and zero uses setup 3/work 0.
Compute instruction-refill services use 32 additional L1-miss cycles; the common
outer proxy is 545.732041126 cycles with 461-cycle launch interval. These are
fixture-bound effective costs, not identified physical unit/cache/DRAM latencies.
The packet marks integer projection and extrapolation outside observed work
domains as unqualified. The selected native's source/timing/whole-model/±2%
certificates remain false. The overlay binds the exact fixture bytes and actual
run; it adds no fit or hardware observation.

Each compute coordinate is 19.6923 MAC/requested-data-byte: 4096 MACs divided
by 208 ROI-local architectural bytes, comprising 128 vector-output bytes,
72 scalar-load bytes and 8 scalar-store bytes. Operand preparation is outside
these ROIs. The 128-byte VRF row move and instruction-fetch requests are excluded.
Accepted timing-intent bytes use a separate ledger, even though their total is
also 208 here. Neither ledger measures L2 or DRAM traffic. Physical bandwidth,
the memory-bandwidth slope, physical roofline, physical MAC completions and stall
causes remain unknown.

The [independent review](../build/full-graph-VME-source-capacity-overlay-review-v1/report.json)
checks the source conditions, Decimal fractions, clock-window convention, byte
scopes and 16 adversarial controls. The
[closure](../build/full-graph-VME-source-capacity-overlay-closure-v1/report.json)
preserves the new source and artifacts without editing the original profile.
