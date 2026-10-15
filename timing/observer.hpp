#ifndef SPIKE_TIMING_OBSERVER_HPP
#define SPIKE_TIMING_OBSERVER_HPP
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include <functional>
#include "memtracer.h"
class processor_t;
namespace spike_timing {
bool enabled() noexcept;
void before(processor_t *, std::uint64_t pc, std::uint64_t bits);
void after(std::uint64_t next_pc, bool committed);
void aborted() noexcept;

class Session : public memtracer_t {
public:
  Session(const std::string &model, const std::string &report,
          const std::string &elf, const std::string &input_digest,
          const std::vector<std::string> &libraries,
          std::function<unsigned(std::uint64_t, std::size_t)> memory_kind);
  ~Session();
  bool interested_in_range(std::uint64_t, std::uint64_t, access_type type) override;
  void trace(std::uint64_t address, std::size_t bytes, access_type type) override;
  void clean_invalidate(std::uint64_t, std::size_t, bool, bool) override;
  void finish(int exit_code, bool completed = true);
private:
  class Impl;
  std::unique_ptr<Impl> impl_;
  friend void before(processor_t *, std::uint64_t, std::uint64_t);
  friend void after(std::uint64_t, bool);
  friend void aborted() noexcept;
};
} // namespace spike_timing
#endif
