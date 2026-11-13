require_extension(EXT_ZCD);
require_fp;
IRIS_STORE_FPR(uint64_t,RVC_RS1S + insn.rvc_ld_imm(),insn.rvc_rs2s());
