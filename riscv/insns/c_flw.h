require_extension(EXT_ZCF);
require_fp;
IRIS_LOAD_FPR(uint32_t,f32,insn.rvc_rs2s(),RVC_RS1S + insn.rvc_lw_imm());
