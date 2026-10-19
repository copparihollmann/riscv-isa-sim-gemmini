#ifndef SPIKE_TIMING_COUNTER_TAINT_HPP
#define SPIKE_TIMING_COUNTER_TAINT_HPP

#include <cstddef>
#include <cstdint>
#include <limits>
#include <set>
#include <stdexcept>

namespace spike_timing {

// Only counter-dependent bytes need entries. Ordinary writes erase stale
// labels; aliases and partial loads use actual committed byte addresses.
class CounterMemoryTaint {
public:
  explicit CounterMemoryTaint(std::size_t limit) : limit_(limit) {
    if (!limit) throw std::invalid_argument("counter taint requires a positive byte budget");
  }
  bool read(std::uint64_t address, std::uint64_t bytes) const {
    bounds(address, bytes);
    const auto found = bytes_.lower_bound(address);
    return found != bytes_.end() && *found - address < bytes;
  }
  void write(std::uint64_t address, std::uint64_t bytes, bool tainted) {
    bounds(address, bytes);
    if (!tainted) {
      auto first = bytes_.lower_bound(address), last = first;
      while (last != bytes_.end() && *last - address < bytes) ++last;
      bytes_.erase(first, last);
      return;
    }
    // Check before mutation; no prefix can be mistaken for complete tracking.
    std::size_t existing = 0;
    for (auto it = bytes_.lower_bound(address); it != bytes_.end() && *it - address < bytes; ++it) ++existing;
    if (bytes > limit_ || bytes - existing > limit_ - bytes_.size())
      throw std::length_error("counter-dependent memory byte budget exceeded");
    for (std::uint64_t i = 0; i < bytes; ++i) bytes_.insert(address + i);
  }
  std::size_t size() const { return bytes_.size(); }

private:
  std::size_t limit_;
  std::set<std::uint64_t> bytes_;
  static void bounds(std::uint64_t address, std::uint64_t bytes) {
    if (bytes && bytes - 1 > std::numeric_limits<std::uint64_t>::max() - address)
      throw std::overflow_error("counter-dependent memory interval wraps");
  }
};

} // namespace spike_timing
#endif
