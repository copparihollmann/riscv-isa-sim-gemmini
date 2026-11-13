require_extension(EXT_ZCA);
if(P.VU.iris_mode)p->iris_write_xpr_transport(insn.rd(),STATE.XPR.read_transport(insn.rvc_rs2()));
else WRITE_RD(RVC_RS2);
