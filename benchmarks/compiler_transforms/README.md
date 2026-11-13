# Compiler transformation ablations

These experiments separate legal matrix offload from profitable lowering.
The candidates are experimental and do not change the compiler's defaults.
The persistent campaign notebook is
`/users/copparihollmann/iris-work/out/artifacts/fpga/model-shapes-20261108/compiler-tuning-v1/NOTES.md`.

`conv_pack.h` packs signed INT8 convolution into the existing matrix kernel's
K-major activation/weight layout. It preserves input bytes, padding zeros,
the reduction order `(input channel, kernel y, kernel x)` and wrapping INT32
results. Real-zero padding assumes a zero-point of zero; an asymmetric
quantization contract needs its own pad value and admission. The candidate
does not recompute activation scales per panel. `test_conv_pack.py` checks the exact C implementation against an
independent direct convolution, including layouts, asymmetric padding, stride,
batch transitions, partial panels and buffer guards:

```sh
python3 -m unittest discover -s benchmarks/compiler_transforms -p 'test_*.py' -v
```

`build_conv_ablation.py` creates a fresh source-bound snapshot of the admitted
v9 hand-kernel fixture. It never edits existing packets or launches hardware:

```sh
python3 benchmarks/compiler_transforms/build_conv_ablation.py \
  --source-v9 /absolute/path/to/frozen/v9 \
  --output /absolute/path/to/fresh/corpus
```

The corpus compares original full unfolding with 32-, 128- and 512-row
activation panels. Both NCHW/OIHW and NHWC/HWIO cases use batch1, H=W=64,
Ci=16, Co=64, a 3x3 kernel, stride1 and padding1. All four panel variants
within one layout use identical inputs and the exact same RVV/VME primitive
objects. The lowered GEMM is M=4096, N=64, K=144. Activation panel workspace
is 589,824 bytes for full unfolding, versus 4,608 / 18,432 / 73,728 bytes;
input, output and weight buffers are additional. This is a capacity calculation,
not measured cache or DRAM traffic.

Clean regions include weight reordering, activation unfolding, all primitive
calls and the completion fence. They contain no internal phase CSR reads.
Profile variants separately expose preparation and matrix costs, with their
own overhead. Output hashes, independent host oracles, anchors and all buffer
guards must pass; the small control corpus additionally checks every word.
Native results are functional admissions, never hardware cycle measurements.

Blocking can improve locality and workspace while increasing dispatch overhead
or repeated weight reads. Its speedup is unknown until measured. Static weight
prepacking is a distinct candidate: this corpus deliberately retains the same
runtime weight reordering cost on both routes. The guarded NCHW 1x1 zero-copy
activation predicate has host tests but is not enabled in this corpus.

Projections already have GEMM form. Weight prepacking, compatible QKV or
gate/up fusion, and existing-token row blocking are separate candidates. QKV
fusion grows N, not M, so it does not fill absent token rows during single-token
decode. Row batching may use existing prefill rows or independent requests;
causally dependent future decode tokens cannot simply be batched. Preserve
each original quantization recipe, row scale and output-channel weight scale.

Any hardware execution requires fresh preparation, a root-reviewed managed
queue and the complete ownership/inspection/shared-lock checks in
`../../firesim/OPERATING_RULES.md`. Every job uses
kill -> infrasetup -> runworkload -> kill, owned cleanup and archive. This
directory provides no hardware bypass or automatic launch entry point.
