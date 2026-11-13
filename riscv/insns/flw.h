require_extension('F');
require_fp;
IRIS_LOAD_FPR(uint32_t,f32,insn.rd(),RS1 + insn.i_imm());
