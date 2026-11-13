# Companion compiler integration

The pristine `third_party/merlin`, `third_party/iris-mlir` and `third_party/rvv-mlir`
checkouts preserve full source pins. Implemented changes live in detached
`integration/merlin` and `integration/iris-mlir` worktrees. No commit, push or PR
was created. `manifest.json` records exact baseline revisions, patch digests,
modified-file digests and evidence. `patches/` contains reviewable patches which
were checked against the pristine baselines. Regenerate with
`build/merlin-venv/bin/python integration/record.py` after intentional edits.

The OOT README is the runnable interface documentation. The concrete full front
door is:

```sh
export MERLIN_PYTHON=$PWD/build/merlin-venv/bin/python
export MERLIN_CHIPYARD_IRIS=/scratch/eygao/iris-cy
export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH
integration/iris-mlir/examples/iris/run.sh op gemm --harts 2 --zephyr-mlir \
  --model-root "$PWD" --clang build/llvm23/bin/clang-23 \
  --llvm-source third_party/llvm-project \
  --binary build/zephyr-primary-0c0fd778/spike \
  --uart build/zephyr-primary-0c0fd778/libsifive_uart.so \
  --output build/merlin-workflow/example-gemm-h2 --timeout 120
```

That path performs real Merlin MLIR routing/lowering, compiles RISC-V model and
LLVM descriptor-bridge objects with the exact LLVM23 toolchain, emits the actual
source-derived OOT VME backend, and runs registered Zephyr tasks on all three
physical CPUs. One/two VME workers occupy0/1 while hart2 overlaps CPU/RVV
producer work. Use `op conv2d` and `--harts 1` for the other operation gates.
The convolution compiler boundary is its im2col contraction endpoint; the
compiled Zephyr producer supplies the indexing/packing. Generic whole-model
OpenMP ownership integration remains explicitly refused.

The four retained0c0 gates executed eight programs (shipped/twin), each with
three changing-input jobs. All98,304 accumulator values and98,304 W8A8 values
matched independent goldens. The same integer requantization was cross-checked
against Merlin's public `Tensor.requant(10).to_i8()` reference. The current
`db964603...` package also passed the complete front door once. These remain
functional operation checks, not full-model, RTL or calibrated timing claims.

Evidence entry points:

- `zephyr/compiler-acceptance.json` and `zephyr/compiler_acceptance.py --verify`.
- `build/merlin-evidence/closure.json`:58 content-addressed retained compiler/runtime inputs for historical0c0 gates.
- `build/merlin-epilogue-crosscheck.json`: actual Merlin integer finishing semantics.
- `build/merlin-workflow/current-memory-gemm-h2/results.json`: current memory epoch through the full front door.
- `build/merlin-targeted-final-tests.log`:20 focused tests pass, including real rank2/rank3 upstream ABI tests and provider tamper/timing refusals.
- `build/merlin-structure-check.log`: all structure checks pass.
- `build/merlin-integration-tests.log`:106 broader passes,3 skips and4 pre-existing board/source-assertion failures. The same4 failures reproduce on pristine d561 in `build/merlin-baseline-board-tests.log`; none comes from the integration patch.
- `workloads/`: frozen config-only model intake,204 proposed structural cases, explicit fitting/validation separation, unknown operators and4GiB streaming obligations. No weights were downloaded.

The experimental provider manifest is regenerated against a verified current
model package with `configure_model.py`. Source/binary/selftest drift fails
closed. Historical runs retain their exact identities even as a new primary
package is published. Timing availability, RTL equivalence, model-wide quality,
complete streaming transport and full-model execution remain false/unknown.
