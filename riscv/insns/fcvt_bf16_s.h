// No scalar BF16 decode exists in pinned Iris Rocket/Shuttle RTL, despite ISA advertisement.
if (P.VU.iris_mode) throw trap_illegal_instruction(insn.bits());
require_extension(EXT_ZFBFMIN);
require_fp;
softfloat_roundingMode = RM;
WRITE_FRD_BF(f32_to_bf16(FRS1_F));
set_fp_exceptions;
