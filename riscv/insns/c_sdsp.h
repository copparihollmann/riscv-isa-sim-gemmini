require_extension(EXT_ZCA);
require((xlen == 64) || p->extension_enabled(EXT_ZCLSD));

if (xlen == 32) {
  MMU.store<uint64_t>(RVC_SP + insn.rvc_sdsp_imm(), RVC_RS2_PAIR);
} else {
  IRIS_STORE_XPR(uint64_t,RVC_SP + insn.rvc_sdsp_imm(),insn.rvc_rs2());
}
