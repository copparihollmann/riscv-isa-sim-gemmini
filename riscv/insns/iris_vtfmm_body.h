// Included in each generated Spike instruction handler (P/STATE/insn are in scope).
ZVT_MTD(4);
ZVT_CHECK_ALIGN_RS1;
ZVT_CHECK_ALIGN_RS2;
ZVT_CHECK_RS1_EMUL;
ZVT_CHECK_RS2_EMUL;
require_extension(EXT_ZVTOFP8FMM);
require(P.VU.vsew == 8 && P.VU.widen == 4);
const unsigned iris_rm = STATE.frm->read_defined(pc);
if (iris_rm > 4)
  throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE: reserved frm for VME FP8");
{
  IrisSoftfloatScope iris_scope(iris_rm);
  // Functional execution has no cycle actor observing repeated C++ register
  // accesses. Cache operand reads/decodes within this instruction only. Lazy
  // first-use checks preserve the original tile/VRF definedness failure order;
  // this instruction never changes its vector operands. Empirical timing keeps
  // the original access path, and every MAC still uses sequential SoftFloat FMA.
  const bool iris_cached = P.get_cfg().iris_timing_fixture.empty();
  static thread_local std::vector<uint32_t> iris_a, iris_b;
  static thread_local std::vector<uint8_t> iris_a_valid, iris_b_valid;
  const size_t iris_m = P.VU.tm, iris_n = P.VU.tn();
  if (iris_cached) {
    iris_a.resize(iris_m * P.VU.tk);
    iris_b.resize(iris_n * P.VU.tk);
    iris_a_valid.assign(iris_a.size(), 0);
    iris_b_valid.assign(iris_b.size(), 0);
  }
  for (size_t m = 0; m < P.VU.tm; ++m) {
    for (size_t n = 0; n < P.VU.tn(); ++n) {
      if (!P.VU.tk) continue; // Zero K is a no-op; do not read an unknown tile.
      auto& cell = P.VU.mt_elt<uint32_t>(td, m, n);
      P.VU.iris_cell(cell, false);
      for (size_t k = 0; k < P.VU.tk; ++k) {
        uint32_t a, b;
        if (iris_cached) {
          const size_t ai = k * iris_m + m, bi = k * iris_n + n;
          if (!iris_a_valid[ai]) {
            iris_a[ai] = iris_fp8_to_f32(P.VU.elt<uint8_t>(insn.rs2() + 2*k, m), insn.rd() & 1);
            iris_a_valid[ai] = 1;
          }
          if (!iris_b_valid[bi]) {
            iris_b[bi] = iris_fp8_to_f32(P.VU.elt<uint8_t>(insn.rs1() + 2*k, n), P.VU.altfmt);
            iris_b_valid[bi] = 1;
          }
          a = iris_a[ai]; b = iris_b[bi];
        } else {
          a = iris_fp8_to_f32(P.VU.elt<uint8_t>(insn.rs2() + 2*k, m), insn.rd() & 1);
          b = iris_fp8_to_f32(P.VU.elt<uint8_t>(insn.rs1() + 2*k, n), P.VU.altfmt);
        }
        cell = f32_mulAdd(float32_t{a}, float32_t{b}, float32_t{cell}).v;
      }
    }
  }
}
// No require_fp/set_fp_exceptions: actual OP-VE FP8 uses VS and raw frm, with
// no FS legality gate and no connection to the backend's fflags collection.
ZVT_END;
