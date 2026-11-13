# Executed source-shaped INT8 compiler gates

The finite small-M gates in `build/workload-small-M-v1` execute real Merlin
MLIR-to-LLVM output on the selected experimental 28a0 Spike model. Every case
uses all three physical harts: hart2 supplies operands and poisons the output,
then one or two compute harts execute the generated VME code. The same compiler
objects also run with the target's scalar twin. All 64 int32 accumulators and all
64 W8A8 output words match a separate mathematical oracle in each image.

| Source family | Executed global M,N,K | Contraction scope | Compute placement |
|---|---|---|---|
| OpenAI GPT-OSS20B | 2,32,2880 | Full router **linear contraction**, without its bias, normalization, top-k, dispatch or experts | h0; h0+h1 |
| Google Gemma4 E4B | 2,32,2560 | First32 output columns of the first sliding-attention Q projection (full width2048) | h0; h0+h1 |
| TinyLlama1.1B base | 2,32,2048 | First32 output columns of Q (full width2048); validation-only | h0; h0+h1 |
| Official Meta implementation reference | 2,32,4096 | A separately labeled reference-code contraction using `ModelArgs.dim`; exact Llama2-7B checkpoint admission remains unavailable | h0; h0+h1 |

For two compute harts each worker compiles and executes a local M=1 call. The
single compute hart executes M=2. Each shipped ROI reports exactly its local
M*N*K INT8 MACs through actual retired VME instructions, and ends with no pending
compute actor. Actual executable-section decoding distinguishes the VME image
from the scalar twin. The independent qualification is
`build/workload-operator-qualification-v2/report.json`: eight case/placement
pairs,16 images,1024 int32 and1024 W8A8 words, and4348 verified unique inputs.

These are synthetic signed-INT8 operand tests. No checkpoint weights, conversion
from MXFP4/BF16, complete projection (except the router contraction itself),
attention block, MoE block, model capture or full model is executed. The W8A8
check is the explicit synthetic rounding/saturation policy in the guest; it is
not qualification of any checkpoint quantizer. The new shapes run baremetal;
existing Zephyr/compiler gates are separate evidence. Their modeled counters
are available, but timing accuracy for these new shapes is unmeasured. Nothing
here certifies +/-2% accuracy or adds calibration examples. TinyLlama remains
validation-only, and **all** cases in this execution set are excluded from
fitting.

## Explicit small-M capability route

The original target's selector delegates to
`merlin.llvmlower.int8_contractions.tile_filling_selector`, which selects only
when both output dimensions reach TE32. The original M2 GPT-OSS attempt therefore
routes zero contractions and refuses compilation. This is preserved under
`build/workload-operators-v1`; it is a tile-utilization policy, rather than a
hardware rejection of M1/2.

`workloads/iris-mlir-small-m` is a private copy of the target. Its sole behavioral
change is an explicit `IRIS_EXPERIMENTAL_SMALL_M_VME=1` selector extension for
rank2 INT8 contractions with M1/2, N32 and positive K divisible by4. TE must32.
The normal policy is unchanged when this flag is absent. This capability-test
route makes no automatic profitability decision. The existing target kernel's
clamped path writes TM, loads only the active rows and reads `r < tm`; the pinned
Saturn sequencer uses TM/TN to enable array rows/columns. The actual gates test
this path rather than bypassing compilation or publishing a scalar result as
VME output. The original bound target/provider/native bytes remain unchanged.

The12 selector controls are recorded in
`build/workload-small-M-admission-v1/report.json`. The omission control under
`build/workload-small-M-noop-v1` compiles away only the kernel call: all64 poisoned
accumulators remain wrong, the guest reports64 errors, and HTIF exits nonzero.
Six further receipt/output/ownership corruptions are rejected by the independent
qualification reader. The copied target's original provenance file describes
its parent; `small-m-companion.json` and the new qualification explicitly bind
the selector override and do not relabel the parent as changed.

The larger M32 original-policy GPT-OSS attempt in
`build/workload-operators-v2` produced a correct1024-output VME image, but its
scalar-twin run exceeded the300-second host bound. This remains an incomplete
gate. The successful M1/2 capability tests do not erase that timeout or change
the original default selector.

## Source identities and exact scope

The full40-character revisions and config digests remain in
`model-inputs.json` and each execution's `case.json`.

- GPT-OSS20B uses config revision
  `6cee5e81ee83917806bbde320786a8fb61efebee`. Official OpenAI `MLPBlock.gate`
  confirms hidden2880→32 experts, including a bias that is explicitly excluded
  from this contraction test. The checkpoint's MXFP4 declaration is not FP8 or
  a verified INT8 conversion.
- Gemma4 E4B uses config revision
  `4ecc2ba63bcac23ba4a767fc87025b1450f84c9c`. Its first layer is sliding
  attention:8 heads ×256 head dimensions =2048 Q columns. The separate full
  attention head dimension512 does not apply to this case. PLE, multimodal
  branches, KV sharing and attention computation remain outside the gate.
- TinyLlama base uses revision
  `59f6f375b26bde864a6ca194a9a3044570490064`, hidden2048 and32 heads. Its Chat
  variant is archived but unexecuted. No TinyLlama-derived data is a fitting
  input.
- The pinned requested Llama2-7B config
  `01c7f73d771dfac7d292323805ebc428287df4f9` still returns HTTP401 without
  credentials, recorded in `build/workload-source-access-v1/report.json`.
  The4096 reference dimension is the official Meta source default at
  `689c7f261b9c5514636ecc3c5fefefcbb3e6eed7`; it is **not** claimed as admission
  of that gated checkpoint.

Official OpenAI implementation pin:
`277020131d524f06bed5f66b694a92ed7f6e5224`. Transformers implementation pin:
`f262c71703eb138381d65ced86b3aaa496be0196`. Exact source files, line references
and digests are frozen by the companion source-facts receipt.

## Reproduce and inspect

The build entrypoint explicitly requires the selected28 empirical package and
fails if the current native epoch differs. Run from the repository root with
the pinned compiler environment; each output directory must be new:

```sh
build/merlin-venv/bin/python workloads/operator_execution_small_m.py \
  --case gpt-oss-20b --harts 2 --timeout 180 \
  --output build/my-gpt-small-M
python3 workloads/check_operator_execution.py \
  --output build/my-operator-qualification
```

The other case names are `gemma4-e4b`, `tinyllama-base` and
`meta-official-reference`. The latter remains reference-only. Each result binds
the real `_mlir_ciface_forward` objects, provider-generated descriptor bridge,
kernel source, RV64 ELF, full console, counter prefixes, physical ROM/DTB,
selected manifest, native/UART pair and executed argv. The chosen selected28
package has explicit experimental accuracy and known-divergence limits. These
receipts do not remove the known original Zephyr hart2 context stall or
page-crossing vector-store hardware divergence.

The closure snapshots all declared input bytes, direct build outputs and failed
attempt evidence. Compiler/system headers not declared by the existing compiler
artifact API are not claimed to form a complete rebuild closure. No new FPGA
contact or global-held-out timing observation was performed.
