// Iris OPU source contract: OFP8 widening followed by sequential FP32 FMA.
// Saturn536774bd4c5e3bcd7813a4a0dc72fc87e5818532:
// exu/fp/fp8ToE5M3.scala8-29; exu/OuterProductUnit.scala84-110.
#ifndef IRIS_FP8_HPP
#define IRIS_FP8_HPP
#include <cstdint>
#include "softfloat.h"

static inline uint32_t iris_fp8_to_f32(uint8_t input, bool e5m2)
{
  const uint32_t sign = uint32_t(input & 128) << 24;
  const unsigned fraction_bits = e5m2 ? 2 : 3;
  const unsigned exponent = (input & 127) >> fraction_bits;
  const unsigned fraction = input & ((1u << fraction_bits) - 1);
  if (e5m2 && exponent == 31)
    return fraction ? 0x7fc00000 : sign | 0x7f800000;
  if (!e5m2 && exponent == 15 && fraction == 7) return 0x7fc00000;
  if (!exponent) {
    if (!fraction) return sign;
    unsigned leading = 0;
    while ((1u << (leading + 1)) <= fraction) ++leading;
    const int unbiased = (e5m2 ? -16 : -9) + int(leading);
    return sign | (uint32_t(unbiased + 127) << 23) |
      ((fraction - (1u << leading)) << (23 - leading));
  }
  return sign | ((exponent + (e5m2 ? 112 : 120)) << 23) |
    (fraction << (23 - fraction_bits));
}

// OPU FMA exception outputs are unwired; preserve all guest and library flags.
struct IrisSoftfloatScope {
  uint_fast8_t mode = softfloat_roundingMode;
  uint_fast8_t flags = softfloat_exceptionFlags;
  uint_fast8_t tininess = softfloat_detectTininess;
  explicit IrisSoftfloatScope(unsigned rounding) {
    softfloat_roundingMode = rounding;
    softfloat_exceptionFlags = 0;
    softfloat_detectTininess = softfloat_tininess_afterRounding;
  }
  ~IrisSoftfloatScope() {
    softfloat_roundingMode = mode;
    softfloat_exceptionFlags = flags;
    softfloat_detectTininess = tininess;
  }
};
#endif
