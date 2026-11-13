# Interpreting the finite source-capacity example

The immutable example uses the older28a0 model and its own exact fixture;
it is not an execution on the new selected7bd5 runtime. Four compute regions
each complete4096 logical MACs inside their captured global CSR windows.
The conditional source ceiling is256 MACs per compute-hart clock edge.
The resulting fractions are modeled rate divided by that source ceiling,
not measured physical utilization.

INT8 and E4M3 run sequentially with different initialization, instruction/data
cache histories and modeled effective service costs. Their approximately0.75%
and7.5% fractions do not show that hardware FP8 is ten times faster. They are
observations of this program and fixture, with finite source and calibration
coverage. Cross-format comparisons require matched preparation and independently
validated timing.

The208-byte denominator counts architecturally retired requested data bytes;
it excludes128 VRF row-move bytes and instruction fetches. It is not DRAM/L2
traffic. Physical bandwidth, the memory-ceiling slope, a physical roofline and
stall attribution remain unavailable. See the exact JSON, source provenance and
review under build/full-graph-VME-source-capacity-overlay-v1 and its closure.
