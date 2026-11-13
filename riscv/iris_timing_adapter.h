#pragma once

#include "mmu.h"
#include "../../../timing/iris_timing.hpp"
#include "../../../timing/scalar_memory.hpp"
#include <functional>
#include <memory>
#include <optional>
#include <random>
#include <string>
#include <vector>

// This adapter is an explicitly uncalibrated integration mode. It establishes
// causal execution/counter/device hooks; it is not an Iris performance profile.
class iris_timing_adapter {
 public:
  using Cycle = iris::Cycle;
  struct Rule {
    unsigned hart; uint32_t mask, match; std::string resource;
    Cycle latency, interval; std::string name;
  };
  struct Hart { Cycle divider = 0; bool count_wfi = true; };
  struct Profile {
    uint64_t base_hz = 0, rtc_divider = 0, max_cycles = 0, trap_cycles = 0;
    std::string source;
    std::vector<Hart> harts;
    std::vector<std::pair<std::string, unsigned>> resources;
    std::vector<Rule> rules;
    std::vector<iris::MemoryPort> memory_ports;
    std::vector<iris::AddressRoute> memory_regions;
    std::map<std::string,std::vector<iris::RoutedStage>> memory_stages;
    static Profile load(const std::string& path, size_t harts);
  };
  iris_timing_adapter(Profile profile, std::vector<processor_t*> cores,
      std::function<void(Cycle, Cycle)> advance,
      std::function<std::optional<Cycle>()> timer_deadline,
      std::function<bool()> host_request,
      std::optional<uint64_t> schedule_seed);
  void step(size_t completions);
  void issue(unsigned hart, reg_t pc, const insn_fetch_t& fetch);
  void retired(unsigned hart, size_t count);
  const insn_fetch_t* completion_fetch(unsigned hart) const;
  Cycle now() const { return clock_.now(); }
  const Profile& profile() const { return profile_; }
  void write_json(const std::string& path) const;
 private:
  struct Pending { reg_t pc; insn_fetch_t fetch; };
  Profile profile_;
  std::vector<processor_t*> cores_;
  iris::Machine clock_;
  std::unique_ptr<iris::MemoryPaths> memory_paths_;
  std::unique_ptr<iris::ScalarMemoryRoutes> memory_routes_;
  struct RoutedAccess { unsigned hart; iris::AccessKind kind; iris::MemoryTransfer transfer; };
  std::vector<RoutedAccess> memory_transfers_;
  std::vector<std::optional<Pending>> pending_;
  std::vector<std::optional<iris::NodeId>> previous_;
  std::vector<bool> blocked_;
  std::optional<unsigned> completing_;
  std::function<std::optional<Cycle>()> timer_deadline_;
  std::function<bool()> host_request_;
  uint64_t completions_ = 0;
  bool yielded_without_event_ = false;
  std::vector<uint64_t> retired_;
  std::vector<unsigned> order_;
  std::optional<uint64_t> seed_;
  std::mt19937_64 rng_;
  void dispatch_ready();
  void queue_trap(unsigned hart);
};
