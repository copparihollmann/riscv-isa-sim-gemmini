The finite scalar-FADD timing option can run independently of the strict source frontend and its RAS definedness requirements. Its exact enable line is:

```
empirical_scalar_fadd source-HSD-pipeline-v1
```

The fixed experimental fixture is `build/scalar-FADD-legacy-front-e8ed-inputs-v1/ON.fixture` (SHA256 `fbf867dd9169a7dbba99f22c1c860d5e34564158b32c0d773d768f4c3de44d93`). It appends only that line to the selected `70c0a5...` fixture; it neither changes coefficients nor enables the strict frontend. This is a separately qualified experimental mode, not a mutation of the selected provider or an inherited calibration certificate.

The implementation in frozen native e8ed is byte-identical to the earlier phase-qualified scalar-FADD primitive. It accepts finite M-mode nonmemory FADD.H/S/D, stages the numerical result at scalar COM and publishes the FPR value, per-operation flag delta and FS effect at the modeled physical write. Shuttle writes four source edges after accepted EX; Rocket writes three edges after EX. COM occurs at EX+2. Dependency handling permits the next dependent EX only at write+1 on all three harts. Rocket may admit ID on the write edge and reads the new FPR at its following EX. No FPR bypass is invented. Independent accepts can occur each source edge, with actual finite occupancy peaks 4/4/3.

The original saved whole-CPU phase proof contains 288 accepted FADDs, nine numerical regions and 2,613 checks. Its finite observation, memory/preload and two-state scope remain explicit; it is not deployed-image equivalence. The new frontend-independent source audit is `build/scalar-FADD-legacy-front-source-audit-v2/report.json`.

Actual e8ed tests passed dependent and independent H/S/D chains, local flag accumulation, five legal rounding modes, precise wrong-path suppression and per-hart undefined-FPR refusals. The original IRQ guest exited normally with correct values on all harts, but its pending-FADD overlap requirement was observed on harts 0 and 1 only. Its failed coverage receipt is preserved. Exact interrupt-delivery timing and shared scalar/vector-FPU arbitration are not certified; unsupported FP, memory and context domains retain conservative drains.

All 32 canonical functional guests and five real three-hart Zephyr groups passed in this epoch. The two six-task RVV/IEEE context groups each actually accepted and published 72 scalar FADDs per hart, totaling 432. This tests real mode activation and state preservation, not merely a zero-use configuration. The five gates also retain the existing matrix ownership, migration, timer, hart-2 producer and refusal checks. See `build/scalar-FADD-e8ed-activation-QA-closure-v1/report.json`.

The exact new 576-region power-of-two scalar ELF finished normally in 473.81 host seconds, with all 2,304 numerical words correct. The independent qualifier joined all 1,152 mcycle endpoints to the program's UART records and verified every region's FADD count equals N or 4N for its dtype. Each hart accepted and published 183,600 FADDs; every ROI boundary and the final exit had no pending FADD owner. See `build/pow2-scalar-e8ed-source-FADD-qualification-v2/report.json` and its immutable model-only predictions.

The new source feature names are `scalar.fadd.fp16`, `scalar.fadd.fp32` and `scalar.fadd.fp64`. Generic `scalar.fp*` still contains other operations such as conversion or register moves; old coefficients must not be relabeled. The power-of-two reserved hardware sizes N=32/256/1024 remain coordinator-only. These model-only tests did not consume their hardware timings, fit parameters, establish a universal 2% bound or authorize a provider switch.
