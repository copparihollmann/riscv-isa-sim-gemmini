#include "fp_operand_timing.hpp"
#include <iostream>
#include <stdexcept>

static void check(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}
int main() {
  using spike_timing::fp_divsqrt_special;
  const auto boxed32 = [](std::uint32_t word) { return UINT64_C(0xffffffff00000000) | word; };
  for (unsigned width : {32u, 64u}) {
    const auto box = [&](std::uint64_t word) { return width == 32 ? boxed32(word) : word; };
    const auto one = width == 32 ? UINT64_C(0x3f800000) : UINT64_C(0x3ff0000000000000);
    const auto sign = width == 32 ? UINT64_C(0x80000000) : UINT64_C(0x8000000000000000);
    const auto infinity = width == 32 ? UINT64_C(0x7f800000) : UINT64_C(0x7ff0000000000000);
    const auto special = [&](bool sqrt, std::uint64_t a, std::uint64_t b) {
      return fp_divsqrt_special(sqrt, width, box(a), UINT64_MAX, box(b), UINT64_MAX);
    };
    check(!special(false, one, one), "normal divide must retain its old price");
    check(!special(false, 1, one) && !special(false, one, 1), "subnormals are normal HardFloat inputs");
    check(!special(false, sign | one, one), "negative finite divide is normal");
    for (auto word : {UINT64_C(0), sign, infinity, sign | infinity, infinity | 1}) {
      check(special(false, word, one) && special(false, one, word), "zero/Inf/NaN operand is special");
      check(special(true, word, one), "special sqrt input must be classified");
    }
    check(!special(true, one, infinity), "sqrt must ignore rs2 data");
    check(special(true, sign | one, one), "negative finite sqrt is special");
    check(!special(true, 1, one), "positive subnormal sqrt remains normal");
    check(fp_divsqrt_special(false, width, box(one), 0, box(one), UINT64_MAX),
          "invalid outer NaN box must become a special canonical NaN");
  }
  check(spike_timing::fp_operand_ieee(32, 0, UINT64_MAX) == 0x7fc00000,
        "invalid S-in-D NaN box must not look like zero");
  bool refused = false;
  try { spike_timing::fp_operand_ieee(16, 0, 0); } catch (const std::invalid_argument &) { refused = true; }
  check(refused, "unsupported floating format must refuse");
  std::cout << "source-bound FP operand classification passed\n";
}
