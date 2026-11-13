#pragma once
#include "../../../timing/overlap_completion_entry_schedule.hpp"
#include "../../../timing/overlap_completion_command_queues_tk.hpp"

#include "mmu.h"
#include "iris_saturn_live.h"
#include "iris_forwarded_values.h"
#include "../../../pipeline/rocket_fabric_peer.hpp"
#include "../../../pipeline/rocket_serial_peer.hpp"
#include "../../../pipeline/axi_functional_fixture.hpp"
#include "../../../pipeline/cbus_functional_fixture.hpp"
#include "../../../pipeline/rocket_fabric_fixture.hpp"
#include "../../../pipeline/fabric_backing.hpp"
#include "../../../pipeline/serial_backing.hpp"
#include "../../../pipeline/frontend_rtl_peer.hpp"
#include "../../../pipeline/fast_source_frontend.hpp"
#include "../../../pipeline/fast_rocket_packets.hpp"
#include "../../../pipeline/rocket_frontend_rtl_peer.hpp"
#include "../../../pipeline/rocket_branch.hpp"
#include "../../../pipeline/empirical_counter_clock.hpp"
#include "../../../pipeline/frontend_branch.hpp"
#include "../../../pipeline/store_front_completion_runtime/empirical_engine.hpp"
#include "../../../pipeline/store_front_completion_runtime/empirical_scalar_memory.hpp"
#include "../../../timing/empirical_cache_v9.hpp"
#include "../../../pipeline/scalar_l2_hit_service.hpp"
#include "../../../pipeline/scalar_outer_response_service_v2.hpp"
#include "../../../timing/shuttle_issue.hpp"
#include <array>
#include <deque>
#include <exception>
#include <functional>
#include <fstream>
#include <memory>
#include <optional>
#include <random>
#include <string>
#include <vector>

