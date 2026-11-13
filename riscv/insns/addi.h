if(P.VU.iris_mode&&insn.i_imm()==0) {CHECK_REG(insn.rd());CHECK_REG(insn.rs1());p->iris_write_xpr_transport(insn.rd(),STATE.XPR.read_transport(insn.rs1()));}
else {
WRITE_RD(sext_xlen(RS1 + insn.i_imm()));
}
