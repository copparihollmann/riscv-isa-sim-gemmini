# Source-bound operator coverage and 4 GiB planning

`audit_models.py` freezes only public configuration and weight-index JSONs, with
full model repository revisions, URLs, byte digests and independent source-code
pins. It downloads no weights and executes no remote model code. Recompute and
verify the derived plan offline with:

```sh
build/merlin-venv/bin/python workloads/audit_models.py --verify
```

An explicit `--refresh` selects new upstream revisions and downloads metadata.
`model-inputs.json` is the frozen input roster; `operator-coverage.json` contains
204 proposed operator cases and the memory contract. Every case is marked
unexecuted and numerically unqualified. These are structural coverage inputs,
not a claim that the full models run on Iris.

| Requested family | Exact frozen input | Relevant finding |
|---|---|---|
| GPT-OSS MoE | User-selected `openai/gpt-oss-20b`;120b exploratory | Hidden2880, Q output4096, KV output512;32/128 experts and top4 routing. The checkpoint uses MXFP4, which Iris must not decode as FP8. |
| Gemma4 “4B” | `google/gemma-4-E4B-it` and `google/gemma-4-26B-A4B-it` | E4B is an effective-size dense/PLE architecture; A4B is a distinct128-expert/top8 MoE. E4B is the selected first compiler baseline; A4B remains exploratory. The source distinction prevents treating effective parameter count as memory size. |
| Llama7B | `meta-llama/Llama-2-7b-hf` candidate | User-selected base checkpoint; exact config fetch returns HTTP401. Official pinned Meta ModelArgs/FeedForward defaults supply explicitly provisional4096-wide/32-layer/11008-FFN shapes; these remain ineligible for fitting until exact checkpoint admission. No mirror checkpoint is substituted. |
| TinyLlama | User-selected intermediate-step-1431k-3T base, with Chat-v1.0 archived as exploratory | Public configs are frozen for validation-only identity. They contribute no fitting or corpus-selection cases. |

The current Merlin checkout supplies a real TinyLlama headline loader, while
GPT-OSS, Gemma4 and Llama7B loaders/captures are absent from its public example
roster. Merlin explicitly protects TinyLlama as a claim workload in
`merlin/contract/claim_models.yaml`: its captures, names and measured shape
frequencies cannot define the fitting corpus. Independent iteration sources
include `examples/workloads/causal_decoder/loader.py`; this boundary is retained.
No captured answers or weights were inspected.

For GPT-OSS, original and Transformers-format configs are cross-checked
independently. Projection/expert shapes also cite the pinned OpenAI and
Transformers implementations. Gemma4 requires separate sliding/full attention
widths, shared KV ownership and PLE. The A4B full-attention V projection is absent
because V reuses K. The plan therefore does not equate hidden width with Q width,
count every layer as producing KV, or count an absent V GEMM.

At one byte per matrix parameter, selected weight matrices alone require at
least17.80GiB for GPT-OSS20B,106.79GiB for120B,5.70GiB for Gemma4E4B and21.27GiB
for Gemma4A4B. These are explicit formula-backed lower bounds, excluding other
weights and all runtime buffers. They exceed the4GiB physical DRAM. Native
GPT-OSS checkpoint index payloads also exceed4GiB. Converting checkpoint formats
is a separate checked numerical policy; native checkpoint bytes and int8 matrix
bytes are different quantities. No whole-model residency claim is made for any
family, including TinyLlama.

The proposed execution contract keeps a bounded producer on hart2 and VME tasks
on harts0/1. The producer stages only requested dense/expert panels into two
owned buffers; consumers publish completion before reuse. Candidate tests must
include empty experts, concentrated routing, balanced routing, expert churn,
small decode batches, tails, cold/warm panels, KV producer/consumer overlap and
contention with CPU-only compute. The initial source-bound shape cases use M=1,8,32,64
and source-derived projection widths; they do not encode a preferred schedule.

The memory plan uses a configurable256MiB software reserve and64MiB weight
panels as explicit planning policies, not hardware facts or tuned optima. Both
panels, code, stacks, OS, heap, activations, scales and actual KV ownership must
fit before admission. Shared/full-length Gemma KV allocations are still unknown.
The4GiB physical window is separate from Zephyr's smaller linked-image relocation
limit. A runtime streaming transport, numerical conversion policy and complete
memory admission remain unimplemented. Serial latency and bandwidth stay null;
no cycle prediction or +/-2% claim follows from these footprint calculations.

The primary configuration sources are the pinned URLs in the manifest. Google's
[Gemma4 model documentation](https://ai.google.dev/gemma/docs/core) distinguishes
effective parameter sizes, PLE and the separate MoE family. The official
[GPT-OSS config](https://huggingface.co/openai/gpt-oss-20b/blob/6cee5e81ee83917806bbde320786a8fb61efebee/config.json)
records its actual attention/expert geometry and MXFP4 declaration.

Only the20B/E4B source-derived cases are fit-eligible; their default plan is88cases. The28 provisional Llama cases and88 exploratory120B/A4B cases are separately marked ineligible. Required non-matrix coverage (normalization, rotary embeddings, softmax, nonlinearities, quantization, gathers and expert dispatch/combine) is recorded explicitly as unimplemented/unqualified. A successful GEMM kernel never implies those operations or a whole model are available.
