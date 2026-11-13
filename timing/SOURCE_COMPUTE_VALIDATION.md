# Experimental source compute model: scope and independent validation

This model prioritizes the Shuttle compute harts0/1. All three harts execute
functionally; hart2 remains the Rocket control/program core. Detailed hart2 timing
is not qualified. VLEN256 applies to all harts; DLEN128 applies to harts0/1 and
DLEN256 to hart2. Hart2 has ordinary integer and IEEE vector arithmetic, but no
VME/OPU. Exact capabilities and discrepancies are recorded in hardware/dtypes.json.

The frozen source composite is native02b4a9ab/UART8903d961, with pending scalar-base
RRD retry, a missing asynchronous RRD wake fixed, per-EG FADD queues/hazards and
numeric publication, independent counter reads, and source OPU FENCE predicates.
Source COM+1 remains an unqualified bridge. This is an experimental finite model,
not a cycle-accurate SoC or a blanket ±2% result. The default model is unchanged.

## Independent measurement

The exact ELF f845782a5676a74ef130d6a3389a703ad4843fc1be6ff07433a6066ee1814d5e
uses assembly bodies with all kind/mode dispatch before the ROI,16x unroll, explicit
pre-execution/full reset, and independent full-output goldens. It tests both compute
harts individually, with the other harts parked. Arithmetic and matrix counts32/128,
LMUL1/2/4/8, supported SEWs, memory payloads16/32/64/128/256B, and row counts2/8/32/128
provide power-of-two coverage. Three repetitions of every case are retained.
Pre-execution is a defined history, not proof of a physical cache hit.

The FPGA job completed kill→infrasetup→runworkload→kill, guest exit0,1320 regions,
184128 checked words, owned cleanup and archive. There were zero training rows.
All1320 model predictions and3960 actual counter/ELF joins froze before the
protected timings were opened. Original TRAIN-only numeric coefficients were
unchanged; no refit or model selection used these labels. All retired instruction
counts match in total, issue and drain phases. These opened results cannot qualify
future adaptive changes as a new blind test.

Signed error is100×(model−FPGA)/FPGA. The table uses actual program mcycle deltas;
no overhead or outlier subtraction. P90 uses nearest-rank ceil.

| Operation | Regions | Median signed | Median absolute | P90 absolute | Maximum absolute | Within2% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| integer | 576 | +1.058% | 1.072% | 8.276% | 81.216% | 330/576 |
| fp | 432 | +0.145% | 0.322% | 1.685% | 5.056% | 408/432 |
| matrix_int | 48 | +0.569% | 0.569% | 2.098% | 5.747% | 39/48 |
| matrix_fp8 | 48 | +0.384% | 0.431% | 1.107% | 2.392% | 46/48 |
| rowmove | 24 | +2.495% | 2.812% | 4.396% | 5.405% | 4/24 |
| load | 60 | -7.653% | 8.284% | 17.158% | 32.727% | 3/60 |
| store | 60 | -5.940% | 6.266% | 13.073% | 24.405% | 4/60 |
| load_use | 24 | +27.733% | 27.733% | 47.292% | 47.692% | 0/24 |
| load_independent | 24 | +27.657% | 27.657% | 44.809% | 47.160% | 0/24 |
| store_compute | 24 | +17.736% | 17.736% | 33.145% | 33.480% | 0/24 |

Across all1320 total regions, median absolute error is0.756%,P9010.135%,maximum
81.216%;834regions meet2%. Issue-window median absolute error is2.863%; drain-window
median is25.000%. Thus good total medians do not certify completion/overlap behavior.
Integer outliers and memory/compute interaction remain material limitations.
FP8 matrix timing results above cover E4M3×E4M3 only; other source-supported
format pairs do not inherit this timing qualification. An independent audit of the
archived v12 FPGA run separately confirms all four E4M3/E5M2 operand pairs,
30 functional checksum observations each on compute harts0/1. That finite coverage
uses explicit A-format bits and B-altfmt configuration, not the misleading alias
macro names. It covers tile0,row0,+1 operands,TK4,N16/64; it is not an all-MRF,
per-word or special-value certificate. [Exact format coverage audit](../build/fp8-format-functional-coverage-audit-v1/report.json). No concurrent-hart or end-to-end workload
accuracy is inferred from these isolated measurements. The previous C-loop
calibration and this assembly experiment differ, so their medians are not a
like-for-like improvement claim.

