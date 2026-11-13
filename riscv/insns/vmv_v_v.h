// vvmv.v.v vd, vs1
VI_VV_MERGE_LOOP
({
  vd = vs1;
  P.VU.copy_element_mask(insn.rd(),insn.rs1(),i);
})
