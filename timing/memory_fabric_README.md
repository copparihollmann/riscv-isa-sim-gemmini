# Source-coupled Iris memory fabric (development)

This separate component joins the saved Rocket data cache, its real tile master
arbiter and width widget, both halves of the Rocket asynchronous crossing, the
complete configured NoC, all four inclusive L2 banks, the inner/outer buffers,
bank binder and cache cork. The source is the standalone saved IrisConfig FIR
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`.
No association with Ethan's programmed image or whole-workload accuracy is
inferred. Primary Spike, existing timing engines and frozen component packages
are unchanged.

`memory_fabric_extract.py` copies selected original instance blocks and their
reachable RTL modules. Source port expressions, including source-ID/address
slices, are retained. `memory_fabric_graph.py` follows actual hierarchical port
connections and transparent aliases: its first graph has 730 joined nets across
seven source components. The public composite exposes 263 external physical
input nets and 1,046 source-component output pins. A joined input is unavailable
through the external-input lookup; cache ready or L2 request signals cannot be
replaced by an observed value.

`MemoryFabric::evaluate` settles peer outputs and connected inputs to a fixed
point without a clock edge. `sample` returns those preedge outputs. `commit`
advances the explicitly selected Rocket and/or uncore domains once, with every
peer retaining the inputs settled before any peer commit. There is no extra
adapter, NoC-link or fixed-point-iteration edge. The saved reference uses 500 MHz
source edges; independent domain events remain explicit in the API. An outer
scheduler must supply the source clock/reset relationships rather than derive
cycles from host wall time.

Every external input carries a value and a known-bit mask. Unknown bits,
out-of-width values, malformed phases and failure to converge refuse the edge.
The strict input contract is deliberately conservative, including inactive
payload pins. Supplying a concrete test fixture or two-state reference pin does
not establish architectural definedness for unknown hardware state. Numeric
outputs alone certify neither an internal unreset RAM bit nor an entire
four-state knownness model. The source-qualified Shuttle invalid replay-head
refusal is preserved in its separate cache SDK; Shuttle caches are not connected
in this first composite.

The external four-bank memory interface is **after** the real cork. No serial-TL,
DRAM-controller or FireSim memory-service latency is invented. Without supplied
external responses a miss stays outstanding. The independent semantic test
uses an explicitly synthetic memory actor with a three-edge minimum response
spacing and an integer address-to-data formula. Those timings are test inputs,
never fitted Iris parameters. TCM, scratchpad, peripherals, other harts, the
Rocket instruction/vector producers, and the external memory hierarchy remain
external physical peers in this stage.

Separate host-wrapper derivatives are necessary for multi-SDK use. Verilator
5.052 has a thread-local active context; the old standalone wrappers did not
select their owner on every entry. With interleaved libraries this could execute
NoC plusargs against an unrelated context. `memory_fabric_context_scoped.py`
replaces only host-wrapper objects, selects the owner during operations and
restores the caller on success/error, construction, destruction and move
assignment. All saved RTL model and runtime archive members stay byte-identical.
The derivative has its own source identity; historical component evidence is
not relabeled. Verilator's shared per-thread RNG still prevents an unrestricted
claim that arbitrary unreset histories commute across evaluation orders.

Current development evidence:

- `build/memory-fabric-coupled-native-v4/check.stdout`: 1,805 independent checks
  across four reset seeds. A cold refill traverses the actual width/CDC/NoC/L2
  path and returns eight 64-bit service beats as two 256-bit cache beats. A warm
  store/reload and a subsequent instruction-side Get check updated data through
  a real B probe and two 256-bit dirty C beats. No external service means no
  fabricated CPU completion.
- `build/memory-fabric-context-sdk-v2/noc/order.stdout`: 73,443,582 qualified
  output comparisons over three source peers and varying construction and
  interleaving orders; 1,626,552 caller-context restoration checks. Every entry
  begins in an unrelated context without NoC plusargs.
- `build/memory-fabric-context-checks-v3/report.json`: four actual-reset NoC
  reference replays (270,288 edges), same-edge ready revisions, and the existing
  lifecycle/snapshot checks retain the independently frozen defined-field
  digests under the new host wrapper.
- `build/memory-fabric-reference-v1` and `memory-fabric-observer-v1`: a separate
  complete saved-RTL build, with only read-only visibility of 1,309 physical
  signals. A three-hart architectural control and closed-boundary comparison
  are being qualified; these do not yet provide a completed acceptance capsule.

The build inputs, graphs and intermediate failures remain in separate versioned
paths. This is neither the published full simulator nor a calibration, speed,
held-out +/-2%, complete-knownness, full-RTL or deployed-image certification.
