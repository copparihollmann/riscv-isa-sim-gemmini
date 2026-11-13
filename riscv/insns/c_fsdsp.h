require_extension(EXT_ZCD);
require_fp;
IRIS_STORE_FPR(uint64_t,RVC_SP + insn.rvc_sdsp_imm(),insn.rvc_rs2());
