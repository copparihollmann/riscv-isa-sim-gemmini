#ifndef SPIKE_TIMING_FP_OPERAND_TIMING_HPP
#define SPIKE_TIMING_FP_OPERAND_TIMING_HPP

#include <cstdint>
#include <stdexcept>

namespace spike_timing {
// IEEE inputs to the selected HardFloat DivSqrtRecFN_small normalCase test.
// Spike's internal FPRs are 128-bit NaN-boxed; invalid boxes are canonical NaNs.
inline std::uint64_t fp_operand_ieee(unsigned width, std::uint64_t low, std::uint64_t high) {
  if (width == 32)
    return high == UINT64_MAX && (low >> 32) == UINT32_MAX ?
        std::uint32_t(low) : UINT32_C(0x7fc00000);
  if (width == 64) return high == UINT64_MAX ? low : UINT64_C(0x7ff8000000000000);
  throw std::invalid_argument("operand-dependent FP timing requires scalar S/D inputs");
}

inline bool fp_divsqrt_special(bool sqrt, unsigned width,
                               std::uint64_t a_low, std::uint64_t a_high,
                               std::uint64_t b_low, std::uint64_t b_high) {
  const auto a = fp_operand_ieee(width, a_low, a_high);
  const auto b = fp_operand_ieee(width, b_low, b_high);
  const auto sign = width == 32 ? UINT64_C(0x80000000) : UINT64_C(0x8000000000000000);
  const auto exponent = width == 32 ? UINT64_C(0x7f800000) : UINT64_C(0x7ff0000000000000);
  const auto special = [&](std::uint64_t word) {
    return (word & ~sign) == 0 || (word & exponent) == exponent;
  };
  return special(a) || (sqrt ? (a & sign) != 0 : special(b));
}
}  // namespace spike_timing
#endif
