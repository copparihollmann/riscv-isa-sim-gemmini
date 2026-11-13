// Iris fork: preserve strict upstream matching outside --iris-vme.
require(P.VU.iris_mode || ((insn.bits() & 0xfffff0ff) == 0x43e06057));
ZVT_MTD(P.VU.iris_mode ? 4 : 16);
require(!P.VU.iris_mode || P.VU.tew() == 32);

ZVT_MN_LOOP
({
  switch (tew) {
    case 8: P.VU.mt_elt<uint8_t>(td, m, n) = 0; break;
    case 16: P.VU.mt_elt<uint16_t>(td, m, n) = 0; break;
    case 32: { auto& cell = P.VU.mt_elt<uint32_t>(td, m, n); cell = 0; P.VU.iris_cell(cell, true); break; }
    case 64: P.VU.mt_elt<uint64_t>(td, m, n) = 0; break;
    default: abort();
  }
})

ZVT_END;
