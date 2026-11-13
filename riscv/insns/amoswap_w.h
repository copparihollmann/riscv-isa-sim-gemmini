require_extension(EXT_ZAAMO);
if (p->get_cfg().iris_vme) {
  const auto incoming = iris_definedness::truncate<int32_t>(STATE.XPR.read_transport(insn.rs2()));
  const auto previous = MMU.amo_transport<int32_t>(RS1, [&](const auto&) { return incoming; });
  p->iris_write_xpr_transport(insn.rd(), iris_definedness::extend_integer<reg_t>(previous));
} else {
  WRITE_RD(sext32(MMU.amo<uint32_t>(RS1, [&](uint32_t UNUSED lhs) { return RS2; })));
}
