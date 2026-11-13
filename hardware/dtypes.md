# Iris datatype audit

**The configured compute harts have FP8 hardware.** `IrisConfig` selects
`VectorParams.opuMxParams` for harts 0–1: that enables vector Mx FMA/conversion and
the Mx outer-product unit. Their matrix unit accepts int8 or OFP8 E4M3/E5M2
operands and accumulates into 32-bit tiles. Hart 2 has no matrix unit.

This is a source and elaboration audit, not a certification of the deployed image
or of simulator support. [dtypes.json](dtypes.json) records 93 per-hart capability
rows, operation groups, input/output/accumulator types, source-line citations,
full commits, source hashes, and repository dirty-patch hashes. The main hardware
manifest is unchanged. The CPU configuration is heterogeneous and cannot be
represented correctly by one global dtype list.

| Group / operation | Harts 0–1: Shuttle + Saturn OPU | Hart 2: Rocket + Saturn DMA |
| --- | --- | --- |
| Scalar integer | 8/16-bit storage, promoted register arithmetic; native 32/64-bit arithmetic and atomics | Same width classes |
| Vector integer | Signed/unsigned 8/16/32/64-bit arithmetic; 8→16, 16→32, 32→64 widening multiply/MAC | Same width classes; iterative multiply/divide |
| Scalar IEEE floating point | Full FP16/FP32/FP64 H/S/D arithmetic, conversions, divide/sqrt | Full FP16/FP32/FP64 H/S/D arithmetic, conversions, divide/sqrt |
| Vector IEEE floating point | FP16/FP32/FP64; SIMD FMA, iterative divide/sqrt, H/S/D comparisons | FP16/FP32/FP64; FMA through shared scalar FPU, elementwise |
| Scalar BF16 | No executable scalar conversion entry despite `zfbfmin` advertisement; no BF16 scalar arithmetic path | No scalar BF16 conversion/arithmetic path |
| Vector BF16 | Add/sub/multiply/FMA/reduction subset; widening arithmetic to FP32; FP32↔BF16 conversion | Raw bit storage only; no Mx arithmetic/conversion path |
| Vector FP8 | OFP8 E4M3/E5M2 add/sub/multiply/FMA/reduction subset; widening to BF16; BF16↔FP8 conversion | Raw bit storage only; no FP8 arithmetic datapath |
| VME integer | Any signed/unsigned int8 operand combination → 32-bit wrapping accumulation | Absent |
| VME floating point | Any E4M3/E5M2 operand-format combination → FP32 accumulation | Absent |
| VME other native inputs | No int4/int16/int32/int64, FP16/BF16/FP32/FP64 matrix-multiply input path | Absent |

“Supported width classes” does not mean every operation exists for every pair of
types. In particular, vector BF16/FP8 FMA support does not add BF16/FP8 divide,
sqrt, compare/minmax, or integer-conversion semantics to units that only implement
H/S/D. FP32 tile moves transfer raw 32-bit data; they do not imply a native
FP32×FP32 matrix multiplication. Packed int4 is possible in software, with no
native int4 arithmetic identified here. The label “BF8” is ambiguous: select an
explicit format rather than assigning it an unsupported hardware meaning.

The scalar BF16 finding is stronger than an absent mnemonic search: both FCVT
encodings have no fixed-bit intersection with **any of the 835** 32-bit patterns
in the pinned Rocket instruction definitions. Scalar/FPU decoder tables select
from those definitions; Saturn's early vector decoder excludes scalar opcode
`0x53`. The generated audit rechecks this proof and retains the exact instruction
and decoder sources. This resolves the source advertisement discrepancy. A
subsequent actual managed FPGA batch also tested both conversion families on
every hart: all 720 regions (eight rounding-mode fields, three source bit
patterns, five trials) produced precise illegal-instruction traps and preserved
destination/FCSR bits. [Observed hardware evidence](actual-scalar-bf16-observation.json)
binds the exact ELF, selected image/driver, source pins, raw archive and independent
validation. Full source-to-image association remains unverified; this result
concerns scalar conversion encodings and does not remove vector BF16 support.

## Why the DMA comment is insufficient

The comment above `dmaParams` says “only does memcpys,” but the constructor does
not disable execution units. It inherits `VectorIssueStructure.Unified`, whose
factory creates integer units and all ordinary FP units. A zero-depth execute
queue bypasses storage (`io.deq <> io.enq`), rather than removing computation.
Hart 2 consequently has integer arithmetic and shared-FPU vector FP16/32/64
paths. This conclusion follows the instantiated factories and queue semantics,
not its VLEN or its nickname.

