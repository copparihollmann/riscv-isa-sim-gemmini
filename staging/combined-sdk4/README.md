# Experimental combined Iris SDK4 package

This staging package contains the combined source model for all three Iris harts: Shuttle0/1 with VLEN256/DLEN128 and VME, and Rocket2 with VLEN256/DLEN256 Saturn integer and IEEE floating execution. Hart2 does not advertise the compute harts' matrix/Mx arithmetic. The raw hardware dtype audit is separate from the explicitly tested model coverage in `provenance.json`.

The primary package remains unchanged pending coordinator review. `provider.device_simulator()` reports the full model unavailable. Explicit functional selection uses `provider.experimental_functional_simulator()` and verifies the complete package, SDK4 pair and evidence closure before returning an executable. Full RTL certification, complete knownness coverage, deployed-image association, calibrated full-SoC timing and held-out +/-2% remain false.

## Build

```sh
python3 build.py --output /new/isolated/rebuild-directory --jobs 8
```

The packaged builder defaults to `source/` and verifies every file against `source-lock.json`; it does not rebuild the old primary source tree. It needs the recorded compatible host C/C++ tools, make and dtc. The local tested environment places `/scratch/eygao/iris-cy/.conda-env/bin` first in PATH. The receipt records the actual command lines and tool digests. Changing host tools may produce a different byte epoch: retain that result and run fresh gates rather than assigning the existing proof to it.

The source snapshot comes from Spike pin72958551566a30f19444bd7e354552824e4d0a98 plus the complete Iris overlaye33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060. Relative board/timing includes resolve inside the snapshot. Both C and C++ source-location prefix maps reproduce historical source strings while compiling the packaged sources. Fresh offline and packaged-source builds must reproduce native35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d and UARTcc9e38b8df42c0f482f94213a0f58747e1e1c66bd17d54eef154e3ea9748a34b.

The generic descriptor executes the hash-bound `launch.py`, which resolves known fatal-handler symbols from an unstripped RV64 ELF and then execs the exact native359. The descriptor records the launcher digest separately from `native_binary_sha256`; this is not a new native byte epoch. Malformed/stripped ELF symbol metadata is explicitly refused.

The matching SDK is under `sdk/`, including `config.h` and `riscv/iris_clocked_device.h`. ABI4 is required; old ABI1/3 plugins are deliberately incompatible. Rebuild extensions against this SDK and retain their dependency hashes. Native and plugin bytes form a pair.

## Run and Merlin

The package preserves the generic Merlin provider descriptor fields `available`, `binary`, `binary_sha256`, `isa_extensions` and `provenance`. The generated `merlin-manifest.json` also binds exact per-hart ISA, matrix worker harts0/1, the memory map, bootROM/DTB, finite clocked UART and a fresh three-hart smoke.

Use the existing Iris OOT adapter with:

```sh
export MERLIN_IRIS_MODEL_MANIFEST=/absolute/package/path/merlin-manifest.json
export MERLIN_IRIS_ALLOW_EXPERIMENTAL_FUNCTIONAL=1
export MERLIN_IRIS_TIMING=off
```

The manifest contains absolute launch paths; regenerate that small deployment manifest after relocating a package, rather than editing its frozen evidence. The provider itself verifies package-relative source, binary and evidence paths. Run arguments for direct execution are available from its explicit functional descriptor; preserve all three `--hart-isa` overrides and the board memory regions. Select matrix workers only on harts0/1; hart2 may serve as an integer/vector producer or scheduler.

Software must initialize state before numeric/control observations. Bit-level shadow masks track reset-unknown XPR/FPR/VRF/predicate/FCSR/tile and canonical shared RAM data, including opaque context spill/reload. Missing required bits cause a nonzero `IRIS_UNDEFINED_STATE` diagnostic naming hart, PC, unit and masks. This refusal is a model limitation/unknown observation, not an invented hardware zero. The launcher configures ELF fatal symbols (`z_fatal_error`, `k_sys_fatal_error_handler`, `arch_system_halt`, assertion/stack failures and `abort`) and unions explicit `IRIS_FATAL_PCS`; these entry points terminate with native hart/PC/cause/EPC/tval diagnostics; an arbitrary architectural trap is not automatically fatal because legitimate OS trap handlers exist.

The source model explicitly refuses hart2 CEASE halt-until-reset and unsupported configured column matrix readout. Nonzero vstart, decode legality, hart2 matrix refusal and finite UART mismatch/unknown-RX cases have directed checks. See `limitations` and `datatype_coverage` in provenance for exact numeric scope, source-specific floating flag policies and remaining gaps.

## Evidence and timing

`evidence/combined` preserves the original19 local groups,32 guest corpus and five handler/oracle groups, including mask knownness corrections, FCSR/FS policy, scalar pipeline/counters, physical board, IPI/atomics, memory guards, PLIC and SDK mismatch tests. `evidence/os` is the separate exact-byte root acceptance companion: positive scalar/mixed SMP, RVV and VME context migration/preemption, actual compiler shipped/twin GEMM and nine captured profile regions. Those are successful tests, not universal Zephyr or RTL certification.

Default functional cycles are not a calibrated performance estimate. An explicit `--iris-timing-fixture=...` can exercise the source Shuttle/Rocket integer pipeline and serialized remaining-operation integration. The experimental fixture's scope, unsupported operations and missing frontend/cache/vector/VME/memory interactions prevent a full timing claim. No sampling or fitted +/-2% guarantee is advertised.

The build evidence also preserves an inspection incident: an objcopy command without a separate output unexpectedly rewrote an inspected frozen native; its exact original359 bytes were restored from the immutable content-addressed object and verified. Primary and preliminary binaries were untouched. Subsequent section inspection uses read-only byte parsing. The first fresh build's different564 byte identity is retained separately; the final C/C++ mapped build reproduces359 exactly.
