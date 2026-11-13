# Protected operator validation batch

`build/model-operator-batch-v1` contains the new bundled validation ELF. It
retains the exact qualified MLIR model and descriptor object instruction bytes,
with unique symbol renames for each case and image. Separate translation units
compile the unchanged target-generated kernels as VME and scalar-twin variants.
`binary-proof.json` records all32 object renames, their original and transformed
hashes, byte-identical executable sections and unique compiled exports. A changed
compiled instruction is a tested admission refusal.

The batch comprises the eight finite source/reference placement cases described
in [EXECUTED_OPERATORS.md](EXECUTED_OPERATORS.md), VME and scalar-twin variants,
and three distinct synthetic operand patterns:48 invocations. Every invocation
uses hart2 to write the full operands, poison every result word and hash the
actual producer memory, then one or two compute harts call their actual compiled
`_mlir_ciface_forward`. A fence follows that call inside the measured region.
All harts participate in every barrier. The producer is a scalar staging role;
this batch does not newly certify all Rocket vector instructions.

The console contains72 compute and48 producer `IRIS_REGION` rows,48 `IRIS_WORDS`
records with all3072 int32 and3072 W8A8 output words, and a unique successful
`IRIS_BATCH_DONE`. Every trial has a distinct case identity. The three patterns
vary the input values, rather than merely repeating a literal golden table.
The independent validator recalculates every accumulator, quantized output and
per-hart checksum. Output poisoning occurs before the compute barrier; the
producer checks those poison values before consumers start.

The exact immutable359 functional pair passes seeds0 and17 in11.49 and11.29
host seconds. The actual omitted-call ELF fails all3072 compute outputs and
exits nonzero. Nine qualification controls cover that real negative, changed
MLIR instruction bytes, full-word corruption, checksum/case identity and missing
completion/producer records. Ten managed-tool controls additionally reject
changed protection/readiness/source identity and an actual fitting archive used
under the wrong protected validation role. The first runner invocation omitted
the heterogeneous ISA transport and refused before guest execution; its logs
remain separate from the successful corrected invocations.

This corpus is **validation-only and unusable for fitting**, including GPT-OSS
and Gemma cases. TinyLlama remains protected validation-only. Meta's4096-wide
case is official-code reference coverage; the requested gated Llama2-7B
checkpoint is still unadmitted. No checkpoint weights or full model executes.
New physical timing observations may describe this instrumented ELF, but do not
retroactively qualify the previous standalone ELF or any checkpoint/model.

The frozen ready packet is `build/model-operator-batch-v1/ready.json`; its ELF
SHA256 is `af22419f8b095dfce0cf388468b0d0d88c251b130172ba3719b5e16154ca36f4`.
The prepared coordinator-owned job is
`runs/fpga-model-operator-batch-v1-001`. Preparation and verification from `/tmp`
both pass, with all337 input paths absolute. The job uses the original archived
driver, TSI step128,600-second foreground wall watchdog and780-second phase
bound, without `+max-cycles` because the loader itself can exceed5billion global
driver cycles and the original option uses32-bit parsing. The read-only FASED
observer is included. Preparation performs no hardware operation. The
coordinator must still check actual complete ownership/idle inspection and hold
the shared lock through all four managed phases.

After the coordinator completes cleanup and capture, validate the actual
archive with:

```sh
python3 firesim/analyze_model_operator_batch.py \
  runs/fpga-model-operator-batch-v1-001 \
  --output build/fpga-model-operator-batch-v1-001-analysis
```

The analyzer checks the exact archived ELF, corpus, source identities, all four
managed outcomes, raw UART and every full output word. It refuses a partial or
wrong-role run. A prepared packet and local functional passes do not imply that
the FPGA has executed the batch; only a successful managed archive can establish
that observation.
