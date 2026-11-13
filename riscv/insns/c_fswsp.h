require_extension(EXT_ZCF);
require_fp;
IRIS_STORE_FPR(uint32_t,RVC_SP + insn.rvc_swsp_imm(),insn.rvc_rs2());
