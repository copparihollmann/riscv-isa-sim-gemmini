# Distinct pipelines on all three harts

The fifth isolated candidate is native
`91c404614db4c86247777d16cce4d8a18c68d27f38ba2b63b235aae2254684ee`,
matching finite-UART plugin
`8b78272d399c5cddaacb5373201008926dcf1a07945a2792b0aacbc4c04b8e87`.
Its source is `pipeline/riscv-isa-sim-rocket-pipeline`, built in
`build/spike-rocket-pipeline-v3`. It adds an explicit Rocket domain to the
frozen e060 Shuttle counter pipeline:

```
shuttle_pipeline pure-integer-rvc-counter-sequential-frontend
rocket_pipeline pure-integer-rvc-counter-sequential-frontend
```

`pipeline/heterogeneous.fixture` is the complete synthetic test fixture. All
three physical harts execute on the same clock/event/device timeline. Shuttle
keeps its two-lane/four-packet source rules; Rocket issues one instruction per
hart edge with three EX/MEM/WB packets in flight. No clocks are divided to
manufacture IPC. The primary package and prior isolated epochs stay unchanged.

## Rocket source contract

Pinned Rocket source `fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0` establishes:

- `RocketCore.scala:320-324`: decode/retire width1.
- `RocketCore.scala:463-480,555-565,661-679,735-749`: ALU bypass and the
  distinct EX/MEM/WB registers. Pure ALU results can bypass from EX.
- `RocketCore.scala:353-354,962-964`: zero-operand S/C is rewritten to CSR.R;
  CSR reads occur at WB. They do not inherit Shuttle's global CSR EX drain.
- `RocketCore.scala:1040-1055`: CSR RAW/WAW dependencies block ID while a
  producer is in EX/MEM. `RocketCore.scala:846-855,1372-1393` permits the consumer
  at WB via RF write-through. CSR results are never exposed at EX.
- `IBuf.scala:86`: the same default RVC expander is used. The admitted pure
  compressed ALUs retain the existing exhaustive saved-module expansion proof.

The30 admitted base integer operations use the exact shared pinned Rocket
IDecode/I64Decode rows already audited for Shuttle. `pipeline/audit_rocket.py`
checks those controls and freezes complete source snapshots, hashes, repository
SHAs and line citations. Frontend/cache/branch/vector timing is not inferred.

An instruction accepted at ID edgeR has EX ready atR+D, MEM atR+2D and WB
retirement atR+3D, with positive-duration nodes for each stage. Counters become
result-ready at their WB node. Architectural effects execute through actual
Spike handlers in program order at WB. Pending interrupts and fetch faults are
captured precisely and retire no instruction. Unsafe contexts, debug/halt,
single-step and triggers retain the existing guards.

Rocket's safe direct-RAM prefetch checks each required byte at a guest page
boundary, since sparse memory uses separately allocated host pages. Normal MMU
fetch still performs access/fault checks. The native test fetches an actual
32-bit instruction across separate host pages, rejects an unmapped trailing
halfword, and verifies the original strict-pointer behavior remains the default
for prior Shuttle domains. This avoids a conservative fallback at0x80000ffe.

## Verified scope

`build/rocket-pipeline-v3-review/results.json` binds14 successful gate groups.
The independent CSR corpus checks32 Rocket cases alongside64 Shuttle cases
and192 actual reads, including EX/MEM CSR interlocks, independent overlap,
back-to-back reads and COM-versus-WB readiness. The integer corpus proves512
dependent and512 independent Rocket operations issue one per hart edge, checks
all30 base ALUs and19 compressed groups through independent integer oracles,
and tests source pairing, precise traps/IPIs, timers and boundary fetch faults.

Live8+3, memory6+7, UART12, source forms/admission, nonlinear wrap/inhibit and
off-hart memory responses pass. All32 unchanged functional goldens pass.
Three legacy pipeline modes preserve exact e060 guest output, counter
observations, event-clock totals and architectural retirement. Actual three-hart
Zephyr scalar6 and mixed9 regions pass, including the explicit VME context ABI.
The captured-read profiler joins all9 mixed regions.

The IPI pulse producer has an explicit `IRIS_ROCKET_PULSE` test define that omits
its old NOP: a genuinely pipelined Rocket now needs three stages plus draining
for that intervening NOP. The original default stimulus remains unchanged.
The strict capture<clear<exception-retirement assertion remains unchanged;
failed earlier attempts and their raw traces are preserved.

The original256 debug/fitting probes now match all6 source RTL rows exactly:
Shuttle dependent263/independent136 cycles, Rocket259/259, and the source-visible
IR deltas256/257. Read-only alias controls also match. These old observations
are not held-out validation. Separate prediction receipts freeze candidate,
ELFs, fixtures, checksums and counter contracts before new RTL observations or
before agent unblinding, with those roles distinguished explicitly.

## Review and limitations

The five-file delta on e060 is
`build/rocket-pipeline-v3-review/rocket-on-e060.patch`, SHA256
`b104fbfb13536a229a47c4eba894921ad34938ebe42193f6375464409b69be05`.
It changes the live adapter/graph, adds Rocket issue/stages and extends the safe
prefetch helper with an explicit split-page option. It applies cleanly to the
frozen e060 source. The closed review epoch is
`build/rocket-pipeline-frozen-91c40461`.

```sh
python3 pipeline/freeze_epoch.py --snapshot build/rocket-pipeline-frozen-91c40461 --verify
python3 pipeline/check.py --rocket-pipeline --help
```

The frontend remains an explicitly sequential fixture. Branch prediction,
cache/coherence state, replay/flush, loads overlapping pipelines, broader scalar
execution, asynchronous Saturn/VME/FP sequencing and calibrated NoC/serial-TL
costs remain required. Routed vector/translated memory retains named refusals.
The source clock convention and captured CSR reads do not qualify these missing
costs. Full functional/RTL/timing certification and held-out +/-2% remain false;
Ethan-image association remains unverified. No FPGA action occurred.
