require_extension(EXT_ZAAMO);
require_rv64;
if (p->get_cfg().iris_vme) {
  const auto incoming = iris_definedness::truncate<int64_t>(STATE.XPR.read_transport(insn.rs2()));
  const auto previous = MMU.amo_transport<int64_t>(RS1, [&](const auto&) { return incoming; });
  p->iris_write_xpr_transport(insn.rd(), iris_definedness::extend_integer<reg_t>(previous));
} else {
  WRITE_RD(MMU.amo<uint64_t>(RS1, [&](uint64_t UNUSED lhs) { return RS2; }));
}
