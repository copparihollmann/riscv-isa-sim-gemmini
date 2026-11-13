require_extension('D');
require_fp;
IRIS_LOAD_FPR(uint64_t,f64,insn.rd(),RS1 + insn.i_imm());
