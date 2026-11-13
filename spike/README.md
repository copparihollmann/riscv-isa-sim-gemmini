# Iris SDK4 selected release

The primary entry points select one immutable release through `spike/current`. The current candidate contains Spike72958551566a30f19444bd7e354552824e4d0a98 plus Iris overlaye33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060, native35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d and its ABI4 UARTcc9e38b8df42c0f482f94213a0f58747e1e1c66bd17d54eef154e3ea9748a34b. Full-model, RTL/image and calibrated timing certification remain unavailable.

`spike/bin/spike-iris-functional` remains a native ELF for existing Zephyr/board launchers. `provider.experimental_functional_simulator()` returns the separate fatal-aware launcher and its digest, plus `native_binary`/`native_binary_sha256`. The launcher resolves named fatal handlers from an unstripped guest ELF before execing the exact native. Existing Zephyr runners continue supplying explicit fatal PCs. Recoverable traps still enter the guest handler normally.

Use the existing build command:

```sh
python3 spike/build.py --jobs 8 --dtc /path/to/dtc
```

It builds from `current/source` into a fresh directory, verifies exact native/UART reproduction, recompiles the five corrected real-handler tests and replays32 guest cases. The active release is never overwritten by a build. A different byte epoch fails admission and retains its artifacts. The dispatcher verifies/pins recorded host compiler bytes so a dtc PATH override cannot accidentally select Conda C/C++ compilers. `--output NEWDIR`, `--verify-only` and explicit `--no-selftest` are supported.

`run_selftest.sh` and the `run_functional.py` CLI replay the corrected32 guest corpus. `run_native_selftest.sh` and `run_csr_selftest.sh` rebuild the matched five-handler suite; source/headers/static libraries come from the selected epoch. `run_functional.command` and `symbols` stay import-compatible. Historical ABI1 dispatch sources remain under `historical-5e6-dispatch` as source evidence; execute the old epoch from its preserved full workspace/snapshot, not relocated raw scripts.

`spike/include` and `spike/build` expose matched SDK4 headers/config and libraries. These are selected-release SDK views; use `build.py` rather than running make in the compatibility library directory. Corrected handler sources and the FPComp FS-observation test are mirrored at traditional filenames. Model source edits require a new overlay, build and evidence epoch.

The canonical Git inspection view at `third_party/riscv-isa-sim-current` preserves the base tracked symlink and verifies the exact full overlay. `spike/source` and builds use the portable byte-locked snapshot, which normalizes the disassembler source symlink into identical source-file bytes. The existing `third_party/riscv-isa-sim` main checkout stays historical because its .git directory anchors all active worktrees. Decoder/header consumers select `spike/source` explicitly; `build_reference.py` intentionally uses the historical repository only to archive the exact pinned base. Both current views are immutable release inputs/projections. Native and UART reproduction is exact.

For Merlin, run `integration/iris-mlir/configure_model.py --model-root . --output NEWDIR`, select the emitted manifest and set `MERLIN_IRIS_ALLOW_EXPERIMENTAL_FUNCTIONAL=1`. Launcher, native, UART, bootROM/DTB and smoke evidence are bound separately. The backend checks declared execution inputs before and after execution, with no fallback after refusal. Old native-only descriptors remain compatible.

Per-hart datatype subsets, knownness policy, limitations, source provenance,19 proof groups and the separate positive Zephyr/compiler/profile companion are in `spike/current/provenance.json` and `spike/current/README.md`. Source scalar pipeline fixtures remain explicit uncalibrated experiments without a full-SoC +/-2% guarantee.
