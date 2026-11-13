require_extension(EXT_ZCD);
require_fp;
IRIS_LOAD_FPR(uint64_t,f64,insn.rvc_rs2s(),RVC_RS1S + insn.rvc_ld_imm());
