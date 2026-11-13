This separate baremetal packet exercises signed INT8-to-INT32 and E4M3/E4M3-to-FP32 matrix multiplication on each compute hart individually. It includes diagonal dimensions 8, 16, 32, 64, 128 and 256, plus M=N=32 with K=8, 16, 64, 128 and 256: 11 unique shapes, two dtypes, two harts and three trials, totaling 132 measured regions.

The source-compatible strategy uses a single 32×32 accumulator tile, clamps TM/TN at 8/16/32, and sets TK=1. Operand rows are loaded once per output tile and reused across every real K matrix instruction. Every result row uses supported row readout, a vector store and a fence before scalar copying. The measured kernel includes configuration, operand preparation/loading, all matrix operations, readout, stores and copying. This is an explicit baseline kernel strategy; it is not a claim about an optimized compiler kernel or peak hardware throughput.

Inputs use finite signed values of magnitude 1–4. All products and sums are exact representable integers in FP32, including the FP8 path. This permits a host integer MAC oracle and an independent closed-form every-word validator. The packet archives 1,109,760 expected words, poisons every destination outside the ROI, checks every output word on target and compares its independently computed full-output FNV checksum. E5M2, special values, other rounding modes and arbitrary model operators are outside this packet's scope.

All three harts boot. Hart 2 explicitly executes the matrix discard encoding, verifies exactly one illegal instruction, emits a typed refusal record and participates in barriers/WFI. No matrix arithmetic runs on hart 2.

All dtype/hart/trial variants of shapes 16×16×16, 128×128×128 and 32×32×64 were reserved before hardware. Their 36 timing labels remain coordinator-only. The training export contains 96 other regions and removes absolute timestamps. TinyLlama and the pre-existing global workload holdouts are not used here.

The frozen positive ELF and qualification are in `build/pow2-matrix-single-v2`; the earlier v1 directory preserves a compile refusal. Seeds 0 and 17 each passed all 132 regions and all 1,109,760 words in about 11 seconds. A separately compiled kernel-omission ELF failed every word in every region and exited nonzero. The independent proof validates all 132 compiled 40-byte case records, both actual matrix opcodes, the record ABI, file-backed completion sentinel, CLINT/CSR order and 25 corruption controls.

The coordinator's prepared job is `runs/fpga-pow2-matrix-single-v1-001`; its PRELAUNCH identity is recorded in `build/pow2-matrix-single-packet-closure-v1/report.json`. After the managed run, only the coordinator should analyze the combined archive:

```sh
python3 firesim/analyze_pow2_packets_v2.py --kind matrix \
  runs/fpga-pow2-matrix-single-v1-001 \
  --output build/NEW-ROOT-ONLY-matrix-analysis \
  --training-export build/NEW-matrix-TRAIN-only-export
```

The additive v2 adapter fixes retention of inventory-hashed readiness metadata without changing the frozen guest, runtime or numerical validator. This packet alone certifies neither full FPGA/source association nor complete functional/timing coverage or a universal 2% error bound.
