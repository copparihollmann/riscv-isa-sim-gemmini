# Optional harts 0/1 integer VADD source actor

This experiment adds a source-controlled, per-element-group `VADD.VV` actor to
the frozen 02b4 native. It is disabled by default. It does not change the current
provider or any selected calibration.

The independently tested integer component is
[`build/rvv-integer-EG-source-frozen-v1`](../build/rvv-integer-EG-source-frozen-v1).
The native capsule is
[`build/C12-VADD-EG-frozen-35a80496-v2`](../build/C12-VADD-EG-frozen-35a80496-v2).
Its binary SHA256 is
`35a804964d7882f36a8892d7672dcfbbc7becc89c87e2d830c149820c1291388`;
its paired UART library SHA256 is
`1723a1679f429b57d6a1aacf4a5f33e1f12c5cb35ccb8c4730975302ed60c6c0`.
The external qualification report is
[`build/C12-VADD-EG-native-closure-v1/report.json`](../build/C12-VADD-EG-native-closure-v1/report.json).
The capsule's original `runtime_qualification_pending` field records its freeze
time; the separate closure report records the subsequently completed gates.

## Scope and boundaries

Enable the actor in a new fixture with:

```text
empirical_vadd_eg compute-VADD-VV-fullVL-COMplus1-v1
```

The admitted operation is harts 0/1 full-VLmax, unmasked `VADD.VV`, vstart zero,
SEW 8/16/32/64, aligned LMUL 1/2/4/8, M-mode, VS already dirty, and defined
operands. Hart 2 retains the parent implementation. The source VDQ depth is 4,
the integer issue queue depth is 3, and this VADD pipe writes one source edge
after a microissue. A command can require many microissues: this is not a
one-cycle instruction model.

The functional instruction executes at ordered architectural COM against
private logical operand versions. The actor restores the physical VRF after
that functional evaluation, then publishes each 16-byte group only at its
source-controller write edge, with ownership, epoch, byte and version checks.
Opaque wrongpath front reservations cannot enqueue or publish. A successful
COM offers the backend input at COM+1; this conservative CPU-to-component
bridge is **not** qualified as the exact whole-core RTL join.

Independent scalar ALU/control and supported read-only cycle/instret CSR forms
may overlap the actor. FENCE and other consumers retain pending-controller and
final-write preedge checks. Other vector units, OPU operations, vector memory,
configuration and unsupported consumers conservatively drain. Shared VRF
arbitration between concurrently active different unit actors is not modeled.

Active IRQ contexts are explicitly refused. This mode is not qualified for
active-vector Zephyr context switches. The ordinary OFF mode retains the
parent's OS behavior. Partial VL, masking, unsupported configuration and
unknown operands remain typed refusals. Unknown AVL or vtype GPR inputs still
fail the original XPR definedness check at VSET; readonly VL/VTYPE writable-mask
metadata is not treated as an initializedness oracle.

Recognized VADD uses the source actor instead of the old `rvv.integer`
effective-family setup/work/interval charge. Other inherited family, cache,
memory and CPU behavior remains unchanged. There is no new parameter fit, no
source-to-image attestation, no physical traffic/utilization certificate, and
no ±2% timing acceptance.

## Reproduce the software checks

Run from the repository root, choosing fresh output paths. This complete ASM
readback checks every measured value and CSR endpoint but deliberately quits
after measurements; it is not a normal HTIF guest completion:

```bash
python3 pipeline/replay_rvv_compute_asm_integer_VADD_EG_v1.py \
  --capsule build/C12-VADD-EG-frozen-35a80496-v2 \
  --fixture build/C12-VADD-EG-inputs-v2/ON.fixture \
  --build build/rvv-compute-asm-v5 \
  --output build/CHOOSE_NEW_VADD_ASM_OUTPUT --timeout 900
```

For normal-exit numeric, version, wrongpath and refusal controls:

```bash
python3 timing/check_C12_VADD_EG_actor_v2.py \
  --capsule build/C12-VADD-EG-frozen-35a80496-v2 \
  --ON build/C12-VADD-EG-inputs-v2/ON.fixture \
  --OFF build/C12-VADD-EG-inputs-v2/OFF.fixture \
  --output build/CHOOSE_NEW_VADD_DIRECTED_OUTPUT
```

The standalone source component has its own clean reproducer:

```bash
python3 timing/rvv_integer_eg_source_v3_build.py \
  --output build/CHOOSE_NEW_INTEGER_SOURCE_OUTPUT
```

The native capsule contains the exact 02b4 companion patch, full patch on Spike
`72958551566a30f19444bd7e354552824e4d0a98`, source archive/inventory, compiled
external input inventory, binary pair and build recipe. Both patch paths were
reconstructed and all 2,142 native file hashes checked. The published binary
used documented parent-object reuse; it is not described as a fresh clean
compile. Rebuild only into a new source and build directory, preserving the
repository-relative pipeline depth and the hash-bound external dependencies.

## Completed evidence

* The source component compares 256 full-unit runs across all admitted SEW and
  LMUL values, dependent/independent/chaining/WAW streams and seeds 1/17. It
  checks 3,689,088 fields, 153,600 actual source write beats, and 46,080 output
  bytes obtained through accepted source VSE payloads. An independent source
  sequencer test checks 90,000 edges and explicit hazard/backpressure inputs.
* Final native directed gates check 21,632 independent words, actual wrongpath
  annulment, flags preservation, 14 typed refusals and default-OFF byte parity.
  A quiet three-hart guest exits normally with FS off. Eight final-binary VSET
  tests prove known inputs succeed and unknown AVL/vtype inputs refuse at the
  actual VSET before any VADD source issue.
* The ASM run checks all 1,320 regions, 184,128 words and 3,960 actual CSR/ELF
  endpoint joins. Its VADD journal accounts for 78,720 successful COMs and
  585,600 16-byte source writes. Actual mcycle/minstret reads overlap committed
  unfinished VADD owners; FENCE waits past the final write edge.
* Final native trace ON/OFF runs and the logging-parent-to-final-native runs
  have byte-identical regions, complete CSR prefixes, stdout and readback.
  Canonical functional32 passes on the final binary with preserved per-test
  environment overrides.

Full ASM debugger termination leaves a 156-byte partial final FADD-fence event.
It is preserved, never parsed as a complete event, and prevents a global
full-transcript claim. All VADD and OPU authoritative owner journals are
complete. Hardware timing labels were not used by these checks.

## New OPU journal, separate from timing behavior

The final native additionally logs `opu_functional_COM` only after successful
guarded MM COM, with actual instruction geometry and owner identity. After a
successful guarded source write it logs `opu_K_write_owner` with entry, K,
last-K flag, cell/MAC count and whether the final MRF projection occurred.
The full ASM audit joins 7,728 actual COMs to 57,792 entry/K completions and
14,794,752 logical MACs. Intermediate K writes do not publish the final MRF.

These are model-side ownership/completion records, not measured hardware
utilization. Generic TMOVE has no new authoritative COM journal. Frozen 02b4
profiles must retain their own missing-work qualification and cannot borrow
the new native's events.
