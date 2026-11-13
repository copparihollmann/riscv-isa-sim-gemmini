// Iris fork: preserve strict upstream matching outside --iris-vme.
require(P.VU.iris_mode || ((insn.bits() & 0xfff0707f) == 0x43f06057));
ZVT_BASE;
ZVT_CHECK_ALIGN_RD;
if (P.VU.iris_mode && (RS1 & (reg_t(1) << 24)))
  throw std::runtime_error("IRIS_UNSUPPORTED_COLUMN_MOVE hart=" + std::to_string(P.get_id()) +
    " pc=" + std::to_string(pc) + " capability=column-move-out; elaborated OPU has no column readout datapath");
require(!P.VU.iris_mode || (P.VU.vsew == 32 && P.VU.widen == 1));

#define LOOP(type) for (size_t i = 0; i < P.VU.tn(); i++) { auto& cell = P.VU.tss_elt<type>(RS1, i); P.VU.iris_cell(cell, false); P.VU.elt<type>(insn.rd(), i, true) = cell; }

switch (P.VU.vsew) {
  case e8: require_extension(EXT_ZVT8E); LOOP(uint8_t); break;
  case e16: require_extension(EXT_ZVT16E); LOOP(uint16_t); break;
  case e32: LOOP(uint32_t); break;
  case e64: require_extension(EXT_ZVT64E); LOOP(uint64_t); break;
  default: abort();
}

ZVT_END;
