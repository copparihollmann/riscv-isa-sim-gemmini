# Optional FADD per-EG native actor

Frozen capsule: `build/FADD-EG-actor-corrective-frozen-v2`. Its clean
`FADD-EG-on-C12.patch` applies to the exact frozen C12 native source. No
existing native tree, fixture, provider, current pointer, or hardware input
was modified. Enable explicitly with:

```
empirical_fadd_eg compute-HSD-fullVL-flags0-COMplus1-v1
```

The admitted architectural instruction is compute-hart `vfadd.vv`: M-mode,
unmasked full VLmax, aligned LMUL1/2/4/8, IEEE H/S/D, RNE, defined operand
bytes, known FFLAGS and an already Dirty FS field. Hart2 retains the parent
functional path. Architectural unsupported geometry/context still refuses;
guest errors include actual hart, PC/raw, VL/SEW/LMUL, frm and flags.

The actor uses the independently source-qualified VDQ4/IQ3/sequencer/FMA4
controller. Future COM slots are reserved with a bounded queue forecast.
Only successfully committed, qualified commands enter the backend one edge
after COM. This COM+1 CPU bridge is explicit and remains unqualified; no
fitted timing constant or existing FADD setup/work coefficient is charged.

The functional instruction executes through real Spike semantics inside its
actual COM callback. Earlier committed private EG versions provide logical
operands. The oracle's physical VRF and FCSR are restored synchronously before
the callback returns. Each source microissue verifies its actual physical
operand bytes, known masks and version. Each qualified write verifies the
destination predecessor version and publishes exactly its owned 16 bytes and
known mask. No whole-VRF result is published early.

FFLAGS is temporarily cleared only inside the private COM oracle to isolate
new exception bits even when previous flags were set. The original value and
known mask are restored. Nonzero new flags refuse before backend input or
numeric publication. With the admitted zero aggregate every local EG flag
delta is zero; no unknown local flag split is guessed. FS must already be
Dirty, so an unproved FS transition is not staged. Other CSR, memory, config,
scalar-FP and vector consumers conservatively drain the actor. Ordinary
integer ALUs and CFI can overlap. Active IRQ context is explicitly refused.

Unretired wrong-path work is a CPU-front reservation, not a backend command.
An unsupported speculative geometry/context produces an opaque token used
only for bounded front-capacity forecasting. It can be canceled pre-COM or
refuse at architectural COM. The opaque token cannot execute semantics or
enter the source controller. This fixes the observed stale indirect-call
prediction from the old FP kernel into the next load case's partial-VL
configuration. It does not qualify exact wrong-path CPU/VU timing.

Qualification:

- `build/FADD-EG-actor-corrective-directed-v2/report.json`: four quiet-hart
  h0/1 × seeds0/17 normal exits, 8,432 independent word checks, exact per-EG
  versions and issue-to-write +4 edges, explicit partial-VL/undefined-v1
  wrong-path cancellation, old8f causal failure, 16 typed refusal cases,
  live MTIP intersecting committed work, and parent/default-OFF byte parity.
- `build/FADD-EG-actor-context-audit-v1/report.json`: all16 native error
  contexts match their real ELF hart/PC/opcode; 32 changed-hart/opcode controls
  refuse.
- `build/rvv-compute-asm-FADD-EG-corrective-ON-v2/run.json`: actual exact ASM
  1320 cases, 184,128 golden words and 3,960 CSR/ELF joins. Its deliberate
  postmeasurement debugger stop is not a normal end-to-end guest-exit claim.
- The first1,512 CSR records exactly match the preserved 8f failure before
  the corrected frontier. The logging-only29c run independently identified
  the unretired JALR and stale FP target without changing that prefix.

Metric `accepted` counts RRD front reservations, including pre-COM kills.
After full drain, backend accepted commands equal accepted minus killed.
The controller clock's occupancy is scheduling machinery, not FMA utilization.
16-byte write points count internal VRF writes, not DRAM/TileLink traffic.

No hardware timings, protected labels, parameter fit, default promotion,
source/image attestation, physical utilization or ±2% accuracy claim is made.
IEEE cases that raise new flags, FS transitions, partial VL, masks, widening,
reductions, BF16/FP8 FADD, general interrupt/context concurrency and exact CPU
ingress/arbitration remain outside this finite native actor's qualification.
