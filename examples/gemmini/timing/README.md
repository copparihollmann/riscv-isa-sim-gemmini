# Annotated Spike target observer

This optional C++17 provider converts successful primitive commands into events
for Merlin's generic timing engine. It changes no guest registers, memory,
functional accelerator state, or instruction results. The optional bridge loads
as a separate provider library beside the unchanged functional extension.

These trusted simulator sources are independent of the generated OOT compiler.
Phase 1 receives runtime endpoints through its broker; these sources, vendor
headers and selfcheck fixtures are not candidate inputs.

The observer has two separately pinned target profiles. `stock_u250.json` uses
public `libgemmini` `ea8f7ed7afd68e001fb06ddccad9a023c990961d` and the
`a9a190b9` archive. `fire_aligned_30mhz.json` uses the receiver
`5b1254a7dc72f757442280e7f28ef30542c78533` selected by Gemmini
`63f0b68a68f185a016a2993f2fb32e1661ea9e6c` and the `0af6f26e` archive.
Both have the same generated parameter-header bytes, but their receiver source
bytes differ. `export_config.py` verifies each source and the Spike RoCC header
before exporting. It imports no compiler, kernel, scheduler or model code.

## Standalone source bundle

Export the independently buildable provider from pinned public declarations:

Install Merlin's standalone `merlin-timing` package before exporting. The target
exporter supplies Gemmini sources and facts to its generic bundle builder. Bundle
verification and compilation are implemented once in Merlin; the exported helper
contains those canonical bytes and requires only Python's standard library.

```sh
python3 examples/gemmini/timing/export_config.py \
  --profile stock_u250 \
  --public-library /path/to/public/libgemmini \
  --spike-rocc /path/to/riscv-isa-sim/riscv/rocc.h \
  --bundle-dir /path/to/new/provider-source
python3 /path/to/new/provider-source/build_provider.py \
  --spike-root /path/to/riscv-isa-sim \
  --output-library /path/to/libtiming_provider.so
```

For the selected 30 MHz FireSim build, pass `--profile fire_aligned_30mhz`
and the `software/libgemmini` checkout at `5b1254a7` from the pinned Gemmini
tree. Its exported source bundle contains `fire_aligned_30mhz.json` instead of
`stock_u250.json`. The generated profile pins the 16 GiB board's archive,
source revisions and DTS; its embedded bitstream digest remains unknown because
the source-only handoff excludes that file. Prices and queue capacities remain
unset until Phase 1 measurements and calibration establish them.

The closed bundle contains only the observer, bridge, shared build helper, this README,
generated stock facts and a hash manifest, within one MiB. It contains no kernels
or compiler implementation. `--output` remains available for facts-only export.
The standard-library helper verifies exact membership and hashes, refuses
symlinks and builds with one C++17 compiler process using only the generic Spike
timing API and vendored engine headers. It installs nothing. Output must be
outside the bundle and is replaced atomically after successful verification.
`build_provider.py --verify-only` checks custody without a compiler or simulator.
The manifest binds file contents; external custody must bind the manifest hash.

## Inputs and API

- `HardwareConfig` holds declared geometry and feature facts. Reset activation
  state is optional: the public functional reset does not initialize it.
- `Parameters` contains primitive prices; every used coefficient must be
  explicitly selected. The shipped profile has **no prices or queue capacities**.
- `ResourceBindings` selects generic engine resources. Missing bindings remain
  unknown. Capacities and waiting queues belong to the caller's `ResourceSpec`.
- `required_tokens` reserves scratchpad/accumulator row tokens, three load-state
  tokens, store/execute/preload/PE tokens and four normalization-state tokens.
- `observe_command(pc, funct, rs1, rs2, earliest)` returns the engine's issue,
  start and ready times. `observe_fence` drains known outstanding work and adds
  the separately priced fence. Unknown prior work stays unknown.

Local read/write and configuration hazards persist until completion. Row tokens
are a conservative dependency granularity, not a bank-conflict simulation.
The observer bounds per-command row processing; exhausting that host work budget
reports unknown semantics rather than silently dropping work.