Full signed rows and input/output SHA256 bindings:
[validation report](../build/rvv-compute-heldout-C12-source-composite-root-validation-v1/report.json),
[all regions](../build/rvv-compute-heldout-C12-source-composite-root-validation-v1/regions.jsonl),
[prediction freeze](../build/rvv-compute-heldout-C12-source-composite-selected-v1/freeze.json),
[hardware archive](../runs/fpga-rvv-compute-heldout-asm-v1-001.capture.tar.gz).

## Software profiles and guardrails

The source-compute fixture enables source OPU/FENCE and finite per-EG FADD. Eight
preserved GEMM/conv2d compiler images at one/two workers (shipped/twin) passed normal
exit,32768int32 and32768W8A8 values. These were preserved actual ELFs, not freshly
compiled programs. Five real Zephyr/context groups passed with a separate OS
fixture that disables source OPU entry and specialized FENCE. Those OS results
must not be transferred to the source-compute profile.

Per-EG FADD is limited to fullVL,unmasked,RNE,H/S/D,already-dirty FS and no newly
raised flags or active IRQ. Unsupported contexts refuse explicitly. Active per-EG
FADD preemption/context switching is not certified by the OS tests. The legacy
functional path remains available through an explicitly different profile/model.
Both profiles keep correct hart2 boot/control/timer/IPI behavior and VME refusal.
Source-compute timing evidence does not certify the OS profile's timing.

[Exact software readiness](../build/C12-source-composite-readiness-v1/readiness.json)
and [profile-specific runtime admission](../build/C12-source-composite-runtime-QA-root-closure-v1/report.json).
The optional package is available: [run instructions](../build/C12-source-composite-optional-package-v2/RUN.txt)
and [delivery receipt](../build/C12-source-composite-optional-delivery-v1/report.json).
Each profile passed its own normal three-hart smoke, timing sensitivity and seven
fatal/launcher gates;44descriptor/digest/cross-profile controls pass. Existing
providers and the default pointer are preserved.

## Profiling

[Per-region JSON](../build/rvv-compute-heldout-C12-FADD-source-profile-v1/regions.json)
and [Perfetto/Chrome trace](../build/rvv-compute-heldout-C12-FADD-source-profile-v1/trace.json)
cover all432 measured FADD regions. Actual architectural COMs join all57,600
commands to432,000 source EG issues and16B publications. Metrics include source
pipeline-valid union cycles, command-pending age, dtype/LMUL element throughput
versus the conditional source ceiling, and ELF function attribution. An independent
review recomputed every region from per-edge sets and rejected14 corrupt joins.

These are model/source activity metrics. Internal VRF bytes and logical source
operands are not physical memory traffic. DRAM bandwidth, physical arithmetic
switching, a hardware roofline and additive CPU stall attribution are unobserved.
A25-byte final observer fragment is preserved after controlled debugger exit;
all selected FADD events are complete. Shared source-clock spans and program
mcycle deltas are reported separately. Controlled-stop replays do not establish
end-to-end execution speed.

## Provenance and remaining acceptance

Source pins and dirty patches are recorded in hardware/manifest.json and each
capsule, including Chipyard b4542facf6cc9457f6e358e8f80a8b3a0ff5df19,
Saturn536774bd4c5e3bcd7813a4a0dc72fc87e5818532,
Rocketfc745a8c377fdbf1d278eea81da9ac47b4b5fbc0,
Shuttlea536ed1df91a0f65770e36758291d02a8cb929c4 and
Spike72958551566a30f19444bd7e354552824e4d0a98 plus frozen changes.
Full image/source association remains unverified. The exact existing image and
matching original driver are hashed and preserved; no substituted image is implied.

The current image exposes no TracerV,AutoCounter,SynthPrint or useful HPM counters.
FASED reset30 was read before driver initialization in memory-model clock units;
it is not a calibrated CPU memory latency. The current memory/compute completion
model needs structural work, including actual source request/response identities,
source queues and contention. The full goal still requires held-out concurrent
Zephyr workload accuracy, functional/type certification breadth, physical traffic
qualification and the agreed complete profiling workflow.

The normal three-hart packaged smoke ran at approximately0.220simulatedMIPS
(source_compute) and0.216MIPS(source_os), including launcher/provenance and console
costs. Each is one12-region normal-exit run, not a general throughput guarantee.
[Measured speed receipt](../build/C12-source-composite-normal-smoke-speed-v1/report.json).

The real Merlin contract now has an additive [adapter recipe](../build/C12-source-composite-Merlin-adapter-delivery-v1/RUN.txt).
It supplies required ISA metadata while preserving both source profiles. All8
shipped/twin one/two-worker images passed through actualdevice_simulator.run
with fullI32/W8A8 goldens,3physicalharts and workers restrictedto0/1. It doesnot
change timing/native code or transfer timing qualification betweenprofiles.
