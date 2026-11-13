require_extension(EXT_ZCA);
if(P.VU.iris_mode) {
  const unsigned iris_dest=insn.rvc_rs1s();CHECK_REG(iris_dest);CHECK_REG(insn.rvc_rs1s());
  auto iris_left=STATE.XPR.read_transport(insn.rvc_rs1s());
  iris_definedness::Value<reg_t> iris_right;iris_right.value=insn.rvc_imm();iris_right.known.fill(0xff);
  [[maybe_unused]] constexpr bool iris_same=false;
  constexpr unsigned iris_kind=0;
#include "iris_bitwise_body.h"
} else {
WRITE_RVC_RS1S(RVC_RS1S & insn.rvc_imm());
}
