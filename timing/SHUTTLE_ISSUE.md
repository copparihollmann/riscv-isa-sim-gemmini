# Source-backed Shuttle issue selection

`shuttle_issue.hpp/.cpp` translates the configured Shuttle's two-lane RRD issue
predicates and integer forwarding decisions. It uses **242 scalar control
templates generated from the actual enabled Rocket decode tables**, including
the scalar IEEE, atomics, bitmanip and vector/matrix configuration tables. It
does not classify unknown vector encodings as architectural illegal instructions.
The scalar template may be used only after explicitly resolving the Saturn
vector override; dynamic privilege/CSR/FS/VS legality remains the functional
decoder's responsibility.

The configuration and full 40-character repository pins, 15 source snapshots,
source lines, generated masks/control fields and a bound local FIR excerpt are
in `shuttle_issue_sources.json`. The FIR confirms two RRD lanes and enabled
X-to-M and W-to-L forwarding. That local elaboration is not a deployed-image
build attestation. All unfitted cycle parameters remain null.

Run checks and record compiler/binary/source/artifact hashes with:

```sh
python3 timing/check_shuttle_issue.py
```

The receipt is `build/shuttle-issue/results.json`. The simpler shell command
`bash timing/run_shuttle_issue_tests.sh` runs the same C++ checks. Source
verification reparses the frozen decoder tables and regenerates the expected
header; it also verifies source/line bounds and the FIR identity. Neither test
runner modifies or rebuilds the Spike core.

## Rules that matter for the integration

- Harts 0/1 can issue up to two uops; hart 2 is single issue. This primitive's
  packet selector is Shuttle-specific, not a replacement for Rocket hazards.
- Same-packet dependent ALUs can issue together. Lane 1 moves to **MEM** for an
  ALU producer in lane 0, and to **WB** for a memory producer. A load miss makes
  the latter replay. These stages must not be collapsed into ordinary EX.
- X-to-M forwarding is blocked if the older MEM lane 1 is holding a late ALU.
  Older integer bypass priority is last matching entry, in LL/WB/COM/MEM/EX
  order and lane order. An older ready value must not hide a younger unready one.
- WAW is permitted after a lane-0 ALU; after a memory producer it requires the
  late dependency path. x0 suppresses architectural register hazards.
- The retiming comparisons use raw `rs1` and `rs2` fields before qualification
  by operand-read controls. Even unused LUI/immediate bitfields can select MEM.
- Branch/config consumers cannot use same-packet integer forwarding. One
  memory operation, one branch port and one configuration setter fit per packet.
- CSR, system and exception uops must be youngest. Fence is pipe0-only and
  waits for the drain conditions, but it is not inherently youngest; an
  independent lane-1 ALU can accompany a drained fence. FP execution, multiply,
  divide and vector execution are pipe0-only, but are not automatically youngest.
  FP loads are distinct from FP execution; FP stores use the FP execution path.
- `issueVConfig=false` in Saturn's Shuttle integration. Configuration is not
  automatically pipe0-only; configuration-in-flight and one-config gates apply.
- Frontend prediction tags matter even on non-CFIs. Small-forward branches and
  compressed shadows have separate restrictions. The real frontend, not an
  opcode-only guess, must provide those tags.

`IssueSignals` defaults to **unknown**, not idle. `empty_pipeline_fixture()` and
`FrontendSignals::sequential_fixture()` are explicit test fixtures, never Iris
timing defaults. A known blocking condition dominates unknown irrelevant state;
otherwise a missing input yields `needs_input`. A ready RRD prefix may still have
an unresolved result stage, which the pure-bundle integration guard rejects.

## Required live-adapter work

The primitive does not execute instructions or change the global clock. The
current one-in-flight adapter cannot gain real throughput merely by applying
these predicates: a whole packet held until full retirement still serializes
pipeline latency. Several packets must occupy distinct pipeline stages.

The integration must retain separate producer-ready and architectural-retire
state, and model stage occupancy/backpressure/replay. It must handle precise
traps and interrupt boundaries, cache misses, store visibility, branch prediction
and squash, FP/vector decoupling and the scoreboard. Do not call `step(2)`
unconditionally or divide the clock to imitate superscalar issue.

`pure_integer_bundle()` identifies a deliberately narrow initial execution
subset: two resolved pure ALUs without CFI, configuration, memory, FP or traps.
It permits source-legal RAW pairs but preserves their MEM stage. It is not a
claim that the excluded hardware instructions cannot pair, nor that the subset
alone can meet +/-2%.

For a tentative second fetch, retain/defer its fault until the first instruction
has completed; never attribute that fault to the first PC. Model both instruction
PCs, dependencies, result stages and retire events in graph/profiler output.
CSR cycle/retirement reads and guest memory effects must occur at their actual
modeled event boundaries. No timing calibration or held-out accuracy is proved
by these issue checks.

The C++ checks include the actual smoke loop encodings, dependent and independent
pairs, load-late replay prerequisites, WAW/branch/fence/CSR/config/FP distinctions,
compressed shadows, unused source fields, missing state and all 32x32 integer
producer/consumer register combinations. Current coverage is 2,111 checks.
