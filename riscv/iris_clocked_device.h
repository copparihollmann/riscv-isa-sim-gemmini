#pragma once
#include <cstdint>
#include <optional>
extern "C" uint64_t iris_device_clock_abi_v3();

// Optional independent interface: ordinary Spike devices retain their ABI.
// Times are absolute ticks of the selected modeled base clock, never host time.
class iris_clocked_device_t {
 public:
  virtual ~iris_clocked_device_t() = default;
  virtual void iris_advance_model_clock(uint64_t before, uint64_t after,
                                      uint64_t base_hz) = 0;
  virtual std::optional<uint64_t> iris_next_model_event(uint64_t now,
                                                       uint64_t base_hz) const = 0;
};
