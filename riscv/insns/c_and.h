require_extension(EXT_ZCA);
if(P.VU.iris_mode) {
  const unsigned iris_dest=insn.rvc_rs1s();CHECK_REG(iris_dest);CHECK_REG(insn.rvc_rs1s());
  auto iris_left=STATE.XPR.read_transport(insn.rvc_rs1s());
  CHECK_REG(insn.rvc_rs2s());auto iris_right=STATE.XPR.read_transport(insn.rvc_rs2s());
  [[maybe_unused]] const bool iris_same=insn.rvc_rs1s()==insn.rvc_rs2s();
  constexpr unsigned iris_kind=0;
#include "iris_bitwise_body.h"
} else {
WRITE_RVC_RS1S(RVC_RS1S & RVC_RS2S);
}
