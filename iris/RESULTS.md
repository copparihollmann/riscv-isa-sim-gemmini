# Iris result provenance and interpretation

This document accompanies schema `iris.public_capability_results.v1` in
[`results.json`](results.json). The report values were copied directly from the
recorded root validation reports on 2026-11-07; publication performed no fitting.
The README tables round to three decimal places; JSON preserves the original
floating-point values.

## Exact measured implementation

- Frozen native SHA256: `35a804964d7882f36a8892d7672dcfbbc7becc89c87e2d830c149820c1291388`.
- Clocked UART SHA256: `1723a1679f429b57d6a1aacf4a5f33e1f12c5cb35ccb8c4730975302ed60c6c0`.
- Upstream Spike: `72958551566a30f19444bd7e354552824e4d0a98` plus the frozen Iris overlay.
- Chipyard: `b4542facf6cc9457f6e358e8f80a8b3a0ff5df19`.
- Saturn: `536774bd4c5e3bcd7813a4a0dc72fc87e5818532`.
- Rocket Chip: `fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0`.
- Shuttle: `a536ed1df91a0f65770e36758291d02a8cb929c4`.
- HardFloat: `0ecaef097ce2accbd16a61613699450ed5533f29`.

The [source-import receipt](provenance/import.json) records include relocations
for this fork. The historical source/binary measurements bind the frozen binary
above, not every later build of this source branch. New build receipts and
regressions must be evaluated separately; inherited calibration fixtures do not
establish new-binary numerical or timing qualification. The [original release
index](provenance/frozen-release.json) and [validation summary](validation.json) preserve the
previous package identities and their original path requirements.

## Evidence identities

The paths below are relative to the external archived `iris-model` workspace;
large raw campaign data remain outside Git. Digests identify the exact reports,
not an assertion that those external files are downloaded by a normal clone.

| Evidence | Archived path | SHA256 |
| --- | --- | --- |
| isolated_compute | `build/rvv-compute-heldout2-C12-source-VADD-root-validation-v1/report.json` | `bd7c177fdb0eb235f5e86e713a4b401c86c65bc29f54da24557bb546ffc51c88` |
| zephyr | `build/zephyr-hart2-pow2-35a-OS-root-validation-v2/report.json` | `da6e43471b2f67cea0eb617c38859d5111441aedf98c3fa42bb026a35ef8bfeb` |
| FPGA_functional | `build/zephyr-hart2-pow2-FPGA-sealed-analysis-v1/report.json` | `35d713fbc927c8dda0a05e94fe4c3528efafede40f27884f409fdb2849a9f407` |
| Zephyr_example_parity | `build/zephyr-firstuse-f5d-model-FPGA-functional-parity-v1/report.json` | `493725e7398cd20f468cd1d334337b593e7d063c3fffcf45486911a410518521` |

The isolated compute report retains all 1,320 regions, three repetitions,
184,128 independent output-word checks and 3,960 CSR/ELF joins. Both harts are
measured separately; this does not establish concurrent timing. The Zephyr
report retains all 648 regions and 1,944 phase rows. Its reserved validation
subset has 192 regions; 456 are marked training-eligible, but no refit or new
model selection was performed for this comparison.

## Metric definitions

Each selected `total_cycle_groups` entry contains the source report's region
count, median signed percent error, median absolute percent error, P90 absolute
percent error, maximum absolute percent error and number within ±2%. Absolute
and signed medians are calculated independently. These are region distributions,
not a claim that an entire application has the same error distribution.

The isolated `all`, `hart:0`, `hart:1` and `kind:*` groups come from the frozen
compute profile. The Zephyr `mask:1`, `mask:2` and `mask:3` groups respectively
select hart-0 compute, hart-1 compute and both compute workers, with hart 2 as
scalar coordinator. `split:protected_validation` is the originally reserved
subset. The two experiments use different profiles and workloads; differences
between them do not isolate multicore contention as a single causal variable.

The original report `pass: true` means that its analysis/consistency gates
passed; the explicit accuracy acceptance flags remain false. Every region stays
in the reported distribution, including the three Zephyr regions with retired
instruction-count mismatches. No region, drain phase, outlier or OS overhead is
silently subtracted. The signed-error denominator is the recorded FPGA region
cycle count. P90 is nearest-rank ceil.

The model was stopped after collecting the broad measured regions, before all
normal UART completion. A finite debugger-step control passed for the separate
nine-checksum Zephyr example, but universal equivalence between controlled-stop
and ordinary scheduling remains unqualified. Neither broad comparison is an
end-to-end guest completion or simulated-MIPS measurement.

## Functional and timing scope

The FPGA's 648-region functional pass covers active outputs and guards at the
recorded power-of-two geometries. FP8 covers finite inputs in E4M3/E5M2 format
pairs; it is not special-value/all-encoding certification. Ordinary vector INT8
on hart 2 is supported despite absence of a matrix unit there. The nine-checksum
Zephyr example has a separate normal-exit FPGA/model parity report.

Source event accounting describes model occupancy and completed logical work.
Physical unit utilization, physical memory bytes/bandwidth/rooflines and useful
hardware HPM/TracerV measurements are not available from this image. Timing
qualification for compute harts cannot be transferred to hart 2 or the OS
profile, and loaded FPGA image identity is not a full source-to-image attestation.
The whole ±2% held-out gate, full-ISA bit-exact certificate, unrestricted vector
context migration, memory/compute overlap and whole-model qualification remain
unmet. Preserved failures are not relabeled passes by this documentation.
