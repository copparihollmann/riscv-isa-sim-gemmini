# Source counter edge policy, isolated review epoch

The candidate native is `8930257d62c58d53c3f1f9c9503b953806aaa69a04f0d72ed613385b2ec1e34c`;
its matching clocked UART is
`cde52d1646ba9493903dec78438513acba606ae19a4c525e739eaa4e746d667e`.
The source is `pipeline/riscv-isa-sim-observe`, built in
`build/spike-counter-policy-v2`. Primary5e6 and the historical646/680 snapshots
remain unchanged. Publication requires coordinator review.

## What changed and why

The model defines an instruction node's `end=T` as its local retirement edge.
Its guest CSR evaluation samples counter state immediately before that edge's
update. Global and device clocks continue advancing normally. Each mcycle clock
advance retains the value before its final local edge, including wrap, inhibit
and optional WFI clock gating. The simulator stamps that edge; every timed
counter read requires its stamp to equalT. An off-edge or stale sample produces
a named refusal instead of a guessed value.

This convention implements the pre-edge registered read observed in actual
source-matched CSR units and the whole CPU. The frozen component proof is
`build/pipeline-csr-proof-closed`;4582 independent edge checks cover commands,
aliases, write priority, inhibit transitions and wrap. The whole-CPU proof is
`build/csr-phase-proof-v2/report.json`:152 edge samples,48 returning counter reads
and32 Shuttle RF writes confirm pre-edge COM reads and WB writeback one edge
later. Its448-byte TSI signature matches the original scalar experiment exactly.
These refer to the saved standalone Iris FIR, not an attested Ethan image.

Shuttle passes encoded zero-operand CSR.S/C commands unchanged to CSRFile.
The model therefore writes old B00/B02 values back for Shuttle CSRRS/CSRRC
rs1=x0 and CSRRSI/CSRRCI uimm=0, overriding that edge's increment. Rocket rewrites
these to CSR.R. C00/C02 are read-only aliases with no counter write case.
Nonzero encoded rs1 holding value zero remains a write on both core types.
Explicit counter writes retain priority even while counting is inhibited.
Architectural retired-instruction totals remain distinct from visible minstret.

CSRFile uses the registered mcountinhibit value before a concurrent inhibit
write. Iris retirement now snapshots that value before instruction execution;
inhibit-set counts its own edge and inhibit-clear retains the old inhibition at
its edge. The existing implementation used the post-handler value for minstret
and functional mcycle. The new native corpus exposes that difference directly:
the old689 candidate produces set/clear deltas1/1 instead of2/0, and reports
12346 after clearing an inhibited explicit12345 write instead of12345.
That failed behavioral control is preserved with exact binaries and outputs.

No broader zero-operand side effects are inferred for FCSR, VCSR or counteren.
Their asynchronous/definedness semantics require separate proof.

## Captured reads and profiling

Every successful guest counter evaluation records hart, PC, original raw word,
CSR, value, destination, discarded-result flag, per-hart sequence, owning node,
read timestamp and `model_retirement_edge_pre_update` phase. Internal/peek
evaluations are excluded. A trapped instruction discards its buffered reads;
architectural retirement binds successful observations to the completed node.
Rd0 evaluations are retained explicitly and excluded from guest boundary matching.

The profiler joins actual guest values to these observations. It supports writes,
wrap, inhibition and nonlinear offsets without assuming `mcycle=T/divider`.
Ambiguous boundary values fail closed. Actual mixed Zephyr9-region profiling
passes at `build/counter-policy-v2-mixed-profile` with its process receipt in
`build/counter-policy-v2-profile-check.json`.

## Evidence and remaining timing gap

`pipeline/review_counter_policy.py` verifies12 candidate-bound gate reports and
the independent source/whole-CPU proof artifacts. Passing gates include unchanged
32 functional guest goldens,11 directed pipeline runs plus3 fixture refusals and
native guards, live8+3, memory6+7, UART12,20 counter forms/60 intervals/120 reads,
45 nonlinear reads/9 regions,75 inhibit/memory-edge reads and actual three-hart
Zephyr scalar6/mixed9 regions. The asynchronous response corpus contains8 hart2
responses on odd base ticks followed by correctly aligned even-edge CSR reads.

The strict new source-contract checker independently decodes the unchanged
scalar ELF, all256 ADD bodies, brackets, mailbox/checksums and corruption controls.
It preserves the original collector and failing original RTL receipt. Both the
original writable-counter ELF and the derived read-only-alias ELF now match
source-visible retirement deltas:256 on Shuttle B02 versus257 on C02 and Rocket.

| Probe, Shuttle0/1 | Reference cycles | Candidate cycles | Signed error |
| --- | ---: | ---: | ---: |
| Dependent256, B00 |263|266|+1.141%|
| Independent256, B00 |136|139|+2.206%|
| Dependent256, C00 |264|267|+1.136%|
| Independent256, C00 |137|140|+2.190%|

Rocket remains777 modeled versus259 actual cycles (+200%) with the conservative
three-cycle fixture. The model's Shuttle physical read spans267/140 exceed
the observed264/137 by3 edges. Counter policy accounts for the source pause;
it does not remove this pipeline-boundary gap. The next implementation must
overlap legal counter operations through real pipeline stages, followed by
Rocket/frontend/cache/vector/VME work. No constant is subtracted or fitted.
Calibration, full RTL certification and held-out +/-2% remain false.

## Reproduction

```sh
python3 pipeline/build_native.py --source pipeline/riscv-isa-sim-observe --build build/spike-counter-policy-v2
python3 pipeline/check_counter_forms.py --binary build/spike-counter-policy-v2/spike --uart build/spike-counter-policy-v2/libsifive_uart.so --output build/counter-policy-new-forms
python3 pipeline/check_counter_edge_cases.py --output build/counter-policy-new-edges
python3 pipeline/review_counter_policy.py
```

The full build overlay is
`79feb0e8047c85ec6f43ff8ba91604a5ca40044a69ee03d53b6e1ee8b75e0b5a`.
The reviewable delta on frozen5e6 is
`build/counter-policy-v2-directed/pipeline-on-parent-epoch.patch`, SHA256
`c72a5b55a17d0ae5152ccef1a53c75ede16514091f0a6458c34aa66c25fc4202`.
Each gate receipt records its exact command, input and artifact digests. Use new
output directories after changing any model, source, ELF or fixture.
