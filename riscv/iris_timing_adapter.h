#pragma once

#include "mmu.h"
#include "../../../timing/iris_timing.hpp"
#include "../../../timing/scalar_memory.hpp"
#include "../../../timing/shuttle_issue.hpp"
#include <array>
#include <deque>
#include <exception>
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
    bool shuttle_pure_pipeline = false;
    bool shuttle_rvc_pipeline = false;
    bool shuttle_counter_pipeline = false;
    bool rocket_pure_pipeline = false;
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
  void counter_read(unsigned hart, reg_t pc, uint32_t raw, unsigned csr, reg_t value, unsigned destination, const char* phase);
  const insn_fetch_t* completion_fetch(unsigned hart) const;
  std::exception_ptr completion_exception(unsigned hart) const;
  Cycle now() const { return clock_.now(); }
  const Profile& profile() const { return profile_; }
  void write_json(const std::string& path) const;
 private:
  struct Pending { reg_t pc; insn_fetch_t fetch; std::optional<iris::NodeId> completion_node; };
  struct CounterRead {
    uint64_t sequence=0;
    iris::NodeId node=0;
    unsigned hart=0,csr=0,destination=0;
    reg_t pc=0,value=0;
    uint32_t raw=0;
    Cycle read_cycle=0;
    std::string phase;
  };
  std::optional<iris::NodeId> completing_node_;
  std::vector<CounterRead> completion_reads_, counter_reads_;
  std::vector<uint64_t> counter_sequences_;
  void finish_counter_reads(unsigned hart,uint64_t before);
  void write_counter_reads(std::ostream&) const;
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
  struct PureInstruction {
    reg_t pc;
    insn_fetch_t fetch;
    iris::shuttle::Uop uop;
    iris::shuttle::ResultStage result_stage = iris::shuttle::ResultStage::none;
    uint64_t packet = 0;
    unsigned lane = 0;
    Cycle rrd = 0;
    Cycle ex_release = 0, com_cycle = 0;
    bool counter = false;
    std::optional<iris::NodeId> csr_ex;
    std::optional<iris::NodeId> mem;
    std::optional<iris::NodeId> result, com, wb;
    std::vector<size_t> raw_producers;
    bool retired = false, released = false;
    std::exception_ptr exception;
  };
  struct PurePacket { uint64_t id; unsigned remaining; };
  struct PureHart {
    bool engaged = false, boundary = false;
    reg_t frontier = 0;
    std::optional<Cycle> last_attempt;
    uint64_t next_packet = 0;
    size_t next_commit = 0, first_live = 0, peak_packets = 0;
    std::deque<PurePacket> packets;
    std::deque<PureInstruction> instructions;
    std::array<std::optional<size_t>,32> last_writer{};
    std::exception_ptr deferred_fetch;
  };
  std::vector<PureHart> pure_;
  std::optional<size_t> completing_pure_;
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
  bool pure_candidate(unsigned hart, const insn_fetch_t& fetch) const;
  bool pure_begin(unsigned hart, reg_t pc, const insn_fetch_t& fetch);
  void pure_dispatch(unsigned hart, const insn_fetch_t* first = nullptr);
  iris::shuttle::IssueSignals pure_signals(unsigned hart) const;
  void pure_accept(unsigned hart, const std::vector<std::pair<reg_t,insn_fetch_t>>& fetched,
                   const iris::shuttle::PacketPlan& plan);
  void pure_exception(unsigned hart, std::exception_ptr exception);
  void pure_commit(unsigned hart, size_t instruction);
  void write_pure_json(std::ostream& out) const;
  void rocket_dispatch(unsigned hart,const insn_fetch_t* first=nullptr);
  void rocket_accept(unsigned hart,reg_t pc,const insn_fetch_t& fetch);
  void write_rocket_json(std::ostream& out) const;
};
