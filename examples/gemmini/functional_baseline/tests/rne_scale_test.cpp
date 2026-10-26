// Compile against the prepared public receiver header, not a copied oracle.
#include <cassert>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <limits>
#include "gemmini_params.h"

static int expected(float product) {
  const float rounded = std::nearbyintf(product);
  return rounded > INT8_MAX ? INT8_MAX : rounded < INT8_MIN ? INT8_MIN : static_cast<int>(rounded);
}

int main() {
  static_assert(std::numeric_limits<float>::is_iec559 && sizeof(float) == 4 &&
                std::numeric_limits<float>::digits == 24);
  assert(std::fegetround() == FE_TONEAREST);
  const float below_one = std::nextafterf(1.0f, 0.0f);
  assert(2.0f * below_one == std::nextafterf(2.0f, 0.0f));
#ifdef REPRODUCE_UPSTREAM_BUG
  assert(ACC_SCALE(2, below_one) == 3);
  assert(ACC_SCALE(-2, below_one) == -3);
  return 0;
#else
  assert(ACC_SCALE(2, below_one) == 2);
  assert(ACC_SCALE(-2, below_one) == -2);
  for (float value : {0.5f, 1.5f, 2.5f, 3.5f, -0.5f, -1.5f, -2.5f, -3.5f,
                     std::nextafterf(2.0f, 0.0f), std::nextafterf(-2.0f, 0.0f),
                     std::nextafterf(2.5f, 3.0f), std::nextafterf(-2.5f, -3.0f)})
    assert(ROUND_NEAR_EVEN(value) == std::nearbyintf(value));
  const float scales[] = {below_one, std::nextafterf(1.0f, 2.0f), 0.0f, 0.25f, 0.5f,
                          0.75f, 1.0f, 1.5f, -0.5f, -below_one, 1e-20f};
  const acc_t values[] = {INT32_MIN, -16777217, -256, -129, -128, -127, -17, -4, -3,
                          -2, -1, 0, 1, 2, 3, 4, 17, 127, 128, 129, 256, 16777217, INT32_MAX};
  for (auto value : values)
    for (auto scale : scales) {
      // The FP32 product is stored separately; the independent C library
      // operation tests integer rounding, including ties, before saturation.
      volatile float product = static_cast<float>(value) * scale;
      assert(ACC_SCALE(value, scale) == expected(product));
    }
  for (int value = INT8_MIN; value <= INT8_MAX; ++value)
    for (auto scale : scales) {
      volatile float product = static_cast<float>(value) * scale;
      assert(MVIN_SCALE(static_cast<elem_t>(value), scale) == expected(product));
    }
  assert(ACC_SCALE(255, 0.5f) == 127);
  assert(ACC_SCALE(-257, 0.5f) == -128);
#endif
}