// This adapter is an explicitly uncalibrated integration mode. It establishes
// causal execution/counter/device hooks; it is not an Iris performance profile.
class iris_clocked_device_t;
class iris_timing_adapter {
 public:
  using Cycle = iris::Cycle;
  struct Rule {
    unsigned hart; uint32_t mask, match; std::string resource;
    Cycle latency, interval; std::string name;
  };
  struct EmpiricalRule {unsigned hart;std::string family,resource,status,source;double setup=0,work=0;Cycle interval=1;};
  struct Feature {std::string family="scalar.other";uint64_t work=0,bytes=0,macs=0,dlen_beats=0,atl_beats=0;iris::ScalarAccess memory{};};
  struct FeatureTotal {uint64_t instructions=0,work=0,bytes=0,macs=0,dlen_beats=0,atl_beats=0;};
  using FeatureTotals=std::map<std::string,FeatureTotal>;
  struct EmpiricalCacheRule{unsigned hart;double read,write,l1,outer,outer_interval,dirty;std::string status,source;};
  struct EmpiricalScalarL2HitRule{unsigned hart;double coefficient;std::string status,source;};
  struct EmpiricalInstructionRule{unsigned hart;double l1,outer,interval;std::string status,source;};
  struct EmpiricalBranchRule{unsigned hart;double penalty;std::string status,source;};
  struct Hart { Cycle divider = 0; bool count_wfi = true; bool source_counter_idle=false; };
  struct Profile {
    uint64_t base_hz = 0, rtc_divider = 0, max_cycles = 0, trap_cycles = 0;
    std::string source;
    // Non-owning registration-order view; sim devices retains ownership.
    std::vector<iris_clocked_device_t*> clocked_devices;
    bool shuttle_pure_pipeline = false;
    bool shuttle_rvc_pipeline = false;
    bool shuttle_counter_pipeline = false;
    bool rocket_pure_pipeline = false;
    bool private_forwarded_values = false;
    bool saved_shuttle_frontend = false;
    bool saved_rocket_frontend = false;
    bool keep_history=true,empirical=false,empirical_async=false,empirical_async_two_owner=false,empirical_async_fadd=false,empirical_icache=false,empirical_load_front=false,empirical_shuttle_load_com_forward=false,empirical_rocket_packets=false,empirical_vme_shape_work=false,empirical_store_front=false,empirical_read_overlap=false,empirical_shuttle_random=false,empirical_opu_entry=false,empirical_opu_tk124=false,empirical_opu_fence=false;std::string empirical_identity;
    bool empirical_scalar_fadd=false;
    bool saturn_live=false;std::string saturn_manifest;
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
    std::vector<EmpiricalRule> empirical_rules;std::vector<EmpiricalCacheRule> empirical_cache_rules;std::vector<EmpiricalScalarL2HitRule>empirical_scalar_l2_hit_rules,empirical_scalar_outer_rules;std::vector<EmpiricalInstructionRule> empirical_instruction_rules;std::vector<EmpiricalBranchRule> empirical_branch_rules;
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
  void register_clocked_device(iris_clocked_device_t* device) { profile_.clocked_devices.push_back(device); }
  bool source_counter_pre_edge(unsigned hart,Cycle cycle);
  std::pair<uint64_t,uint64_t> source_counter_span(unsigned hart,Cycle cycle);
  void write_json(const std::string& path) const;
 private:
  struct Pending { reg_t pc; insn_fetch_t fetch; std::optional<iris::NodeId> completion_node;Feature feature;std::optional<uint64_t> cache_owner; };
  struct EmpiricalFetchObservation{uint64_t owner,node,address,bytes,l1_misses,l2_misses,submitted,start,end;bool issued;};
  struct CounterRead {
    std::optional<EmpiricalFetchObservation> pending_fetch;
    uint64_t sequence=0;
    iris::NodeId node=0;
    unsigned hart=0,csr=0,destination=0;
    reg_t pc=0,value=0;unsigned scalar_fp_accepted=0,scalar_fp_queued=0;Cycle scalar_fp_next_write=0;unsigned async_pending_count=0;bool async_pending=false;uint64_t async_backend_end=0;
    uint32_t raw=0;
    Cycle read_cycle=0;
    std::string phase;
    std::optional<unsigned> source_fetch_sampled_beats;
    bool source_fetch_final_input_present=false;
    Cycle source_fetch_next_edge=0,source_fetch_period=0;
    bool source_fetch_final_graph_completed=false;
    FeatureTotals features;std::map<std::string,std::map<std::string,uint64_t>> memory;std::map<std::string,iris::Machine::Occupancy> occupancy;std::map<std::string,uint64_t> busy;uint64_t retired=0;
  };
  std::optional<iris::NodeId> completing_node_;
  std::vector<CounterRead> completion_reads_, counter_reads_;
  std::vector<uint64_t> counter_sequences_;
  void finish_counter_reads(unsigned hart,uint64_t before);
  void write_counter_reads(std::ostream&) const;
  struct StoreMetrics{uint64_t accepted=0,fast_COM=0,ownership_losses=0,cost_deferrals=0,published=0,IRQ_pending_before_publish=0;};
  std::vector<StoreMetrics>store_metrics_;std::vector<std::optional<size_t>>store_deferred_;
  bool empirical_store_candidate(unsigned,const iris::shuttle::Uop&)const;
  bool empirical_store_wait_base(unsigned,const iris::shuttle::Uop&)const;
  bool empirical_store_before_commit(unsigned,size_t);
  void empirical_store_after_commit(unsigned,size_t,bool);
  void empirical_store_write_totals(std::ostream&)const;
  void empirical_store_observe(unsigned,size_t,const char*)const;
  void empirical_store_boundary_observe(unsigned);
  struct EmpiricalLoadMetrics{uint64_t accepted=0,hit_responses=0,coherence_fallbacks=0,faults=0,partial_transports=0,discarded_responses=0;};std::vector<EmpiricalLoadMetrics>empirical_load_metrics_;
  struct EmpiricalLoadActor{unsigned hart=0;uint64_t cache_owner=0;std::optional<iris::NodeId>response;bool discarded=false,done=false;};
  std::map<iris::NodeId,std::shared_ptr<EmpiricalLoadActor>>empirical_load_responses_;
  bool empirical_load_candidate(unsigned,const iris::shuttle::Uop&)const;
  void empirical_load_response(unsigned,size_t);
  void empirical_load_capture(unsigned,size_t);
  void empirical_load_before_commit(unsigned,size_t);
  void empirical_load_after_commit();
  static reg_t empirical_load_handler(processor_t*,insn_t,reg_t);
  struct EmpiricalAsync{
   size_t instruction=0;Cycle com_cycle=0;std::optional<iris::NodeId>backend;Feature feature;bool done=false,retired=false,stages_fp=false,opu_entry=false,opu_queued=false;unsigned opu_remaining=0;Cycle opu_available=0;uint64_t opu_pc=0;iris::opu_entry::CommandTK opu_command{};
   reg_t before_fflags=0,after_fflags=0,before_fflags_known=0,after_fflags_known=0,before_fs=0,after_fs=0;
   std::vector<uint8_t>before_vrf,after_vrf,before_initialized,after_initialized;
   std::vector<char>before_mrf,after_mrf,opu_input_mrf;
   iris_definedness::Bytes opu_input_known;
   std::vector<size_t>opu_offsets;
   iris_definedness::Bytes before_vrf_known,after_vrf_known,before_mrf_known,after_mrf_known;
  };
  std::vector<std::shared_ptr<EmpiricalAsync>>empirical_async_,empirical_async_next_;std::vector<uint64_t>empirical_async_handoffs_;
  bool empirical_async_can_dispatch(unsigned,const insn_fetch_t* = nullptr)const;
  std::vector<std::vector<std::shared_ptr<EmpiricalAsync>>> opu_pending_;
  std::vector<iris::opu_entry::CommandQueuesTK> opu_queues_;
  std::vector<bool> opu_clock_active_;
  std::vector<uint64_t> opu_queue_peak_,opu_full_edges_,opu_front_stalls_;
  std::vector<uint64_t> opu_accepted_,opu_writes_,opu_final_writes_,opu_peak_;
  std::vector<bool>opu_fence_prebusy_;
  std::vector<std::optional<Cycle>>opu_fence_retry_;
  std::vector<uint64_t>opu_fence_admissions_;
  bool opu_fence_eligible(unsigned,const insn_fetch_t&);
  void opu_fence_observe(unsigned,const iris::opu_entry::QueueEdgeTK&);
  void opu_fence_write_totals(std::ostream&)const;
  bool opu_is_mm(const insn_fetch_t*)const;
  std::shared_ptr<EmpiricalAsync> opu_find(unsigned,size_t)const;
  bool opu_can_dispatch(unsigned)const;
  void opu_start_clock(unsigned);
  void opu_tick(unsigned);
  void opu_begin(unsigned,size_t);
  void opu_before(unsigned,const std::shared_ptr<EmpiricalAsync>&);
  void opu_after(unsigned,const std::shared_ptr<EmpiricalAsync>&,bool);
  void opu_cancel(unsigned,const std::shared_ptr<EmpiricalAsync>&);
  void opu_check_irq()const;
  void opu_write(unsigned,const std::shared_ptr<EmpiricalAsync>&,const std::vector<size_t>&,bool,unsigned);
  void opu_write_totals(std::ostream&)const;
  void empirical_async_begin(unsigned,size_t);
  void empirical_async_before(unsigned,size_t);
  void empirical_async_after(unsigned,size_t,bool);
  void empirical_async_publish(unsigned,const std::shared_ptr<EmpiricalAsync>&);
  void empirical_async_cancel(unsigned,size_t);
  struct EmpiricalBranchState{std::array<uint8_t,1024>counters;std::array<bool,256>valid{};std::array<uint64_t,256>tags{},targets{};uint64_t branches=0,mispredicts=0;EmpiricalBranchState(){counters.fill(1);}};
  std::vector<EmpiricalBranchState>empirical_branches_;
  std::vector<std::optional<iris::NodeId>>empirical_branch_recovery_;
  uint64_t empirical_predict(unsigned,uint64_t,const iris::shuttle::Uop&,unsigned)const;
  uint64_t empirical_predict_legacy(unsigned,uint64_t,const iris::shuttle::Uop&,unsigned)const;
  void empirical_branch_resolve(unsigned,size_t);
  Feature empirical_feature(unsigned hart,const insn_fetch_t&) const;
  void empirical_retired(unsigned hart);
  void empirical_write_prefix(const CounterRead&);
  void empirical_write_totals(std::ostream&)const;
  std::vector<FeatureTotals> features_;
  std::vector<std::map<std::string,uint64_t>> empirical_fallback_counts_;
  std::vector<std::map<std::string,std::map<std::string,uint64_t>>> memory_features_;
  std::unique_ptr<iris::empirical::CacheHistoryV9> empirical_cache_;
  struct EmpiricalFetch{uint64_t address=0,bytes=0,l1_misses=0,l2_misses=0,line=UINT64_MAX,ready_pc=0;unsigned ready_bytes=0;bool response_ready=false;uint64_t generation=0;std::optional<uint64_t>owner;};std::vector<EmpiricalFetch>empirical_fetch_;
  bool empirical_fetch_ready(unsigned,uint64_t,unsigned,const insn_fetch_t* = nullptr);
  bool empirical_fetch_cache_ready(unsigned,uint64_t,unsigned);
  void empirical_fetch_consume(unsigned,uint64_t,unsigned);
  uint64_t next_cache_owner_=1;std::map<uint64_t,iris::NodeId> cache_nodes_;
  void empirical_memory_feature(unsigned,const iris::empirical::Delta&,bool);
  uint64_t empirical_scalar_l2_hit_extra(unsigned,const iris::empirical::Delta&,iris::empirical::L2ServiceActor);
  std::vector<iris::empirical::ScalarL2HitService>empirical_scalar_l2_services_;
  uint64_t empirical_scalar_outer_extra(unsigned,const iris::empirical::Delta&,iris::empirical::L2ServiceActor);
  std::vector<iris::empirical::ScalarOuterResponseService>empirical_scalar_outer_services_;
  std::map<std::string,double> empirical_fraction_;
  std::unique_ptr<std::ofstream> feature_stream_,async_trace_;
  bool empirical_diagnostics_=false;uint64_t empirical_debug_steps_=0,empirical_boundary_retry_ticks_=0;
  std::unique_ptr<iris::frontend::FastRocketPackets> rocket_packets_;
  bool rocket_packet_waiting_=false;
  std::unique_ptr<std::ofstream> rocket_packet_trace_;
  void rocket_packet_initialize();
  bool rocket_packet_ready(reg_t,const insn_fetch_t&);
  void rocket_packet_finish();
  void rocket_packet_redirect(reg_t,const char*,unsigned=1);
  void write_rocket_packet_json(std::ostream&)const;
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
  struct ScalarFaddActor {
    unsigned hart=0,rd=0,rs1=0,rs2=0,width=0,rm=0;size_t instruction=0;reg_t pc=0;
    Cycle ex=0,write=0;bool accepted=false,retired=false,killed=false,done=false;
    std::optional<iris::NodeId> node;
    iris_definedness::Value<freg_t> source1,source2,before,after;
    reg_t flags_before=0,flags_known_before=0,fs_before=0,delta_flags=0,frm=0;
  };
  std::vector<std::vector<std::shared_ptr<ScalarFaddActor>>> scalar_fadd_;
  std::vector<uint64_t> scalar_fadd_accepted_,scalar_fadd_published_,scalar_fadd_killed_,scalar_fadd_peak_,scalar_fadd_irq_deferrals_;
  std::vector<std::optional<Cycle>>scalar_fadd_last_irq_;
  bool scalar_fadd_candidate(unsigned,const iris::shuttle::Uop&)const;
  bool scalar_fadd_pending(unsigned)const;
  bool scalar_fadd_defer_irq(unsigned);
  Cycle scalar_fadd_release(unsigned,const iris::shuttle::Uop&,Cycle)const;
  void scalar_fadd_reserve(unsigned,size_t);
  void scalar_fadd_ex(unsigned,size_t);
  void scalar_fadd_before(unsigned,size_t);
  void scalar_fadd_after(unsigned,size_t,bool);
  void scalar_fadd_cancel(unsigned,size_t);
  void scalar_fadd_write(const std::shared_ptr<ScalarFaddActor>&);
  struct PureInstruction {
    reg_t pc;
    insn_fetch_t fetch;
    iris::shuttle::Uop uop;
    iris::shuttle::ResultStage result_stage = iris::shuttle::ResultStage::none;
    uint64_t packet = 0;
    unsigned lane = 0;
    Cycle rrd = 0;
    Cycle ex_release = 0, com_cycle = 0;
    std::shared_ptr<ScalarFaddActor> scalar_fadd;
    bool empirical_store=false,store_serviced=false;std::optional<uint64_t>store_owner;
    bool counter = false;uint64_t empirical_prediction=0;bool empirical_compute=false;bool empirical_load=false,empirical_load_warm_hit=false;std::shared_ptr<EmpiricalLoadActor>empirical_load_actor;std::optional<iris_definedness::Value<reg_t>>empirical_load_value;std::optional<uint64_t>empirical_load_owner;std::optional<iris::NodeId>empirical_backend;
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
    iris::IndexedHistory<PureInstruction> instructions;
    std::array<std::optional<size_t>,32> last_writer{};
    std::exception_ptr deferred_fetch;
    std::optional<iris::frontend::ForwardedValues> values;
  };
  std::vector<PureHart> pure_;
  std::unique_ptr<iris_saturn_live_state> saturn_;
  void saturn_initialize();
  void saturn_prepare();
  void saturn_commit();
  bool saturn_try_issue(unsigned,reg_t,const insn_fetch_t&);
  void saturn_retire(iris::NodeId);
  void saturn_publish(const iris::saturn::OwnershipEvent&);
  static reg_t saturn_retire_handler(processor_t*,insn_t,reg_t);
  void write_saturn_json(std::ostream&)const;
  std::vector<iris::frontend::SourceCounterClock> source_counter_clocks_;
  struct CounterClockTransition {unsigned hart;Cycle cycle;bool before,after;std::string reason;};
  std::vector<CounterClockTransition> counter_clock_transitions_;
  void source_counter_finish(unsigned hart,bool retired);
  void write_source_counter_json(std::ostream&) const;
  using FrontendPeer=iris::frontend::FastSourceFrontend;
  struct FrontendRefill {uint64_t address;Cycle accepted;std::vector<iris::NodeId> beats;unsigned returned=0;std::optional<uint64_t> cache_owner;uint64_t l2_misses=0;};
  struct FrontendHart {
    std::unique_ptr<FrontendPeer> model;FrontendPeer::Inputs inputs;FrontendPeer::Outputs outputs;
    Cycle next_edge=0;bool prepared=false;uint64_t edges=0,consumed=0,redirects=0,empty_edges=0;
    std::optional<size_t> active_refill;std::vector<FrontendRefill> refills;uint64_t accepted_refills=0,completed_refills=0,memory_replay_redirects=0,resolved_controls=0,mispredicts=0;
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
    std::optional<size_t> active_refill;std::vector<FrontendRefill> refills;uint64_t accepted_refills=0,completed_refills=0,memory_replay_redirects=0,resolved_controls=0,mispredicts=0;
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
  std::vector<iris::NodeId> squash_after_completion_;uint64_t compacted_cpu_squash_annotations_=0;
  bool frontend_enabled(unsigned h) const {return profile_.saved_shuttle_frontend && h<2;}
  void frontend_initialize();
  void frontend_prepare();
  void frontend_commit_edges();
  void frontend_consume(unsigned,unsigned);
  void frontend_redirect(unsigned,reg_t,unsigned=0);
  void frontend_boundary_complete(unsigned,reg_t,const insn_fetch_t&);
  void frontend_refill(unsigned,uint64_t);
  void frontend_flush_annotations();
  void frontend_diagnostic(unsigned,const char*)const;
  void frontend_branch_resolve(unsigned,size_t);
  void frontend_squash(unsigned,size_t,bool,const char*reason_override=nullptr);
  bool frontend_uop_candidate(unsigned,const iris::shuttle::Uop&)const;
  std::optional<iris::shuttle::Uop> pure_decode_for_frontend(const insn_fetch_t&) const;
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
  void compact_histories();
  void dispatch_ready();
  void queue_trap(unsigned hart,std::optional<unsigned> source_ras_head={});
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