The observer follows load states, block strides, pixel expansion, zero fills,
full/shrunk accumulator widths, dataflow and transpose state, persistent PE
contents' shape bounds, output accumulation, pooling windows and normalization
readouts. Non-RESET normalization reads local data without writing DRAM. FSM
instructions, including their configuration instructions, violate the policy;
the primitive third load channel (funct 14) remains admitted.

The bridge marks custom counter instructions with destination writeback unknown:
the pinned functional extension returns dummy/random data. Counter-derived guest
control/data is outside the qualified domain. Side-effect-only counter commands
can be priced, but their return values never supply calibration labels.

## Prices and shared memory

For each primitive class, latency and occupancy use the explicitly selected
affine price `cycles + bytes × per_byte_cycles + padded_macs × per_mac_cycles`,
rounded upward. A coefficient is required when its quantity is nonzero. None,
RELU and normalizing readouts have separate classes. This is a primitive event
model, not a measured hardware timing claim or a whole-program correction.

`TransferHook` receives ordered row regions and returns shared memory tokens,
resource demands and a minimum latency. When installed, it owns cache/DRAM
modeling; functional extension byte accesses must not be charged again. Without
a hook, explicit DMA rates and bindings provide isolated transfer reservations.
Aliased resource bindings share their longest reservation; serial subphases
require a corresponding explicit price.

`bridge.cpp` adapts the neutral `timing/provider.hpp` ABI. Its hardware keys are
`target.hardware.*`, price keys are `target.prices.<class>.<field>`, and resource
names are `accelerator.{config,load,store,execute}`. The installed shared-memory
bridge owns DMA reservations; the standalone observer additionally supports DMA
bindings. The bridge exports incremental counts and unresolved reasons through
host callbacks. At construction it registers the complete implemented counter
and primitive-class vocabulary with zero counts, including diagnostic classes.
Unsupported names remain absent; zero therefore means observed absence only
for an explicitly registered feature.

Requested DMA bytes describe command payload, not physical DRAM transactions.
Nominal padded MACs describe array-shaped work; shape MACs are a support bound,
not a count of nonzero arithmetic. Queueing, resource overlap and read/write
hazards come from the generic engine. Physical banking and intra-command phase
overlap are not independently resolved by this provider.

## Explicit staged scheduling selection

`target.scheduling.version = 2` separately selects `staged.hpp`. The legacy
selection remains unchanged. This selection distinguishes reservation admission,
controller issue, FIFO consumption, effects and retirement. It requires explicit
LD/EX/ST reservation and controller-queue capacities, DMA command-tracker
capacities, six `accelerator.{issue,controller}.{load,execute,store}` resources,
and issue latency/occupancy prices. Missing prices remain unknown.

A pending solitary PRELOAD survives a fence and starts only when its following
execute command is observed. Non-garbage destination tags retain their reservation
through the following compute result, rather than retiring at descriptor
readiness. Admission timestamps are clamped to the CPU issue frontier, including
after a fence. Load/store configuration reservations release on controller issue;
their configuration effects remain ordered at controller consumption.

`require_fenced_phases = 1` restricts the initial model domain to explicitly
fenced controller phases and rejects a COMPUTE-to-PRELOAD transition without a
completion fence. Such transitions require independent cross-controller bank or
overlapped mesh/tag semantics. The command-order audit continues when prices are
unknown, and an observed fence remains ordering evidence even when its cost is
unknown. These refusals affect native timing, not complete instruction counts.

`allow_dependency_ordered_phases = 1` additionally admits a controller phase
when the actual selected local-storage hazards prove completion of every prior
effect from the other controllers. `DependencyPhases` reconstructs the relevant
selected reservation-station ranges from actual operands and stride state.
It retains exact event ancestry, rather than treating a later DMA sequence
number as proof that unrelated earlier DMA completed. Same-LD/EX queue order
proves issue order only; same-ST dependencies wait completion. PRELOAD source
feed dependencies and its later compute output/tag retirement remain separate.
An EX configuration explicitly drains prior EX retirement. Configuration, PE
and cache tokens do not manufacture cross-controller completion ancestry.

