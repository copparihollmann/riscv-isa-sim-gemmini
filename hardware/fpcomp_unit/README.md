# Saved-Iris FPComp RTL check

Run from the repository root after generating the source-bound standalone RTL:

```sh
python3 hardware/fpcomp_unit/check.py --output build/fpcomp-rtl-unit
python3 hardware/fpcomp_unit/check.py --output build/fpcomp-rtl-unit --verify
```

The output directory must be new. Build and run logs, stimuli, integer-only
goldens, raw results, generated C++, binaries, source/tool/library digests and
archived input bytes are retained. `--verify` checks their integrity and replays
the output checker. Hardware is never contacted.

The test compiles the actual saved `FPCompPipe` and `FPCompPipe_2` modules and
their HardFloat dependencies. Its independent Python oracle imports no Spike
code. Across DLEN128 and DLEN256, it checks 8,448 valid pipeline outputs: all22
factory forms, IEEE16/32/64, signed zeros, infinities, NaNs, subnormals, arbitrary
bit patterns, full/zero/partial byte masks, destination element-group offsets and
the source's H/S-chunk exception selection. Another1,210 checks verify register
retention during pipeline bubbles. Two corrupted-output controls must fail.
No check assumes uninitialized registers hold zero.

This proves the selected functional unit at its sequencer interface. Scalar
broadcast, whole-instruction decoding, architectural fflags gating, vector
sequencing, reduction folding, load/store execution, context switching and
timing accuracy require separate tests. The reduction forms exercise their
element comparator here. This factory admits IEEE H/S/D; it does not implement
FP8 matrix or Mx arithmetic. The saved standalone IrisConfig FIR has a distinct
identity; association with Ethan's deployed FireSim image remains unverified.
