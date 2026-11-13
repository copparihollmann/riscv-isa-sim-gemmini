require_extension(EXT_ZCF);
require_fp;
IRIS_LOAD_FPR(uint32_t,f32,insn.rd(),RVC_SP + insn.rvc_lwsp_imm());
