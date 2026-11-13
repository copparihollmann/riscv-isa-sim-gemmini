# Actual INT8/OFP8 OPU cell check

```sh
python3 hardware/opu_cell/check.py --output build/opu-cell-rtl-proof-v2
python3 hardware/opu_cell/check.py --output build/opu-cell-rtl-proof-v2 --verify
```

Use a new output directory. The check compiles the saved `OuterProductCell`
and its real HardFloat dependencies, bound to the standalone Iris FIR hash.
It never contacts hardware or edits the original source/functional corpora.
Sources, independent oracle, generated RTL/C++, binary, corpus, logs and
compiler/runtime inputs are archived with digests and full audited repository
pins. This is a compute-cell proof, not an image build attestation.

The integer corpus exhausts all256×256operand bit pairs and all four
signed/unsigned combinations:262,144 cases with rotating32-bit accumulators,
wrapping addition and all16MRF destinations. Full entry scans check isolation;
separate controls check mvin, zeroing and update priority. Every entry is
explicitly initialized because the physical MRF registers are unreset.

The FP8 corpus exhausts all256×256pairs and all four E4M3/E5M2 format
combinations at RNE, with rotating FP32 accumulators. Another10,260 sequences
use the existing independent integer-only exact FMA oracle, all five legal
IEEE rounding modes and up to four sequential FP32 accumulations. It includes
NaNs, infinities, signed zeros, subnormals, cancellation and the known distinction
between sequential FP32 rounding and a bulk dot product. There is no host
floating-point computation in either oracle.

The full run checks272,404 FP8 sequences and288,317 FP8 MACs, including32 batches
of16distinct destinations issued on consecutive edges. Same-entry FP8 accesses
wait for completion; batch rounding mode stays constant. A directed latency
test confirms the cell update two edges after acceptance. No fflags output
exists on this cell interface. Corrupted-golden and truncated-corpus controls
must both fail.

These checks validate one cell's arithmetic and local state. Whole-instruction
decode, array/sequencer behavior, tile edges, VRF transport, per-hart placement,
OS contexts and full utilization/timing qualification require their own evidence.
The saved standalone design remains distinct from Ethan's deployed image.
