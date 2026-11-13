// Native FP8 FMA-class operations, source-matched flags and physical-lane NaNs.
if (P.get_id() >= 2)
  throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: hart 2 has no Mx FP8 arithmetic datapath");
require_vector(true);
require_extension(EXT_ZVFOFP8MIN);
const bool iris_vf = insn.funct3() == 5;
if (iris_vf) require_fp;
VI_CHECK_SSS(!iris_vf);
const unsigned iris_rm = STATE.frm->read_defined(pc);
if (iris_rm > 4) throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE native FP8");
const unsigned iris_f6 = insn.bits() >> 26;
const reg_t iris_vl = P.VU.vl->read();
uint8_t iris_flags = 0;
bool iris_wrote = false;
for (reg_t i = P.VU.vstart->read_defined(pc); i < iris_vl; ++i) {
  if (!insn.v_vm() && !P.VU.mask_elt(0, i)) continue;
  // Native FPFMA writes fcsr_flags.valid even when E4 flags are zero.
  if (!STATE.sstatus->enabled(MSTATUS_FS))
    throw std::runtime_error("IRIS_RTL_ASSERT: native FP8 write requires mstatus.FS > 0");
  const uint8_t vs2 = P.VU.elt<uint8_t>(insn.rs2(), i);
  const uint8_t vs1 = iris_vf ? uint8_t(READ_FREG(insn.rs1()).v[0]) : P.VU.elt<uint8_t>(insn.rs1(), i);
  const uint8_t old=(iris_f6>=0x28&&iris_f6<=0x2f)?P.VU.elt<uint8_t>(insn.rd(),i):0;
  auto& dest = P.VU.elt<uint8_t>(insn.rd(), i, true);
  uint8_t a=vs2,b=vs1,c=old;
  unsigned cmd=0;
  if (iris_f6 == 0 || iris_f6 == 2 || iris_f6 == 0x27) {
    b=P.VU.altfmt?0x3c:0x38;c=vs1;
    cmd=iris_f6==2?1:iris_f6==0x27?2:0;
  } else if (iris_f6 == 0x24) {
    c=(a^b)&128;
  } else {
    const unsigned cmds[4]={0,3,1,2};cmd=cmds[iris_f6&3];
    if (iris_f6 < 0x2c) {a=old;c=vs2;}
  }
  const auto result=iris_fp8::fma(a,b,c,P.VU.altfmt,iris_rm,cmd,i&7);
  dest=uint8_t(result.bits);iris_flags|=result.flags;iris_wrote=true;
}
if (iris_wrote) STATE.fflags->accumulate(iris_flags);
VECTOR_END;
