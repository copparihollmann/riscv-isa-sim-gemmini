// Iris fork: preserve strict upstream matching outside --iris-vme.
require(P.VU.iris_mode || ((insn.bits() & 0xfe007fff) == 0x5e006057));
ZVT_BASE;
ZVT_CHECK_ALIGN_RS2;
require(!P.VU.iris_mode || (P.VU.vsew == 32 && P.VU.widen == 1));

#define LOOP(type) for (size_t i = 0; i < P.VU.tn(); i++) { auto& cell = P.VU.tss_elt<type>(RS1, i); P.VU.write_tile_transport(cell,P.VU.read_transport<type>(insn.rs2(),i)); }

switch (P.VU.vsew) {
  case e8: require_extension(EXT_ZVT8E); LOOP(uint8_t); break;
  case e16: require_extension(EXT_ZVT16E); LOOP(uint16_t); break;
  case e32: LOOP(uint32_t); break;
  case e64: require_extension(EXT_ZVT64E); LOOP(uint64_t); break;
  default: abort();
}

ZVT_END;
