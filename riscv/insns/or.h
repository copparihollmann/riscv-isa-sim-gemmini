if(P.VU.iris_mode) {
  const unsigned iris_dest=insn.rd();CHECK_REG(iris_dest);CHECK_REG(insn.rs1());
  auto iris_left=STATE.XPR.read_transport(insn.rs1());
  CHECK_REG(insn.rs2());auto iris_right=STATE.XPR.read_transport(insn.rs2());
  [[maybe_unused]] const bool iris_same=insn.rs1()==insn.rs2();
  constexpr unsigned iris_kind=1;
#include "iris_bitwise_body.h"
} else {
WRITE_RD(RS1 | RS2);
}
