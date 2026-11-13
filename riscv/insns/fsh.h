require_extension(EXT_INTERNAL_ZFH_MOVE);
require_fp;
IRIS_STORE_FPR(uint16_t,RS1 + insn.s_imm(),insn.rs2());
