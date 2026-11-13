require_extension(EXT_ZCD);
require_fp;
IRIS_LOAD_FPR(uint64_t,f64,insn.rd(),RVC_SP + insn.rvc_ldsp_imm());