Compute harts use DLEN 128, and hart 2 uses DLEN 256; all have VLEN 256 and ELEN
64. The compute default `useElementwiseFP64=false` means double-precision lanes
remain instantiated across the SIMD datapath. It does not disable FP64.

## Exact FP8 matrix behavior

The [input conversion](dtypes-evidence/fp8-expand.scala) maps OFP8 E4M3 into an
internal E5M3 representation. E4M3 has signed zero, subnormals down to 2^-9,
maximum finite magnitude 448, and NaNs at bytes `0x7f`/`0xff`; it has no infinity.
E5M2 maps exactly by appending a zero mantissa bit, with signed zero, subnormals
down to 2^-16, maximum finite magnitude 57344, infinities, and NaNs. Internal
E5M3 is an implementation format, not an additional software FP8 storage type.

The [OPU datapath](dtypes-evidence/opu.scala) widens operands to FP32 and performs
sequential FP32 fused multiply-adds using the instruction's `frm` and tininess
after rounding. A's format comes from instruction bit 7 and B's from `altfmt`,
so mixed E4M3/E5M2 operands are supported. This differs from rounding one bulk
dot product only once. OPU exception flags are not wired into architectural
`fflags`; a matching functional model must preserve that behavior. The
[HardFloat rounder](dtypes-evidence/hardfloat-round.scala) canonicalizes NaN sign
and payload. Reserved rounding modes still require explicit behavior validation.

The elaborated OPU port excerpt includes `fp8`, `e5m2_l`, `e5m2_t`, and `rm`,
corroborating that an FP8 datapath exists in the local elaboration. This does not
prove the deployed bitstream's identity.

## Advertised/configured discrepancies

- The compute-hart DTS advertises scalar `zfbfmin` through its vector extension
  list. The reviewed scalar FPU has H/S/D conversion and arithmetic tables, with
  no BF16 scalar conversion path identified. The audit marks scalar BF16
  conversion absent by source decode proof. The selected FPGA image now also
  refuses all 16 tested conversion/rounding encodings precisely on all three
  harts; see the bound observation above. The extension name alone does not
  enable scalar conversion in the model.
- `useOpuColReadout` remains false through the actual config composition. The
  [elaborated port excerpt](dtypes-evidence/fir-opu-ports.txt) has no horizontal
  column-read pipe or `out_col`. Column writes exist, but column reads cannot be
  treated as implemented architectural column reads. Broad opcode acceptance is
  not evidence of the missing datapath, and the audit does not invent an illegal
  instruction trap. Passing upstream Spike column-read tests does not resolve
  this hardware mismatch.
  A subsequent managed FPGA observation now confirms the practical mismatch:
  all 384 column attempts were accepted without a trap, but none returned the
  mathematical column of the explicitly initialized tile. Each had 30–32 wrong
  words out of 32, while all 768 surrounding row checksum controls passed.
  This covers both compute harts, every index, two patterns and three trials;
  normalized readout shapes repeated across all 12 conditions per index.
  [Exact observed evidence](actual-vme-column-observation.json) binds raw words,
  ELF/image/driver/source identities and independently verified archive bytes.
  The model retains an explicit capability refusal. Arbitrary fallback data
  and a fabricated architectural illegal trap are not substituted for a usable
  column operation. Full source/image association remains unverified.

## Provenance and checks

The audit uses Chipyard `b4542facf6cc9457f6e358e8f80a8b3a0ff5df19`, Saturn
`536774bd4c5e3bcd7813a4a0dc72fc87e5818532`, Rocket
`fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0`, Shuttle
`a536ed1df91a0f65770e36758291d02a8cb929c4`, and HardFloat
`0ecaef097ce2accbd16a61613699450ed5533f29`. Local tracked modifications and each
audited file's exact bytes are separately identified. HardFloat is cloned at
its clean exact pin under `third_party/hardfloat`.

```sh
python3 hardware/dtypes.py --verify
python3 hardware/dtypes.py --verify-live
python3 -m iris_model.capabilities --hart 0 --unit vme --dtype ofp8_e4m3 --role input --operation mac
python3 -m iris_model.capabilities --hart 2 --unit vector --dtype f64 --operation fma
```

The first command verifies frozen source hashes and line references offline;
the second also checks the original local source bytes. Query output reports
configured hardware capabilities separately from simulator certification. No
timing throughput or accuracy value is inferred by this audit.
