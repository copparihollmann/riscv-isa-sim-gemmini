require_extension(EXT_ZCA);
require(insn.rvc_rd() != 0);
IRIS_LOAD_XPR(int32_t,insn.rd(),RVC_SP + insn.rvc_lwsp_imm());
