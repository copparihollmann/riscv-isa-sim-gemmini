require_extension(EXT_ZCF);
require_fp;
IRIS_STORE_FPR(uint32_t,RVC_RS1S + insn.rvc_lw_imm(),insn.rvc_rs2s());
