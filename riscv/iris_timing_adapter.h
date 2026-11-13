#pragma once

#include "mmu.h"
#include "iris_forwarded_values.h"
#include "../../../pipeline/rocket_fabric_peer.hpp"
#include "../../../pipeline/rocket_serial_peer.hpp"
#include "../../../pipeline/axi_functional_fixture.hpp"
#include "../../../pipeline/cbus_functional_fixture.hpp"
#include "../../../pipeline/rocket_fabric_fixture.hpp"
#include "../../../pipeline/fabric_backing.hpp"
#include "../../../pipeline/serial_backing.hpp"
#include "../../../pipeline/frontend_rtl_peer.hpp"
#include "../../../pipeline/rocket_frontend_rtl_peer.hpp"
#include "../../../pipeline/rocket_branch.hpp"
#include "../../../pipeline/source_counter_clock.hpp"
#include "../../../pipeline/frontend_branch.hpp"
#include "../../../pipeline/fabric_engine.hpp"
#include "../../../pipeline/fabric_scalar_memory.hpp"
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
  struct Hart { Cycle divider = 0; bool count_wfi = true; bool source_counter_idle=false; };
  struct Profile {
    uint64_t base_hz = 0, rtc_divider = 0, max_cycles = 0, trap_cycles = 0;
    std::string source;
    bool shuttle_pure_pipeline = false;
    bool shuttle_rvc_pipeline = false;
    bool shuttle_counter_pipeline = false;
    bool rocket_pure_pipeline = false;
    bool private_forwarded_values = false;
    bool saved_shuttle_frontend = false;
    bool saved_rocket_frontend = false;
    bool rocket_serial=false;unsigned serial_reset_phases=0;iris::fased::Parameters serial_latency{0,0,0,0};std::string serial_system_identity,serial_latency_identity;
    bool rocket_memory_fabric=false,rocket_scalar_memory=false;Cycle fabric_uncore_divider=0,fabric_first_edges=0,fabric_gap_edges=0;
    std::string fabric_initial_elf,fabric_service_source;
    bool source_counter_clock = false;
    uint64_t frontend_seed=0;unsigned frontend_reset_edges=0;
    Cycle synthetic_icache_first=0,synthetic_icache_gap=0;
    std::string icache_service_source;
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
  bool source_counter_pre_edge(unsigned hart,Cycle cycle);
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
    bool rocket_replay=false;
    bool memory_load_use=false;
    bool source_memory=false,memory_store=false,memory_address_ready=false,memory_accepted=false,memory_killed=false,memory_replay=false,memory_pending=false;
    uint64_t memory_address=0,memory_data=0;unsigned memory_size=0;
    std::optional<iris::NodeId> memory_actor;
    std::optional<iris::frontend::ForwardedValues::Operands> memory_operands;
    std::optional<iris::frontend::SavedRocketFrontend::Uop> rocket_frontend;
    bool squashed=false,sfb_shadow=false;
    std::optional<iris::frontend::SavedShuttleFrontend::Uop> frontend;
    std::optional<iris::frontend::ForwardedValues::Operands> branch_operands;
    bool branch_taken=false;uint64_t branch_wdata=0;
    bool branch_resolved=false,branch_mispredict=false,branch_redirect=false,branch_sfb_pair=false;
    std::optional<iris::NodeId> branch_mem;
    bool private_value_ready = false;
    std::optional<uint64_t> private_value;
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
    std::optional<iris::frontend::ForwardedValues> values;
  };
  std::vector<PureHart> pure_;
  std::vector<iris::frontend::SourceCounterClock> source_counter_clocks_;
  struct CounterClockTransition {unsigned hart;Cycle cycle;bool before,after;std::string reason;};
  std::vector<CounterClockTransition> counter_clock_transitions_;
  void source_counter_finish(unsigned hart,bool retired);
  void write_source_counter_json(std::ostream&) const;
  using FrontendPeer=iris::frontend::SavedShuttleFrontend;
  struct FrontendRefill {uint64_t address;Cycle accepted;std::vector<iris::NodeId> beats;unsigned returned=0;};
  struct FrontendHart {
    std::unique_ptr<FrontendPeer> model;FrontendPeer::Inputs inputs;FrontendPeer::Outputs outputs;
    Cycle next_edge=0;bool prepared=false;uint64_t edges=0,consumed=0,redirects=0,empty_edges=0;
    std::optional<size_t> active_refill;std::vector<FrontendRefill> refills;
    std::optional<FrontendPeer::Uop> conservative;
  };
  std::array<FrontendHart,2> frontend_;
  using RocketFrontendPeer=iris::frontend::SavedRocketFrontend;
  struct RocketFrontendHart {
    std::unique_ptr<iris::frontend::RocketFabricPeer> fabric;
    std::unique_ptr<iris::frontend::RocketSerialPeer> serial;
    std::unique_ptr<iris::frontend::AxiFunctionalFixture> axi_fixture;
    std::unique_ptr<iris::frontend::SerialBacking> serial_backing;
    std::unique_ptr<iris::frontend::CbusFunctionalFixture> cbus_fixture;
    std::vector<iris::fased::Bits> latency_inputs;
    iris::frontend::RocketSerialPeer::Outputs serial_outputs;
    Cycle next_bringup_edge=0,next_serial_edge=0;uint64_t bringup_edges=0,serial_edges=0,axi_reads=0,axi_writes=0;
    std::deque<iris::NodeId> axi_read_nodes,axi_write_nodes;
    std::unique_ptr<iris::frontend::RocketFabricFixture> fabric_fixture;
    std::unique_ptr<iris::frontend::FabricBacking> fabric_backing;
    std::vector<iris::fabric::Input> arbiter_inputs,fabric_inputs;
    iris::frontend::RocketFabricPeer::Outputs fabric_outputs;
    Cycle next_uncore_edge=0;uint64_t uncore_edges=0;bool fabric_prepared=false;
    std::optional<iris::NodeId> source_refill;unsigned source_refill_beats=0;
    std::vector<iris::NodeId> service_nodes;
    std::vector<size_t> pending_wb,pending_ex;
    std::array<std::optional<size_t>,32> pending_loads{};
    std::optional<size_t> physical_ex,physical_mem;
    bool cache_blocked=false,cache_grant=false;
    uint64_t memory_replays=0,early_load_retirements=0,late_rf_writes=0;
    std::unique_ptr<RocketFrontendPeer> model;RocketFrontendPeer::Inputs inputs;RocketFrontendPeer::Outputs outputs;
    Cycle next_edge=0;bool prepared=false;uint64_t edges=0,consumed=0,redirects=0,replays=0;
    std::optional<size_t> active_refill;std::vector<FrontendRefill> refills;
    std::optional<RocketFrontendPeer::Uop> conservative;
    bool might_request=true,next_progress=false;
    std::optional<Cycle> last_architectural_wb;
    std::vector<size_t> pending_mem;
  } rocket_frontend_;
  bool rocket_frontend_enabled() const {return profile_.saved_rocket_frontend;}
  void rocket_frontend_initialize();
  void rocket_fabric_initialize();
  void rocket_fabric_prepare();
  void rocket_fabric_evaluate();
  void rocket_fabric_commit();
  void rocket_serial_initialize();
  void rocket_serial_prepare();
  void rocket_serial_evaluate();
  void rocket_serial_commit();
  void write_rocket_serial_json(std::ostream&) const;
  void rocket_memory_prepare();
  void rocket_memory_after_prepare();
  void rocket_memory_revise_kills();
  void rocket_memory_commit_physical();
  void rocket_memory_replay_wb(size_t);
  void rocket_memory_complete_ex(size_t);
  void rocket_memory_retire_effect(processor_t*,reg_t,insn_t);
  static reg_t rocket_memory_handler(processor_t*,insn_t,reg_t);
  bool rocket_memory_decode(const iris::shuttle::Uop&) const;
  void write_rocket_fabric_json(std::ostream&) const;
  void rocket_frontend_prepare();
  void rocket_frontend_commit_edge();
  void rocket_frontend_consume();
  void rocket_frontend_redirect(reg_t,bool=false);
  void rocket_frontend_boundary_complete(reg_t,const insn_fetch_t&);
  void rocket_frontend_refill(uint64_t);
  void rocket_frontend_resolve_mem();
  void rocket_frontend_replay_accept();
  void rocket_frontend_replay_complete(size_t);
  std::optional<iris::shuttle::Uop> rocket_frontend_decode(const insn_fetch_t&) const;
  void write_rocket_frontend_json(std::ostream&) const;
  std::vector<iris::NodeId> squash_after_completion_;
  bool frontend_enabled(unsigned h) const {return profile_.saved_shuttle_frontend && h<2;}
  void frontend_initialize();
  void frontend_prepare();
  void frontend_commit_edges();
  void frontend_consume(unsigned,unsigned);
  void frontend_redirect(unsigned,reg_t,unsigned=0);
  void frontend_boundary_complete(unsigned,reg_t,const insn_fetch_t&);
  void frontend_refill(unsigned,uint64_t);
  void frontend_flush_annotations();
  void frontend_branch_resolve(unsigned,size_t);
  void frontend_squash(unsigned,size_t,bool);
  std::optional<iris::shuttle::Uop> frontend_decode(unsigned,const insn_fetch_t&,unsigned=0) const;
  void write_frontend_json(std::ostream&) const;
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
