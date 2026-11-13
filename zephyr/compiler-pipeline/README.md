# Real compiler kernels in a three-hart Zephyr pipeline

`zephyr/compiler_pipeline.py` invokes the actual Merlin `MatrixRouting` provider
and Iris OOT source-derived kernel emitter. It runs one or two compute workers
on harts 0/1, calls the target-owned setup hook from
`integration/iris-mlir/zephyr/task_setup.h`, and uses hart 2 for a double-buffer
producer/consumer with ordinary RVV work. All three OS harts boot through the
physical Iris ROM. Generated kernels use independent per-worker workspaces.

The direct OOT route uses its explicit pointer/workspace bridge. The optional
`--mlir-receipt` route instead links the actual LLVM23 model and descriptor
bridge objects produced by `integration/iris-mlir/compile_model.py`. Its exact
`_mlir_ciface_forward` ABI receives three rank-2 memref descriptor pointers and
writes the caller's result buffer. The tested local model is 32×64×64 for GEMM
or 32×64×72 for the convolution contraction. A single compute worker calls that
32-row model twice; two workers call it once each, preserving the complete
64×64 output in both cases. Convolution indexing/im2col runs in the producer;
the MLIR model compiles the contraction endpoint.

Each run executes three jobs with varying signed-int8 inputs. The producer
prepares the alternate buffer while compute workers are active, consumes the
previous result and checks an independent ordinary-RVV checksum. Host validation
compares every int32 accumulator and every quantized W8A8 float container word:
12,288 output elements per shipped or scalar-twin image. It also checks actual
hart/role/counter attribution, producer overlap and VME refusal on hart 2.
Executable disassembly confirms that required VME instructions exist in the
shipped kernel functions and are absent from the scalar twin's kernel functions.
The OS itself retains its matrix context routines in both builds.

For a direct emitted-kernel gate:

```sh
build/merlin-venv/bin/python zephyr/compiler_pipeline.py \
  --op gemm --harts 2 --output build/zephyr-compiler-example
```

For the real Merlin MLIR path, first generate the exact artifact manifests with
the OOT compiler helper and matching LLVM23 environment. Then:

```sh
build/merlin-venv/bin/python zephyr/compiler_pipeline.py \
  --op gemm --harts 2 --mlir-receipt build/merlin-mlir/gemm/artifacts.json \
  --binary spike/bin/spike-iris-functional --uart spike/bin/libsifive_uart.so \
  --output build/zephyr-mlir-example
```

Use `--op conv2d` and its corresponding artifact manifest, or `--harts 1` for
one compute worker. The artifact manifest must match the exact schema, shape,
symbol, source and object hashes; unknown contracts are refused. MLIR mode uses
the pinned thread-safe common libc malloc with a 262144-byte arena and 131072-byte
kernel heap, exercising concurrent intermediate/workspace allocation and
malloc(0). All source/emission/build/ELF/object/console/disassembly hashes are
retained in the per-gate receipts. Historical 421 snapshot results remain under
`build/zephyr-mlir-gates`; packaged-primary results are under
`build/zephyr-mlir-final`.

`python3 zephyr/compiler_acceptance.py --verify` rechecks all 98,304 int32 and
98,304 W8A8 results across the eight final programs. It verifies the archived
0c0 native bytes/provenance closure, actual ELF/disassembly and compiled-source
snapshots, so a later primary simulator epoch cannot silently change this result.

This qualifies the tested compiled operators in explicitly registered Zephyr
tasks. It does not qualify an arbitrary generic OpenMP/whole-model worker pool;
that pool must invoke target-owned setup before dispatching VME work. Full GPT,
Llama/Gemma/TinyLlama model deployment, FPGA/RTL equivalence and calibrated
cycle prediction remain separate gates. Functional-mode counters here describe
Spike instruction progress, not Iris performance.
