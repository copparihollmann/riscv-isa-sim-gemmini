if(P.VU.iris_mode) {
  const unsigned iris_dest=insn.rd();CHECK_REG(iris_dest);CHECK_REG(insn.rs1());
  auto iris_left=STATE.XPR.read_transport(insn.rs1());
  iris_definedness::Value<reg_t> iris_right;iris_right.value=insn.i_imm();iris_right.known.fill(0xff);
  [[maybe_unused]] constexpr bool iris_same=false;
  constexpr unsigned iris_kind=2;
#include "iris_bitwise_body.h"
} else {
WRITE_RD(insn.i_imm() ^ RS1);
}
