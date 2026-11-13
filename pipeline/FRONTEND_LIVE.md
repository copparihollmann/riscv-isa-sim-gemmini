# Isolated live source frontend

The experimental `pipeline/riscv-isa-sim-frontend-live` tree derives from the
frozen258 private-value epoch and the combined359 functional model. It embeds
the actual saved-Iris `ShuttleFrontend` as a small compiled RTL component for
harts0/1. Spike executes architectural effects at COM. Hart2 retains its distinct
single-issue EX/MEM/WB pipeline with its earlier sequential frontend.

This is an integration milestone. External instruction-memory service is
unknown by default: the first actual cache request raises
`IRIS_FRONTEND_MISS_SERVICE_UNMODELED`. Test fixtures explicitly supply synthetic
first-beat and subsequent-beat periods. These periods, the100MHz fixture clock,
hart dividers and WFI counting choices are not Iris calibration parameters.

## Implemented control

The compiled13-module frontend owns reset PC0x10000, next-PC selection, BTB,
BHT, six-entry RAS, instruction TLB/PMA,64-set/two-way I-cache, replacement
history, replay, RVC expansion, carried parcels and the seven-slot fetch queue.
It starts through reset alone. An explicit nonzero31-bit seed selects unreset
implementation bits; it does not attest physical power-on state.

At each local hart edge, event callbacks finish, CPU control and queue readiness
are evaluated, and the frontend samples one edge. A newly enqueued parcel is
available at the following RRD opportunity. EX/MEM private results precede
architectural COM. Scalar integer ALUs, qualified zero-operand counter reads,
conditional branches, JAL and JALR can overlap across live packets.

MEM branch resolution uses source operands and actual frontend predictions.
It drives real BTB/BHT/RAS ports and redirects. JALR retains its target at EX/MEM
and makes its architectural link available at COM. A taken short forward branch
annuls just its compressed shadow. EX cannot bypass that shadow. The private
value store refuses annulment after another operation has latched or consumed
the shadow's value.

FetchBuffer.scala52 uses packet-wide prediction validity for `sfb_br`, whereas
line54 masks prediction validity per instruction. The adapter consumes the
actual queued `sfb_br`. It does not reconstruct it from per-instruction
prediction. Source F2 predecode removes stale predictions on non-CFIs before
RRD; the directed self-modifying-code case verifies that behavior after actual
JALR predictor training and `fence.i`.

## Precise effects and cancellation

Younger CPU stages are cancelable; accepted cache-refill actors continue.
Completed wrong-path EX work remains completed and marked `squashed`. Pending
COM/WB nodes are canceled, with explicit issue state, cancellation time and
reason. A pending cancellation has zero busy duration. An issued cancellation
retains its elapsed physical span without crediting a completed payload.

CSR reads occur only in successful retirement callbacks and produce the
existing captured-read observations. The directed gate confirms that a
wrong-path counter read creates no guest observation. Actual interrupts are
latched before COM: the precision gate captures an IPI at13069, the peer clears
its line at13070, and the trap reaches COM at13072 under the declared synthetic
fixture. Access-fault and illegal-instruction goldens are unchanged.

The physical refill reader ignores data MPRV, preserves RAM knownness masks,
and refuses device/hole routes. This first RTL peer requires fully known
instruction-refill bytes; unknown padding produces an explicit model refusal.
The precision guest explicitly initializes the complete last-TCM cache line
before its existing boundary-fault test. The earlier guest remains unchanged.

Other scalar operations, data-memory operations, FP, RVV and VME retain
conservative fixture boundaries. Their functional behavior comes from the
inherited combined359 model; their pipeline overlap is not qualified here.
VM, debug/trigger execution and full instruction-cache definedness remain
outside this source frontend scope. Rocket's actual frontend and external
cache/coherence/NoC/serial-memory actors still require integration.

## Reproduction and evidence

```sh
python3 pipeline/frontend_peer_check.py --output build/frontend-peer-new
python3 pipeline/build_native_frontend_live.py \
  --frontend-component build/frontend-peer-new --build build/frontend-native-new
python3 pipeline/frontend_native_live_check.py \
  --binary build/frontend-native-new/spike \
  --uart build/frontend-native-new/libsifive_uart.so --output build/frontend-control-new
python3 pipeline/frontend_irq_check.py \
  --binary build/frontend-native-new/spike \
  --uart build/frontend-native-new/libsifive_uart.so --output build/frontend-irq-new
```

The778 candidate passed the32 qualified functional guests,24 byte-identical
frontend-disabled graph/console replays, seven live control runs, actual
three-hart scalar Zephyr(six regions), mixed scalar/RVV/VME Zephyr(nine regions),
the precise interrupt/trap corpus and native context guards. Its mixed profile
joins all nine actual guest counter regions and preserves cancellations in JSON
and the Perfetto timeline. Receipts are under `build/frontend-live-*`.

The live control corpus covers16 compressed shadows/eight annuls per Shuttle,
JALR link and destination/source aliasing, wrong-path CSR suppression, predictor
training, cache invalidation, deterministic replay, reset seed17 and explicit
3/1 versus11/2 synthetic memory service. Including graph serialization, the
recorded control runs achieve about0.06–0.084 simulated MIPS. The standalone
frontend reaches about1.09million local edges/second. Neither figure predicts
whole-model or application performance.

The additional actual CSR-unit clock proof is
`build/frontend-wfi-clock-proof-v1/results.json`. It confirms that `mcycle`
increments on ungated edges only when pre-edge `csr_stall` isfalse and CY
inhibit isclear. WFI entry counts, parked edges and the wake edge hold, and the
following ungated edge resumes. This is separate from pipeline clock gating
and CLINT time. Current fixtures keep their explicit experimental `count_wfi`
choice; a hardware-derived timing profile must apply the proved policy.

The saved-Iris elaboration is distinct from Ethan's deployed FireSim image.
No image association, complete SoC timing, calibration or held-out +/-2% claim
is made. The source-derived frontend replaces empirical miss penalties, but
the external service still has to come from the actual memory/network model.

The older `shuttle_pipeline.domain` string is retained from the inherited
sequential-fronted metadata in this experimental epoch. `source_frontend`
records the actual enabled implementation and service scope. That legacy
domain label must be corrected before a frontend release is published.
