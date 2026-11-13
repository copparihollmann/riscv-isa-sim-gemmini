require_extension(EXT_INTERNAL_ZFH_MOVE);
require_fp;
IRIS_LOAD_FPR(uint16_t,f16,insn.rd(),RS1 + insn.i_imm());