The source authority is the selected `ReservationStation.scala` allocation,
cross-queue dependency, issue and completion logic, together with the selected
execute-controller drain and output-tag logic. This checked subset still
refuses independent work sharing unmodeled banks or packet resources. A
successful ancestry check alone supplies no price or held-out qualification.

`allow_disjoint_scratchpad_banks = 1` can also admit EX/DMA phases using
separate physical scratchpad banks. The caller must bind the selected
`scratchpad_bank_rows`. Independent rows within one bank do not qualify. LD/ST
still share external DMA paths; all accumulator aliases remain one conservative
conflict class rather than inferred independent ports.

`conservative_local_store_holds = 1` selects a broader explicit reservation
abstraction. It requires `scratchpad_bank_count`, `scratchpad_bank_rows`, one
`accelerator.storage.scratchpad.<index>` resource per selected bank and an
`accelerator.storage.accumulator.all` resource. Actual local read/write tokens,
including PRELOAD's B feed, reserve each touched store through
`max(effect_latency, occupancy)`. Unknown terms keep these holds unknown.
PRELOAD descriptor readiness still does not retire its output tag.

Whole-command holds deliberately serialize port use during some intervals when
the RTL could overlap work. Accumulator ports/aliases collapse into one
conservative conflict class; this does not claim the hardware has one port.
The external-memory model similarly uses an explicitly selected aggregate
shared resource and approximate cache/coherence policy. Future reservations
can conservatively postpone independent earlier requests. These are declared
model approximations, not exact packet or bank arbitration. Unchanged held-out
error, ordering, family and coverage gates decide their usable timing domain.
Command payload counts and modeled cache-line traffic remain distinct.

The closed provider bundle includes `staged.hpp`. Its version-2 source manifest
declares `reservations.hpp` as an additional generic runtime header, and the
builder pins it alongside the original ABI/engine headers before and after
compilation. This provides source custody, not timing qualification.

These mechanisms and the synthetic tests do not establish accelerator timing
qualification. The selected source/fact correspondence, supported semantic
subset, all prices and held-out timing gates require separate review. Resource
breakdowns in native reports remain explicitly scoped whole-trace diagnostics;
they must not be summed into counter-window costs or physical traffic.

## Verification

Run bounded independent C++ and source-pinning checks:

```sh
python3 examples/gemmini/timing/tests/run_tests.py \
  --engine-include /path/to/merlin/packages/merlin-timing/include \
  --spike-root /path/to/riscv-isa-sim \
  --public-library /path/to/public/libgemmini \
  --build-dir /path/to/new/task-temporary-directory
```

These tests use artificial prices and small independent geometry under
AddressSanitizer and UndefinedBehaviorSanitizer. They test decoding, transfers,
hazards, overlap, unknowns and the neutral bridge. They launch no simulator and
do not qualify the model's hardware fidelity. The stock profile records pinned
archive/bit/header identities and the unresolved elaboration-source lineage;
calibration and independent simulator qualification are still required.

For a bounded native integration check against an already built annotated Spike,
functional extension and provider library:

```sh
python3 examples/gemmini/timing/tests/run_native.py \
  --spike-root /path/to/riscv-isa-sim \
  --spike-build /path/to/build-with-timing-source-manifest \
  --functional-extension /path/to/libgemmini.so \
  --timing-provider /path/to/libtiming_provider.so \
  --build-dir /path/to/new/task-temporary-directory
```

The freestanding ELF uses raw primitive instructions with an independent scalar
reference for a signed 4×4 matmul and scratchpad DMA roundtrip. It initializes
every used configuration, compares ordinary and annotated execution, and checks
exact transfer/work counts and complete accounting inside a counter window that
ends before printing. HTIF mailboxes are asynchronously host-modified RAM;
post-window console polling and exit remain unqualified external I/O, so the
whole trace must remain incomplete. Each process has a
30-second timeout and a one-million-instruction bound. Artificial prices and
resource capacities test integration only; they establish no cycle accuracy.
