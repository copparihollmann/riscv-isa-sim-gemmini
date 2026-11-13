// Included in each generated Spike instruction handler (P/STATE/insn are in scope).
ZVT_MTD(4);
ZVT_CHECK_ALIGN_RS1;
ZVT_CHECK_ALIGN_RS2;
ZVT_CHECK_RS1_EMUL;
ZVT_CHECK_RS2_EMUL;
require_extension(EXT_ZVTOFP8FMM);
require(P.VU.vsew == 8 && P.VU.widen == 4);
const unsigned iris_rm = STATE.frm->read();
if (iris_rm > 4)
  throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE: reserved frm for VME FP8");
{
  IrisSoftfloatScope iris_scope(iris_rm);
  for (size_t m = 0; m < P.VU.tm; ++m) {
    for (size_t n = 0; n < P.VU.tn(); ++n) {
      if (!P.VU.tk) continue; // Zero K is a no-op; do not read an unknown tile.
      auto& cell = P.VU.mt_elt<uint32_t>(td, m, n);
      P.VU.iris_cell(cell, false);
      for (size_t k = 0; k < P.VU.tk; ++k) {
        const uint8_t a = P.VU.elt<uint8_t>(insn.rs2() + 2*k, m);
        const uint8_t b = P.VU.elt<uint8_t>(insn.rs1() + 2*k, n);
        cell = f32_mulAdd(float32_t{iris_fp8_to_f32(a, insn.rd() & 1)},
          float32_t{iris_fp8_to_f32(b, P.VU.altfmt)}, float32_t{cell}).v;
      }
    }
  }
}
// No require_fp/set_fp_exceptions: actual OP-VE FP8 uses VS and raw frm, with
// no FS legality gate and no connection to the backend's fflags collection.
ZVT_END;
