# Original-order CPU layout fit

This is a fitting-only mechanism diagnostic over the actual 2,313-row managed FPGA batch. It is not a native timing implementation, a full-model certificate, or global held-out validation.

`parameters.json` and label-free `predictions.json` were written before the separate internal-validation command. The offset split was frozen before the hardware run: 22 offsets train, 10 internal validation; all formats, N, repetitions and harts at one offset stay together. The no-op cases remain raw controls and are never subtracted or fitted.

The feature is the number of aligned fetch words intersecting the loop's instruction bytes, beyond its dependency/issue lower bound. For this motif only, the two independent integer operations followed by a branch dependent on the second require at least two Shuttle cycles or three Rocket cycles. Fetch words are 8 and 4 bytes respectively. The fit uses N times these features and one region-only boundary constant; no case names, absolute PCs, repetition IDs or reference cycle lookups enter predictions. The constant must never be applied once per instruction.

Training on conditioned N>=64 immediate repeats1/2 gives:

| Hart class | Dependency iteration cycles | Extra fetch word cycles | Region boundary (audit only) |
|---|---:|---:|---:|
| Shuttle0/1 | 2.00029 | 0.99528 | 4.239 |
| Rocket2 | 3.00012 | 0.99955 | 7.273 |

All 720 internal-validation rows have median absolute error 0.195%, p90 22.16%, and 531/720 within 2%. The conditioned 360-row subset has median 0.0606%, p90 0.404%, and 343/360 within 2%. First-use and N16 errors remain in the report; the worst is 94.6%. Conditioning is an analysis subset, not a live timing input. Cold cache/predictor state must come from runtime history before this becomes a usable model.

All compact-loop offsets converge to roughly two cycles per iteration on both Shuttles. Thus instruction alignment alone does not reproduce the old smoke loop's roughly four-cycle cadence. The wider loop has an extra steady cycle when its span touches three Shuttle fetch words; Rocket gains one when the span touches four Rocket words. Other instruction/dataflow motifs remain unvalidated.

Reproduce the fit and verification into fresh directories:

```sh
python3 timing/empirical_cpu_layout_fit.py fit --output /absolute/new-fit
python3 timing/empirical_cpu_layout_fit.py evaluate --output /absolute/new-fit
```

The fixed independent verification is `build/cpu-layout-fit-verification-v1/report.json`: 7,122 geometry, translation/name/repetition invariance, split, poison-CV invariance, coefficient and honesty checks plus six malformed/corruption refusals. It never contacts hardware.
