# C12 source OPU developer experiment

This opt-in native experiment combines the source-qualified scalar FADD and warm-load paths with a bounded OPU controller for TK1/2/4. The selected model and all existing providers remain unchanged. **C12 has no calibrated-provider release:** its native/mode needs its own timing calibration replay and runtime binding. The recipe preserves that refusal instead of substituting another model.

The staged descriptor is [manifest.json](../build/source-OPU-C12-developer-package-v3/manifest.json), SHA256 `d08561ec3d296930a2fe6de7b50911856c4d48ead05514cf89d32d467e6deba2`. It uses the frozen C12 native `c12a08f7…` and paired SDK4 UART `e02f1a31…`. The native source capsule, complete evidence inventory and exact identities are bound in the descriptor.

From the repository root:

```sh
python3 timing/source_OPU_developer_v3.py \
  --package build/source-OPU-C12-developer-package-v3/manifest.json \
  --expected-sha256 d08561ec3d296930a2fe6de7b50911856c4d48ead05514cf89d32d467e6deba2 \
  --action verify --mode tk124
```

The first execution below has been independently checked: all twelve smoke regions on all three harts pass. It writes separate stdout/stderr, modeled summary and CSR feature records, exact input hashes and an owned-process cleanup receipt into a fresh directory.

```sh
python3 timing/source_OPU_developer_v3.py \
  --package build/source-OPU-C12-developer-package-v3/manifest.json \
  --expected-sha256 d08561ec3d296930a2fe6de7b50911856c4d48ead05514cf89d32d467e6deba2 \
  --action run --mode off --elf benchmarks/build/smoke.elf \
  --output build/NEW-C12-smoke --timeout 90
```

For a known, initialized bare-metal guest, replace `--mode off` with `--mode tk124` and supply its unstripped RV64 ELF. The driver fixes the three hart ISAs, real memory map, ROM, DTB, paired UART and fatal-aware launcher. It accepts no arbitrary launch-option or timing-cost overrides. The timeout only cleans up the process group created for this invocation. A zero process exit is recorded as such; arbitrary guest numerical validation and independent normal-HTIF proof remain the caller's responsibility.

`--action provider` deliberately returns `IRIS_SOURCE_OPU_CALIBRATED_PROVIDER_UNAVAILABLE`. Existing empirical-provider calibration guards have not been changed. No current-pointer or default-selection command is part of this recipe.

| Mode | Qualified use | Important limits |
| --- | --- | --- |
| `off` | FADD + warm-load baseline; canonical32 and five actual Zephyr groups pass | Memory/family costs are inherited from a different native/mode epoch; no transferred accuracy claim |
| `tk124` | Opt-in bare-metal OPU on compute harts0/1; INT8→INT32 and FP8→FP32; positive TM/TN≤32, TK1/2/4, four tiles | M-mode, defined stable VRF; active IRQ and unsupported MM CPU fetch boundaries refuse; no OPU-ON Zephyr-context qualification |

Hart2 retains its functional RVV ISA and has no VME. Its e32/LMUL8/VL64 (256-byte) repeated-load **FPGA liveness remains unqualified**, despite ISA legality and passing source-component controls. Do not describe excluded liveness cases as illegal instructions.

The OPU controller uses source VDQ4/IQ3/sequencer capacities, per-entry dependencies and actual K-loop order. Each K completion credits its own logical MACs; only the final K publishes the entry's architectural MRF result. Intermediate-K architectural values are unavailable. Operand replacement, non-MM consumers, zero/move/config and memory boundaries drain pending work. The COM+1 CPU-ingress bridge, predictive CPU admission and conservative FENCE/config policy remain explicit approximations.

The [C12 readiness inventory](../build/warm-OPU-TK124-c12-readiness-v1/readiness.json) binds source differential, full-MRF, wrong-path, queue-full, refusal, package-sensitivity, canonical32, OPU-OFF Zephyr and launcher7 results. TK2 and TK4 each check106,496 independently read-back words with varied initial cells and K-dependent operands. The [compiler-image report](../build/focused-TK124-compiler-image-regressions-v1/report.json) adds eight preserved compiled GEMM/conv2d executions: one/two workers, shipped/twin, all full int32/W8A8 words checked. These are preserved ELF replays, not fresh compiler invocations or timing-accuracy validation.

The [developer controls](../build/source-OPU-C12-developer-controls-v2/report.json) add eight digest/type/mode/provider refusal controls and the actual fixed-recipe three-hart smoke. An earlier recipe put the device before its UART extlib and failed during native setup; that failed epoch and its logs are preserved. The current recipe registers the exact paired extlib before the device.

All whole-CPU timing, ±2%, physical bandwidth and source/image certificates remain false. The [repeated-load source closure](../build/rvv-rocket-repeated-load-source-closure-v1/report.json) passes128 clean-reset SaturnRocketUnit controls with explicit synthetic responses; it neither reproduces nor resolves the surrounding FPGA memory-path stall.

To stage a later reviewed native epoch, use the parameterized builder with **that epoch's own** capsule, fixtures, readiness, eight compiler-image gates, exact launcher and launcher7 receipt:

```sh
python3 timing/package_source_OPU_developer_v3.py \
  --capsule build/NEW-frozen-capsule \
  --on-fixture build/NEW-inputs/OPU-ON.fixture \
  --off-fixture build/NEW-inputs/baseline.fixture \
  --readiness build/NEW-readiness/readiness.json \
  --compiler-gates build/NEW-compiler-gates/report.json \
  --launcher build/NEW-capsule-launcher/spike \
  --launcher-tests build/NEW-launcher7/report.json \
  --output build/NEW-source-OPU-package
```

The builder refuses mismatched native/UART/launcher/fixture evidence. It does not rebuild or publish a native, fit parameters, create an empirical runtime binding, or make a calibrated provider available.
