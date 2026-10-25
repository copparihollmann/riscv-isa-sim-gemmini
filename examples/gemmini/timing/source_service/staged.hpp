#ifndef GEMMINI_STAGED_TIMING_V2_HPP
#define GEMMINI_STAGED_TIMING_V2_HPP

#include "provider.hpp"
#include "streamed_readout.hpp"
#include "streamed_packet_readout.hpp"
#include "scratchpad_load.hpp"
#include "packet_load.hpp"
#include <merlin_timing/reservations.hpp>
#include <memory>
#include <set>

namespace gemmini_annotated_spike {

struct StagedConfig {
  std::array<std::size_t, 3> reservations, controller_entries;
  std::array<std::size_t, 2> dma_commands;
  std::array<ResourceId, 3> issue_resources, controller_resources;
  std::optional<Cycle> issue_latency, issue_occupancy;
  bool require_fenced_phases = false;
  bool allow_dependency_ordered_phases = false;
  bool allow_disjoint_scratchpad_banks = false;
  std::uint32_t scratchpad_bank_rows = 0;
  bool conservative_local_store_holds = false;
  // Explicit v3 approximation: retire each WS compute epoch before the next
  // PRELOAD consumes its descriptor. CPU admission and other controllers remain
  // asynchronous. This prices no overlap within the mesh pipeline.
  bool serialized_execute_epochs = false;
  // Explicit v4: untransposed OS epochs include their transposer/flush/readout
  // service in the selected compute price and retain tags until that completion.
  bool serialized_output_stationary_epochs = false;
  // Explicit v5: admit a narrow full-tile WS feed/result lifetime split.
  // PRELOAD and COMPUTE feeds remain separately serialized, never fused.
  bool split_ws_feed_lifetimes = false;
  // Narrow accumulating-WS variant: only SP operand consumption moves early.
  // ACC RMW, result publication, queue retirement and execute epochs stay late.
  bool split_ws_accumulate_operands = false;
  // Explicit bounded-tail operand-only release, never a shorter-than-DIM feed.
  bool bounded_ws_operand_release = false;
  std::optional<Cycle> late_accumulator_write_pipeline;
  bool bounded_ws_descriptor_consumption=false;
  bool ws_preload_operand_ownership=false;
  bool load_configuration_request_lifetime=false;
  bool source_identity_ingress=false;
  bool source_bounded_mul_pre_pairing=false;
  bool source_fenced_single_mul=false;
  // Selected full-WS subset: FIFO pop follows operand consumption. COMPUTE's
  // RS completion can precede its PRELOAD output tag only when the registered
  // completion path is provably idle in the retained conservative schedule.
  bool ws_feed_queue_release = false;
  bool ws_resident_mul_pre_pairing = false;
  std::optional<ReadoutStreamConfig> readout_stream;
  std::optional<ScratchpadLoadConfig> scratchpad_load_stream;
  bool scratchpad_packet_loads=false;
  std::vector<ResourceId> scratchpad_bank_resources;
  std::optional<ResourceId> accumulator_storage_resource;
};

// Exact cross-controller RS completion ancestry, independent of event prices.
// Same-LD/EX arrival order proves issue order only. Same-ST entries, however,
// retain their dependencies until completion in the selected source.
class DependencyPhases {
public:
  using Ids = std::set<std::uint64_t>;
  using Rows = std::set<ValueId>;
  using Independence = std::function<bool(std::size_t, const Rows &, std::size_t, const Rows &)>;
  explicit DependencyPhases(Independence independent = {}) : independent_(std::move(independent)) {}
  bool observe(std::size_t group, const Rows &reads, const Rows &writes,
               bool preload = false, bool compute = false, bool execute_config = false,
               const Rows *physical = nullptr) {
    if (execute_config) {
      for (const auto &entry : nodes_) if (entry.second.group == 1) execute_drain_.insert(entry.first);
      return true;
    }
    if (nodes_.size() >= 4096 || sequence_ == std::numeric_limits<std::uint64_t>::max())
      throw std::overflow_error("completion ancestry budget exceeded");
    Ids dependencies = group == 1 ? execute_drain_ : Ids{};
    for (const auto &entry : nodes_) {
      const auto &old = entry.second;
      if ((old.group != group && (overlap(writes, old.writes) || overlap(writes, old.reads) ||
                                   overlap(reads, old.writes))) || (group == 2 && old.group == 2))
        dependencies.insert(entry.first);
    }
    // PRELOAD feed readiness is not tag retirement. Its DMA ancestors feed
    // compute; compute output later completes the non-garbage destination tag.
    if (compute && last_preload_ && nodes_.count(*last_preload_))
      dependencies.insert(nodes_.at(*last_preload_).parents.begin(), nodes_.at(*last_preload_).parents.end());
    const auto ancestors = closure(dependencies);
    bool ordered = true;
    Rows local = reads; local.insert(writes.begin(), writes.end());
    const auto &selected_physical = physical ? *physical : local;
    for (const auto &entry : nodes_)
      if (entry.second.group != group && !ancestors.count(entry.first) &&
          !(independent_ && independent_(group, selected_physical, entry.second.group, entry.second.physical))) ordered = false;
    const auto identity = ++sequence_;
    nodes_.emplace(identity, Node{group, reads, writes, selected_physical, dependencies});
    if (compute && last_preload_ && nodes_.count(*last_preload_))
      nodes_.at(*last_preload_).parents.insert(identity);
    if (preload) last_preload_ = identity;
    return ordered;
  }
  void fence(bool pending_preload) {
    std::optional<Node> retained;
    if (pending_preload && last_preload_ && nodes_.count(*last_preload_)) retained = nodes_.at(*last_preload_);
    nodes_.clear(); execute_drain_.clear();
    if (retained) { retained->parents.clear(); nodes_.emplace(*last_preload_, std::move(*retained)); }
    else last_preload_.reset();
  }
private:
  struct Node { std::size_t group; Rows reads, writes, physical; Ids parents; };
  std::map<std::uint64_t, Node> nodes_;
  Ids execute_drain_;
  std::uint64_t sequence_ = 0;
  std::optional<std::uint64_t> last_preload_;
  Independence independent_;
  static bool overlap(const Rows &a, const Rows &b) {
    auto left = a.begin(), right = b.begin();
    while (left != a.end() && right != b.end()) {
      if (*left == *right) return true;
      if (*left < *right) ++left; else ++right;
    }
    return false;
  }
  Ids closure(const Ids &roots) const {
    Ids result; std::vector<std::uint64_t> work(roots.begin(), roots.end());
    while (!work.empty()) {
      const auto id = work.back(); work.pop_back();
      if (!result.insert(id).second) continue;
      const auto node = nodes_.find(id);
      if (node != nodes_.end()) work.insert(work.end(), node->second.parents.begin(), node->second.parents.end());
    }
    return result;
  }
};

// Version 2 explicitly distinguishes CPU admission, reservation issue, FIFO
// consumption and final effects. It schedules the actual typed v1-observed row
// and memory effects, not a separate decorative plan. Prices remain external.
class StagedObserver {
public:
  StagedObserver(Engine &engine, StagedConfig config, ValueId execute_configuration,
      std::function<void(const std::string &)> unresolved = {},
      ValueId local_base = 0, std::uint32_t scratchpad_rows = 0, std::uint32_t dim = 0, std::uint32_t accumulator_rows = 0)
      : engine_(engine), config_(config), execute_configuration_(execute_configuration),
        phases_([this](auto group, const auto &rows, auto other, const auto &prior) {
          return independent_banks(group, rows, other, prior);
        }), unresolved_(std::move(unresolved)), local_base_(local_base), scratchpad_rows_(scratchpad_rows), dim_(dim), accumulator_rows_(accumulator_rows) {
    if (config_.serialized_execute_epochs &&
        (!config_.require_fenced_phases || !config_.conservative_local_store_holds))
      throw std::invalid_argument("serialized execute epochs require explicit conservative storage and phase checking");
    if (config_.split_ws_feed_lifetimes && !config_.serialized_output_stationary_epochs)
      throw std::invalid_argument("WS lifetime split requires retained v4 epoch/hazard semantics");
    if (config_.split_ws_accumulate_operands && !config_.split_ws_feed_lifetimes)
      throw std::invalid_argument("accumulating WS operands require retained v5 lifetime semantics");
    if (config_.bounded_ws_operand_release && (!config_.split_ws_feed_lifetimes ||
        !config_.conservative_local_store_holds))
      throw std::invalid_argument("bounded WS operands require retained conservative v5 timing");
    if (config_.late_accumulator_write_pipeline && (!config_.bounded_ws_operand_release ||
        !*config_.late_accumulator_write_pipeline || *config_.late_accumulator_write_pipeline>dim_))
      throw std::invalid_argument("late ACC write phases require selected bounded WS and pipeline facts");
    if(config_.bounded_ws_descriptor_consumption && !config_.late_accumulator_write_pipeline)
      throw std::invalid_argument("bounded WS descriptor lifetime requires retained ACC/output phases");
    if (config_.ws_feed_queue_release && !config_.split_ws_feed_lifetimes)
      throw std::invalid_argument("WS queue release requires full-WS operand lifetime split");
    if (config_.ws_resident_mul_pre_pairing && !config_.ws_feed_queue_release)
      throw std::invalid_argument("WS resident pairing requires explicit feed FIFO lifetimes");
    if (config_.serialized_output_stationary_epochs && !config_.serialized_execute_epochs)
      throw std::invalid_argument("OS epochs require conservative serialized execute epochs");
    if (config_.allow_disjoint_scratchpad_banks && (!config_.scratchpad_bank_rows ||
        !scratchpad_rows_ || scratchpad_rows_ % config_.scratchpad_bank_rows))
      throw std::invalid_argument("selected scratchpad bank geometry is inconsistent");
    if (config_.conservative_local_store_holds && (!config_.scratchpad_bank_rows ||
        std::uint64_t(config_.scratchpad_bank_resources.size()) * config_.scratchpad_bank_rows != scratchpad_rows_ ||
        !config_.accumulator_storage_resource))
      throw std::invalid_argument("conservative local-store resource mapping is incomplete");
    if(config_.scratchpad_load_stream) {
      if(!config_.conservative_local_store_holds || dim_!=16)
        throw std::invalid_argument("scratchpad row loads require selected local resources and DIM16");
      load_stream_=std::make_unique<ScratchpadLoadStream>(*config_.scratchpad_load_stream);
      if(config_.scratchpad_packet_loads)
        packet_load_stream_=std::make_unique<PacketLoadStream>(config_.scratchpad_load_stream->identity_stages,config_.source_identity_ingress);
    }
    for (std::size_t i = 0; i < 3; ++i) {
      reservations_[i] = std::make_unique<merlin_timing::ReservationWindow>(config.reservations[i]);
      controllers_[i] = std::make_unique<merlin_timing::ReservationWindow>(config.controller_entries[i]);
    }
    for (std::size_t i = 0; i < 2; ++i)
      dma_[i] = std::make_unique<merlin_timing::ReservationWindow>(config.dma_commands[i]);
  }

  Result submit(const std::string &kind, const Event &source, std::optional<Cycle> occupancy,
                std::uint32_t funct, std::uint64_t rs1, std::uint64_t rs2,
                const std::optional<TransferPhase> &transfer_phase = {}) {
    if (kind == "fence") {
      pair_feed_.reset();
      // A pending PRELOAD has no following execute command yet. It retains its
      // reservation/descriptor/configuration dependency while other work drains.
      const auto drained = engine_.barrier();
      // The instruction establishes the ordering grammar even when its price
      // is unknown. Timing UNKNOWN must not erase observed fence evidence.
      last_data_group_.reset();
      computed_since_fence_ = false;
      phases_.fence(audit_pending_preload_);
      Event event = source;
      if (drained) event.earliest = std::max(event.earliest, *drained);
      else event.latency.reset();
      return engine_.submit(event);
    }
    // Selected Controller routes these directly before reservation allocation.
    // Their explicit primitive prices still remain separate from CPU issue.
    if (funct == 7 || funct == 126) { pair_feed_.reset(); return submit_observed(source); }
    const bool config = funct == 0;
    const auto subtype = config ? rs1 & 3 : 0;
    if (config && subtype == 0 && !(rs1 & 128)) {
      const bool untransposed = !(rs1 & ((1ull << 8) | (1ull << 9)));
      epoch_ws_configured_ = ((rs1 >> 2) & 1) && untransposed;
      epoch_os_configured_ = !((rs1 >> 2) & 1) && untransposed;
    }
    const std::size_t group = config ? (subtype == 1 ? 0 : subtype >= 2 ? 2 : 1) :
        (funct == 1 || funct == 2 || funct == 14) ? 0 : funct == 3 ? 2 : 1;
    if (config || group != 1 || (funct != 4 && funct != 6)) pair_feed_.reset();
    std::vector<ValueId> extra_reads;
    if (funct == 6) {
      extra_reads.push_back(execute_configuration_);
      if (std::uint32_t(rs1) != 0xffffffffu && scratchpad_rows_) {
        const auto address = std::uint32_t(rs1);
        const auto rows = std::min<std::uint32_t>(rs1 >> 48, dim_);
        if (std::uint64_t(address) + rows > scratchpad_rows_) {
          missing("staged:preload_local_address_outside_selected_store");
          semantic_scope_known_ = false;
        } else for (std::uint32_t row = 0; row < rows; ++row)
          extra_reads.push_back(local_base_ + address + row);
      }
    }
    DependencyPhases::Rows rs_reads, rs_writes;
    const auto local = [&](ValueId value) {
      return value >= local_base_ && value - local_base_ < std::uint64_t(scratchpad_rows_) + accumulator_rows_;
    };
    if (config && subtype == 0) {
      a_stride_ = (rs1 >> 16) & 65535; c_stride_ = (rs2 >> 48) & 65535;
      if (!(rs1 & 128)) a_transpose_ = (rs1 >> 8) & 1;
    }
    const auto range = [&](std::uint64_t packet, std::uint64_t rows, DependencyPhases::Rows &into) {
      const auto address = std::uint32_t(packet);
      if (address == 0xffffffffu) return;
      const bool accumulator = address >> 31;
      const auto offset = address & 0x1fffffffu;
      if (rows > 1048576 || std::uint64_t(offset) + rows > (accumulator ? accumulator_rows_ : scratchpad_rows_)) {
        missing("staged:rs_operand_range_not_admitted"); semantic_scope_known_ = false; return;
      }
      for (std::uint64_t row = 0; row < rows; ++row)
        into.insert(local_base_ + (accumulator ? scratchpad_rows_ : 0) + offset + row);
    };
    if (!config && group == 0) {
      for (std::size_t i = 0; i < source.writes.size; ++i) if (local(source.writes[i])) rs_writes.insert(source.writes[i]);
    } else if (!config && group == 2) {
      for (std::size_t i = 0; i < source.reads.size; ++i) if (local(source.reads[i])) rs_reads.insert(source.reads[i]);
    } else if (funct == 6) {
      range(rs1, (rs1 >> 48) & 31, rs_reads);
      range(rs2, ((rs2 >> 48) & 31) * c_stride_, rs_writes);
    } else if (funct == 4 || funct == 5) {
      range(rs1, ((rs1 >> (a_transpose_ ? 32 : 48)) & 31) * a_stride_, rs_reads);
      range(rs2, (rs2 >> 48) & 31, rs_reads);
    }
    if(config && subtype==1) {
      for(std::size_t i=0;i<source.writes.size;++i)if(!local(source.writes[i]))load_configuration_values_.insert(source.writes[i]);
    }
    DependencyPhases::Rows physical_rows;
    for (const auto rows : {source.reads, source.writes})
      for (std::size_t i = 0; i < rows.size; ++i) if (local(rows[i])) physical_rows.insert(rows[i]);
    if (funct == 6) { // Includes the retained destination tag conservatively.
      physical_rows.insert(rs_reads.begin(), rs_reads.end()); physical_rows.insert(rs_writes.begin(), rs_writes.end());
    }
    // Conservative storage holds already order these effects through the live
    // bounded Engine/resource state below. This mode never consumes the exact
    // historical phase proof: retaining it would grow with total command count
    // despite a bounded hardware working set. Keep the proof unchanged for the
    // strict dependency-only profiles which actually use it for admission.
    const bool dependency_ordered = config_.conservative_local_store_holds ? false :
        config ? (subtype != 0 || phases_.observe(group, {}, {}, false, false, true)) :
        phases_.observe(group, rs_reads, rs_writes, funct == 6, funct == 4 || funct == 5, false, &physical_rows);
    // Audit actual command order independently of priced Engine progress. An
    // unpriced first event must not hide unsupported later commands.
    if (config_.require_fenced_phases && group == 1) {
      if (audit_pending_preload_ && funct != 4 && funct != 5) {
        missing("staged:preload_followed_by_noncompute_not_admitted");
        semantic_scope_known_ = false;
      }
      if (funct == 6) {
        if (computed_since_fence_ && !(config_.serialized_execute_epochs &&
                                      (epoch_ws_configured_ || (config_.serialized_output_stationary_epochs &&
                                                               epoch_os_configured_)) && last_compute_ready_)) {
          missing("staged:compute_preload_overlap_without_completion_fence");
          semantic_scope_known_ = false;
        }
        audit_pending_preload_ = true;
      } else if (funct == 4 || funct == 5) {
        audit_pending_preload_ = false;
        computed_since_fence_ = true;
      }
    }
    if (!config && config_.require_fenced_phases && (config_.allow_dependency_ordered_phases || (last_data_group_ && *last_data_group_ != group))) {
      if (!config_.conservative_local_store_holds && (!config_.allow_dependency_ordered_phases || !dependency_ordered)) {
        missing("staged:cross_controller_phase_without_completion_dependency");
        semantic_scope_known_ = false;
      }
    }
    if (!config) last_data_group_ = group;
    if (!semantic_scope_known_) return unknown(source);
    const auto cpu_frontier = engine_.issue_frontier();
    if (!cpu_frontier) return unknown(source);
    auto ticket = reservations_[group]->allocate(std::max(source.earliest, *cpu_frontier));
    if (!ticket) return unknown(source);
    engine_.advance_issue(ticket->admitted);
    std::set<ValueId> consumed_preload_rows,consumed_preload_state;
    std::optional<Cycle> consumed_preload_ready;
    if (group == 1 && pending_) {
      // Lookahead is the next actual execute command, not the next CPU or DMA
      // command. This is the selected cmd.valid(1) PRELOAD start dependency.
      auto pending = std::move(pending_);
      pending->earliest = std::max(pending->earliest, ticket->admitted);
      if (config_.serialized_output_stationary_epochs && epoch_os_configured_) {
        // OS PRELOAD feeds the following compute's A through the transposer
        // (ExecuteController a_address_place). The actual lookahead command is
        // now available. Conservatively retain all its local input rows during
        // PRELOAD as well, rather than letting input DMA race the transposer.
        for (std::size_t i=0; i<source.reads.size; ++i)
          if (local(source.reads[i])) pending->reads.push_back(source.reads[i]);
      }
      const auto full_packet=[&](std::uint64_t p){return (p>>48)==dim_ && ((p>>32)&65535)==dim_;};
      pending->preload_feed_lifetime = config_.ws_feed_queue_release && epoch_ws_configured_ &&
          funct==4 && a_stride_==1 && c_stride_==1 && full_packet(rs1) && full_packet(rs2) &&
          full_packet(last_preload_source_) && full_packet(last_preload_output_) &&
          std::uint32_t(last_preload_source_)<scratchpad_rows_ &&
          (std::uint32_t(last_preload_output_)>>29)==4;
      const bool paired=pair_preload(*pending,ticket->admitted,funct,rs1,rs2);
      {
        const auto consumed=paired ? last_pair_consumed_.value() : schedule(*pending);
        // Actual PRELOAD owns D readout. Descriptor publication already carries
        // the consumed-result edge into the following PRELOADED compute.
        if(config_.ws_preload_operand_ownership && epoch_ws_configured_ && funct==4 &&
            pending->kind=="preload" && pending->rs1==last_preload_source_ &&
            consumed.start && consumed.ready && pending->latency && pending->occupancy &&
            *pending->occupancy<=std::numeric_limits<Cycle>::max()-*consumed.start) {
          consumed_preload_ready=std::max(*consumed.ready,*consumed.start+*pending->occupancy);
          for(const auto value:pending->reads)
            if(value>=local_base_ && value-local_base_<scratchpad_rows_)consumed_preload_rows.insert(value);
          for(const auto value:pending->writes)
            if(!local(value))consumed_preload_state.insert(value);
        }
      }
      pair_feed_.reset();
    }
    auto command = std::make_unique<Command>(kind, source, occupancy, *ticket, group, config, subtype);
    command->preissued=std::move(preissued_compute_); preissued_compute_.reset();
    command->transfer_phase = transfer_phase;
    command->rs1=rs1; command->rs2=rs2;
    command->earliest = ticket->admitted;
    if (config_.serialized_output_stationary_epochs && epoch_os_configured_ &&
        (funct == 4 || funct == 5)) {
      // OS keeps accumulations in the PE state. Conservative epochs include
      // flush/readout before reusing it; no mesh-stage overlap is credited.
      if (!last_compute_ready_) return unknown(source);
      command->earliest = std::max(command->earliest, *last_compute_ready_);
    }
    command->reads.insert(command->reads.end(), extra_reads.begin(), extra_reads.end());
    if (funct == 6) {
      if (config_.serialized_execute_epochs && computed_since_fence_)
        command->earliest = std::max(command->earliest, last_compute_feed_ready_.value_or(*last_compute_ready_));
      last_preload_source_ = rs1; last_preload_output_ = rs2;
      command->preload_requires_result = std::uint32_t(rs2) != 0xffffffffu;
      pending_ = std::move(command);
      return {ticket->admitted, ticket->admitted, ticket->admitted, merlin_timing::UnknownReason::none};
    }
    (void)rs2;
    // Keep all non-admitted shapes/dataflows on the old conservative rule.
    // The original split has no accumulator input, accumulation, transpose or
    // tail. The separate opt-in permits only output RMW reads in ACC.
    if (config_.split_ws_feed_lifetimes && epoch_ws_configured_ && funct == 4 &&
        a_stride_ == 1 && c_stride_ == 1 && kind == "compute_ws") {
      const auto full = [&](std::uint64_t packet) {
        return ((packet >> 32) & 65535) == dim_ && (packet >> 48) == dim_;
      };
      bool reads_sp = true, writes_acc = true, only_output_acc_reads = true;
      std::set<ValueId> acc_reads, acc_writes;
      std::size_t output_rows = 0;
      for (const auto value : command->reads)
        if (local(value) && value - local_base_ >= scratchpad_rows_) {
          reads_sp = false; acc_reads.insert(value);
        }
      for (const auto value : command->writes) if (local(value)) {
        if (value - local_base_ < scratchpad_rows_) writes_acc = false;
        else acc_writes.insert(value);
        ++output_rows;
      }
      command->split_ws = full(rs1) && full(rs2) && full(last_preload_source_) &&
          full(last_preload_output_) && std::uint32_t(last_preload_source_) != 0xffffffffu &&
          (std::uint32_t(last_preload_output_) >> 29) == 4 &&
          reads_sp && writes_acc && output_rows == dim_;
      // The trusted provider adds output reads only for ACC accumulation.
      // Inspect both packets and exact effects; an ACC mesh input, alias, tail,
      // or retained SP reader cannot inherit this narrower lifetime.
      for (const auto value : command->retained)
        if (local(value) && value - local_base_ < scratchpad_rows_)
          only_output_acc_reads = false;
      const auto sp_packet = [&](std::uint64_t p, bool garbage) {
        const auto address = std::uint32_t(p);
        return (garbage && address == 0xffffffffu) ||
            (address < scratchpad_rows_ && std::uint64_t(address) + dim_ <= scratchpad_rows_);
      };
      command->split_accumulating_ws = config_.split_ws_accumulate_operands &&
          full(rs1) && full(rs2) && full(last_preload_source_) && full(last_preload_output_) &&
          sp_packet(rs1, false) && sp_packet(rs2, true) && sp_packet(last_preload_source_, false) &&
          (std::uint32_t(last_preload_output_) >> 29) == 6 &&
          writes_acc && output_rows == dim_ && acc_writes.size() == dim_ &&
          acc_reads == acc_writes && only_output_acc_reads;
      // Keeping the FULL DIM occupancy avoids any assumption that the current
      // garbage B implies a future PRELOAD D is absent. This changes only SP
      // read holds; ACC/RMW, descriptors, RS/FIFO release and output latency stay
      // conservative. A/D may not share a single-ported bank in this subset.
      const auto bounded_sp = [&](std::uint64_t p,bool garbage) {
        const auto address=std::uint32_t(p),rows=std::uint32_t(p>>48);
        const auto cols=std::uint32_t((p>>32)&65535);
        if(!rows || rows>dim_ || !cols || cols>dim_)return false;
        return (garbage && address==0xffffffffu) ||
            (address<scratchpad_rows_ && std::uint64_t(address)+rows<=scratchpad_rows_);
      };
      const auto out_rows=std::uint32_t(last_preload_output_>>48);
      const auto out_cols=std::uint32_t((last_preload_output_>>32)&65535);
      const auto bank=config_.scratchpad_bank_rows;
      const auto a_row=std::uint32_t(rs1),d_row=std::uint32_t(last_preload_source_);
      command->bounded_ws_operands=config_.bounded_ws_operand_release &&
          !command->split_ws && !command->split_accumulating_ws && bank &&
          bounded_sp(rs1,false) && bounded_sp(rs2,true) && bounded_sp(last_preload_source_,false) &&
          std::uint32_t(rs2)==0xffffffffu && a_row/bank!=d_row/bank &&
          a_row%bank+dim_<=bank && d_row%bank+dim_<=bank &&
          ((std::uint32_t(last_preload_output_)>>29)==4 || (std::uint32_t(last_preload_output_)>>29)==6) &&
          out_rows>0 && out_rows<=dim_ && out_cols>0 && out_cols<=dim_ &&
          out_rows==(rs1>>48) && writes_acc && output_rows==out_rows &&
          acc_writes.size()==out_rows && only_output_acc_reads &&
          (reads_sp || acc_reads==acc_writes);

    }
    if(config_.ws_preload_operand_ownership && command->bounded_ws_operands &&
        consumed_preload_ready && !consumed_preload_rows.empty() && !consumed_preload_state.empty()) {
      // This narrow route excludes the old full-tile MUL_PRE pairing. A and D
      // are distinct SP banks, current B is garbage, no transposer/ACC input.
      // Remove only previous-D duplicate reads; actual future PRELOAD remains
      // independently ordered and owns its D read/port/RS/FIFO lifetime.
      std::set<ValueId> expected;
      const auto d=std::uint32_t(last_preload_source_),rows=std::uint32_t(last_preload_source_>>48);
      for(std::uint32_t r=0;r<rows;++r)expected.insert(local_base_+d+r);
      bool state_edge=false,retained_rhs=false,all_rhs=expected==consumed_preload_rows;
      for(const auto value:command->reads)if(consumed_preload_state.count(value))state_edge=true;
      for(const auto value:command->retained)if(expected.count(value))retained_rhs=true;
      for(const auto value:expected)
        if(std::find(command->reads.begin(),command->reads.end(),value)==command->reads.end())all_rhs=false;
      if(state_edge&&!retained_rhs&&all_rhs) {
        command->preload_operands_consumed=consumed_preload_ready;
        command->reads.erase(std::remove_if(command->reads.begin(),command->reads.end(),
            [&](ValueId value){return expected.count(value)!=0;}),command->reads.end());
      }
    }
    // This source proof was bound to the current actual committed PC/ELF.
    // It establishes no PRELOAD through a real fence without delaying this
    // event, reading future guest state or granting any command queue credit.
    if(config_.source_fenced_single_mul && proven_single_mul_ && funct==4 &&
       command->bounded_ws_operands && command->preload_operands_consumed &&
       std::uint32_t(rs2)==0xffffffffu && (rs1>>48)>0 && (rs1>>48)<dim_ &&
       command->occupancy && *command->occupancy>=dim_+1) {
      command->occupancy=std::max<Cycle>(rs1>>48,4)+1;
      command->source_single_feed=true;++fenced_single_feeds_;
    }
    const auto result = schedule(*command);
    if (group == 1 && (funct == 4 || funct == 5)) last_compute_ready_ = result.ready;
    return result;
  }

  bool pending_preload() const { return bool(pending_); }
  std::uint64_t bounded_pairings() const { return bounded_pairings_; }
  void proven_single_mul(bool value) { proven_single_mul_=value; }
  std::uint64_t fenced_single_feeds() const { return fenced_single_feeds_; }

private:
  using Window = merlin_timing::ReservationWindow;
  struct Preissued { Window::Ticket queue; Result issued; };
  struct Command {
    std::string kind;
    std::optional<Cycle> preload_operands_consumed;
    std::vector<ValueId> reads, writes, retained;
    std::vector<Demand> demands;
    std::optional<Cycle> latency, occupancy;
    Window::Ticket ticket;
    std::size_t group;
    bool config;
    bool preload_requires_result = false, split_ws = false, preload_feed_lifetime = false;
    bool split_accumulating_ws = false, bounded_ws_operands = false, late_accumulator_port = false;
    bool source_single_feed=false;
    std::optional<TransferPhase> transfer_phase;
    std::optional<Preissued> preissued;
    std::uint64_t subtype;
    std::uint64_t rs1=0,rs2=0;
    Cycle earliest;
    Command(const std::string &name, const Event &event, std::optional<Cycle> busy,
            Window::Ticket reservation, std::size_t selected, bool configuration, std::uint64_t type)
        : kind(name), reads(copy(event.reads)), writes(copy(event.writes)), retained(copy(event.retained_reads)),
          demands(copy(event.demands)), latency(event.latency), occupancy(busy), ticket(reservation),
          group(selected), config(configuration), subtype(type), earliest(event.earliest) {}
    template <class T> static std::vector<T> copy(View<T> view) {
      return view.size ? std::vector<T>(view.data, view.data + view.size) : std::vector<T>{};
    }
  };
  Engine &engine_;
  StagedConfig config_;
  ValueId execute_configuration_;
  std::set<ValueId> load_configuration_values_;
  std::array<std::unique_ptr<Window>, 3> reservations_, controllers_;
  std::array<std::unique_ptr<Window>, 2> dma_;
  std::unique_ptr<ScratchpadLoadStream> load_stream_;
  std::unique_ptr<PacketLoadStream>packet_load_stream_;
  std::unique_ptr<Command> pending_;
  std::optional<Window::Ticket> preload_retirement_;
  std::optional<std::size_t> last_data_group_;
  DependencyPhases phases_;
  bool audit_pending_preload_ = false, computed_since_fence_ = false, semantic_scope_known_ = true;
  bool epoch_ws_configured_ = false, epoch_os_configured_ = false;
  std::optional<Cycle> last_compute_ready_ = Cycle{0}, last_store_ready_ = Cycle{0};
  std::optional<Cycle> prior_execute_complete_ = Cycle{0};
  std::optional<Cycle> last_compute_feed_ready_;
  struct PairFeed { Cycle start, consumed, next_issue; std::uint64_t weights, a, b; };
  std::optional<PairFeed> pair_feed_;
  std::optional<Preissued> preissued_compute_;
  std::optional<Result> last_pair_consumed_;
  std::map<ResourceId,std::optional<Cycle>> observed_bank_horizons_;
  std::uint64_t bounded_pairings_=0,fenced_single_feeds_=0;
  bool proven_single_mul_=false;
  std::uint64_t last_preload_source_ = 0, last_preload_output_ = 0;
  std::function<void(const std::string &)> unresolved_;
  ValueId local_base_;
  std::uint32_t scratchpad_rows_, dim_, accumulator_rows_;
  std::uint32_t a_stride_ = 0, c_stride_ = 0;
  bool a_transpose_ = false;

  void missing(const std::string &reason) { if (unresolved_) unresolved_(reason); }

  bool independent_banks(std::size_t group, const DependencyPhases::Rows &rows,
                         std::size_t other, const DependencyPhases::Rows &prior) const {
    // DMA directions share external paths even when their SRAM banks differ.
    // ACC aliases/shared adder structure are not claimed independent: every
    // accumulator row maps to one conservative physical conflict class.
    if (!config_.allow_disjoint_scratchpad_banks || (group != 1 && other != 1)) return false;
    const auto banks = [&](const DependencyPhases::Rows &selected) {
      std::set<std::uint64_t> result;
      for (const auto value : selected) {
        const auto offset = value - local_base_;
        result.insert(offset < scratchpad_rows_ ? offset / config_.scratchpad_bank_rows :
                      scratchpad_rows_ / config_.scratchpad_bank_rows);
      }
      return result;
    };
    const auto left = banks(rows), right = banks(prior);
    for (const auto bank : left) if (right.count(bank)) return false;
    return true;
  }

  static bool extend(Cycle &earliest, std::optional<Cycle> value) {
    if (!value) return false;
    earliest = std::max(earliest, *value); return true;
  }
  Result unknown(const Event &source) {
    Event event = source; event.latency.reset();
    const auto result = submit_observed(event);
    engine_.advance_issue({});
    return result;
  }
  Result submit_observed(const Event &event) {
    const auto result=engine_.submit_detached(event);
    for(std::size_t i=0;i<event.demands.size;++i) {
      const auto &d=event.demands[i];
      if(std::find(config_.scratchpad_bank_resources.begin(),config_.scratchpad_bank_resources.end(),d.resource)==
          config_.scratchpad_bank_resources.end())continue;
      auto entry=observed_bank_horizons_.find(d.resource);
      if(entry==observed_bank_horizons_.end())entry=observed_bank_horizons_.emplace(d.resource,Cycle{0}).first;
      if(!entry->second || !result.start || !d.occupancy ||
          *d.occupancy>std::numeric_limits<Cycle>::max()-*result.start)entry->second.reset();
      else entry->second=std::max(*entry->second,*result.start+*d.occupancy);
    }
    return result;
  }
  bool bounded_packet(std::uint64_t p,bool garbage=false) const {
    const auto address=std::uint32_t(p),rows=std::uint32_t(p>>48),cols=std::uint32_t((p>>32)&65535);
    return rows && rows<=dim_ && cols && cols<=dim_ &&
        ((garbage && address==0xffffffffu) || (address<scratchpad_rows_ &&
        std::uint64_t(address)+rows<=scratchpad_rows_));
  }
  // Same actual three-command lookahead as the legacy full-tile path. This
  // extension never delays/backdates an already-started compute to pair it.
  // The next PRELOAD supplies D; current COMPUTE does not re-read old PE weights.
  bool pair_bounded_preload(Command &command,Cycle third_arrival,std::uint32_t funct,
                            std::uint64_t third_a,std::uint64_t third_b) {
    if(!config_.source_bounded_mul_pre_pairing || !pair_feed_ || funct!=4 ||
        !epoch_ws_configured_ || a_stride_!=1 || c_stride_!=1 ||
        command.kind!="preload" || !command.preload_requires_result || preload_retirement_ ||
        !config_.issue_latency || !config_.issue_occupancy || !command.latency || !command.occupancy)
      return false;
    const auto &feed=*pair_feed_;
    if(!bounded_packet(feed.a) || !bounded_packet(feed.b,true) ||
        std::uint32_t(feed.b)!=0xffffffffu || !bounded_packet(command.rs1) ||
        !bounded_packet(third_a) || !bounded_packet(third_b,true) ||
        std::uint32_t(third_b)!=0xffffffffu || feed.consumed<feed.start ||
        feed.consumed-feed.start<dim_ || *command.occupancy>feed.consumed-feed.start ||
        *command.latency>feed.consumed-feed.start)return false;
    const auto output=std::uint32_t(command.rs2),output_rows=std::uint32_t(command.rs2>>48);
    const auto output_cols=std::uint32_t((command.rs2>>32)&65535),offset=output&0x1fffffffu;
    if(((output>>29)!=4 && (output>>29)!=6) || !output_rows || output_rows>dim_ ||
        !output_cols || output_cols>dim_ || std::uint64_t(offset)+output_rows>accumulator_rows_)
      return false;
    const auto bank_rows=config_.scratchpad_bank_rows;
    const auto drow=std::uint32_t(command.rs1),arow=std::uint32_t(feed.a);
    if(!bank_rows || arow/bank_rows==drow/bank_rows ||
        arow%bank_rows+dim_>bank_rows || drow%bank_rows+dim_>bank_rows)return false;
    // Both target arrivals and the actual third compute must be resident
    // before the first feed starts. Source RAW check sees SP inputs vs ACC
    // mesh tags in this subset; no ACC input or SP output is admitted.
    const Cycle issue_start=std::max({third_arrival,command.ticket.admitted,
        engine_.issue_frontier().value_or(std::numeric_limits<Cycle>::max()),feed.next_issue});
    if(issue_start>feed.start || *config_.issue_occupancy>feed.start-issue_start ||
        *config_.issue_latency>feed.start-issue_start-*config_.issue_occupancy)return false;
    for(const auto value:command.reads) {
      const auto ready=engine_.ready(value);if(!ready || *ready>issue_start)return false;
    }
    for(std::uint32_t r=0;r<output_rows;++r) {
      const auto ready=engine_.last_use(local_base_+scratchpad_rows_+offset+r);
      if(!ready || *ready>issue_start)return false;
    }
    for(std::uint32_t r=0;r<std::uint32_t(third_a>>48);++r) {
      const auto ready=engine_.ready(local_base_+std::uint32_t(third_a)+r);
      if(!ready || *ready>issue_start)return false;
    }
    const auto bank=config_.scratchpad_bank_resources.at(drow/bank_rows);
    const auto horizon=observed_bank_horizons_.find(bank);
    if(horizon!=observed_bank_horizons_.end() &&
       (!horizon->second || *horizon->second>feed.start))return false;
    auto preview=*controllers_[1];const auto next=preview.allocate(issue_start);
    const auto third=preview.allocate(issue_start+*config_.issue_occupancy);
    if(!next || !third || next->admitted>issue_start ||
        third->admitted>issue_start+*config_.issue_occupancy)return false;
    const auto queue=controllers_[1]->allocate(issue_start);
    const auto third_queue=controllers_[1]->allocate(issue_start+*config_.issue_occupancy);
    if(!queue || !third_queue)throw std::logic_error("bounded FIFO preview changed");
    const Demand issue_demand{config_.issue_resources[1],1,config_.issue_occupancy};
    Event issue{issue_start,{},{},{&issue_demand,1},config_.issue_latency};
    const auto issued=submit_observed(issue);issue.earliest=issue_start+*config_.issue_occupancy;
    const auto issued_third=submit_observed(issue);
    if(!issued.ready || !issued_third.ready || *issued.ready>feed.start || *issued_third.ready>feed.start)
      throw std::logic_error("bounded source issue preview changed");
    preissued_compute_=Preissued{*third_queue,issued_third};
    const Demand port{bank,1,*command.occupancy};
    Event input{feed.start,{command.reads.data(),command.reads.size()},{},{&port,1},
        *command.occupancy,true};
    const auto consumed=submit_observed(input);
    if(!consumed.start || *consumed.start!=feed.start || !consumed.ready || *consumed.ready>feed.consumed)
      throw std::logic_error("bounded D port/source readiness changed after preview");
    Event published{feed.consumed,{},{command.writes.data(),command.writes.size()},{},Cycle{0},true};
    const auto done=submit_observed(published);
    if(!done.ready || *done.ready!=feed.consumed)
      throw std::logic_error("bounded paired descriptor changed dependency lifetime");
    controllers_[1]->release(*queue,feed.consumed);preload_retirement_=command.ticket;
    last_pair_consumed_=Result{issued.issue,feed.start,feed.consumed,merlin_timing::UnknownReason::none};
    ++bounded_pairings_;return true;
  }
  bool pair_preload(Command &command, Cycle third_arrival, std::uint32_t funct,
                    std::uint64_t a, std::uint64_t b) {
    last_pair_consumed_.reset();
    if(pair_bounded_preload(command,third_arrival,funct,a,b))return true;
    if (!config_.ws_resident_mul_pre_pairing || !pair_feed_ || funct != 4 ||
        !epoch_ws_configured_ || a_stride_ != 1 || c_stride_ != 1 ||
        command.kind != "preload" || !command.preload_requires_result || preload_retirement_ ||
        !config_.issue_latency || !config_.issue_occupancy || !command.latency || !command.occupancy)
      return false;
    const auto &feed=*pair_feed_;
    const auto full=[&](std::uint64_t p){return (p>>48)==dim_ && ((p>>32)&65535)==dim_;};
    const auto output=std::uint32_t(last_preload_output_);
    if (last_preload_source_!=feed.weights || !full(last_preload_source_) ||
        !full(last_preload_output_) || (output>>29)!=4 ||
        !full(a) || !full(b) || std::uint32_t(a)>=scratchpad_rows_ ||
        std::uint32_t(b)!=0xffffffffu ||
        feed.consumed<feed.start || *command.occupancy>feed.consumed-feed.start ||
        *command.latency>feed.consumed-feed.start)
      return false;
    // A and D share a physical SRAM read arbiter within a bank. The current
    // conservative reservation cannot grant two distinct reads there per row.
    const auto bank_rows=config_.scratchpad_bank_rows;
    const auto weight_row=std::uint32_t(feed.weights),a_row=std::uint32_t(feed.a);
    if (!bank_rows || std::uint32_t(feed.b)!=0xffffffffu ||
        weight_row/bank_rows==a_row/bank_rows ||
        weight_row%bank_rows+dim_>bank_rows || a_row%bank_rows+dim_>bank_rows)
      return false;
    // The selected RTL consults a third resident command for its RAW check.
    // Both commands must exist before the already reserved feed begins. Never
    // delay or backdate an already-started compute to invent an overlap.
    const Cycle issue_start=std::max({third_arrival,command.ticket.admitted,
        engine_.issue_frontier().value_or(std::numeric_limits<Cycle>::max()),feed.next_issue});
    if (issue_start>feed.start || *config_.issue_occupancy>feed.start-issue_start ||
        *config_.issue_latency>feed.start-issue_start-*config_.issue_occupancy) return false;
    const auto offset=output&0x1fffffffu;
    if (std::uint64_t(offset)+dim_>accumulator_rows_) return false;
    for (std::uint32_t row=0;row<dim_;++row) {
      const auto output_ready=engine_.last_use(local_base_+scratchpad_rows_+offset+row);
      if (!output_ready || *output_ready>issue_start) return false;
    }
    for (const auto value:command.reads) {
      const auto ready=engine_.ready(value);
      if (!ready || *ready>issue_start) return false;
    }
    if (std::uint64_t(std::uint32_t(a))+dim_>scratchpad_rows_) return false;
    for (std::uint32_t row=0;row<dim_;++row) {
      const auto ready=engine_.ready(local_base_+std::uint32_t(a)+row);
      if (!ready || *ready>issue_start) return false;
    }
    // Preview preserves queue ownership if the conservative fallback is used.
    auto preview=*controllers_[1]; const auto available=preview.allocate(issue_start);
    const auto third_available=preview.allocate(issue_start+*config_.issue_occupancy);
    if (!available || !third_available || available->admitted>issue_start ||
        third_available->admitted>issue_start+*config_.issue_occupancy) return false;
    const auto queue=controllers_[1]->allocate(issue_start);
    const auto third_queue=controllers_[1]->allocate(issue_start+*config_.issue_occupancy);
    if (!queue || !third_queue) throw std::logic_error("paired FIFO preview changed without an intervening event");
    const Demand issue_demand{config_.issue_resources[1],1,config_.issue_occupancy};
    Event issued_event{issue_start,{},{},{&issue_demand,1},config_.issue_latency};
    const auto issued=submit_observed(issued_event);
    if (!issued.ready || *issued.ready>feed.start)
      throw std::logic_error("paired issue timing differs from retained same-controller frontier");
    Event third_issue=issued_event; third_issue.earliest=issue_start+*config_.issue_occupancy;
    const auto issued_third=submit_observed(third_issue);
    if (!issued_third.ready || *issued_third.ready>feed.start)
      throw std::logic_error("third command did not enter FIFO before paired feed start");
    preissued_compute_=Preissued{*third_queue,issued_third};
    // Same weight rows already occupy the compute's SP bank reservation;
    // they are PRELOAD D input while compute consumes A. No extra SRAM port
    // or execute feed is added. Publish only the NEXT descriptor at consumed.
    Event published{feed.consumed,{command.reads.data(),command.reads.size()},
        {command.writes.data(),command.writes.size()},{},Cycle{0},true};
    const auto done=submit_observed(published);
    if (!done.ready || *done.ready!=feed.consumed)
      throw std::logic_error("paired descriptor changed a retained dependency lifetime");
    controllers_[1]->release(*queue,feed.consumed);
    preload_retirement_=command.ticket; // final result is the following MUL's tag
    last_pair_consumed_=Result{issued.issue,feed.start,feed.consumed,merlin_timing::UnknownReason::none};
    return true;
  }
  Result schedule(Command &command) {
    auto &rs = *reservations_[command.group];
    Cycle earliest = command.earliest;
    bool known = true;
    // The selected RTL keeps same-ST dependencies until completion, unlike
    // LD/EX dependencies which clear on issue. Queue occupancy alone is not
    // this completion edge. Preserve the old profile and enforce it in v3.
    if (config_.serialized_execute_epochs && command.group == 2)
      known = extend(earliest, last_store_ready_) && known;
    for (const auto value : command.reads) known = extend(earliest, engine_.ready(value)) && known;
    for (const auto value : command.writes) known = extend(earliest, engine_.last_use(value)) && known;
    if (command.config && command.subtype == 0)
      known = extend(earliest, rs.drained(earliest, command.ticket)) && known;
    auto queue = command.preissued ? std::optional<Window::Ticket>{command.preissued->queue} :
        controllers_[command.group]->allocate(earliest);
    known = bool(queue) && known;
    if (queue) earliest = std::max(earliest, queue->admitted);
    const Demand issue_demand{config_.issue_resources[command.group], 1, config_.issue_occupancy};
    Event issue{earliest, {}, {}, {&issue_demand, 1}, known ? config_.issue_latency : std::nullopt};
    const auto issued = command.preissued ? command.preissued->issued : submit_observed(issue);
    if (command.config && command.subtype != 0) rs.release(command.ticket, issued.ready);

    std::optional<Window::Ticket> dma_ticket;
    std::size_t dma_index = command.group == 2 ? 1 : 0;
    Cycle consume = std::max(issued.ready.value_or(earliest),earliest);
    if(command.preload_operands_consumed)consume=std::max(consume,*command.preload_operands_consumed);
    known = bool(issued.ready) && known;
    if (!command.config && command.group != 1) {
      dma_ticket = dma_[dma_index]->allocate(consume);
      known = bool(dma_ticket) && known;
      if (dma_ticket) consume = std::max(consume, dma_ticket->admitted);
    }
    command.split_ws = command.split_ws && known && command.latency && command.occupancy &&
        *command.latency >= *command.occupancy && *command.occupancy >= dim_;
    command.split_accumulating_ws = command.split_accumulating_ws && known &&
        command.latency && command.occupancy && *command.latency >= *command.occupancy &&
        *command.occupancy >= dim_;
    command.bounded_ws_operands = command.bounded_ws_operands && known && command.latency &&
        command.occupancy && *command.latency>=*command.occupancy &&
        *command.occupancy>=(command.source_single_feed?Cycle{5}:Cycle{dim_});
    command.late_accumulator_port = config_.late_accumulator_write_pipeline &&
        (command.split_accumulating_ws || command.bounded_ws_operands) && command.latency &&
        *command.latency>=dim_+*config_.late_accumulator_write_pipeline;
    command.demands.push_back({config_.controller_resources[command.group], 1, command.occupancy});
    if (config_.conservative_local_store_holds &&
        !(command.transfer_phase && command.transfer_phase->scratchpad_load)) {
      // A declared conservative abstraction: hold every touched local store
      // through the whole effect, including gaps during DMA/mesh service. This
      // admits less overlap than the RTL and never invents a second SP port.
      // ACC aliases/ports collapse to one explicit conservative conflict class.
      std::set<ResourceId> stores;
      for (const auto *tokens : {&command.reads, &command.writes})
        for (const auto value : *tokens) {
          if (value < local_base_) continue;
          const auto row = value - local_base_;
          if (row < scratchpad_rows_)
            stores.insert(config_.scratchpad_bank_resources[row / config_.scratchpad_bank_rows]);
          else if (row - scratchpad_rows_ < accumulator_rows_ && !command.split_ws && !command.late_accumulator_port)
            stores.insert(*config_.accumulator_storage_resource);
        }
      const auto hold = command.split_ws ? command.occupancy : command.latency && command.occupancy ?
          std::optional<Cycle>{std::max(*command.latency, *command.occupancy)} : std::nullopt;
      for (const auto store : stores) {
        const bool sp_feed = (command.split_accumulating_ws || command.bounded_ws_operands) &&
            store != *config_.accumulator_storage_resource;
        command.demands.push_back({store, 1, sp_feed ? command.occupancy : hold});
      }
    }
    Event effect{consume, {command.reads.data(), command.reads.size()},
        {command.writes.data(), command.writes.size()}, {command.demands.data(), command.demands.size()},
        known ? command.latency : std::nullopt, true, {command.retained.data(), command.retained.size()}};
    // Only CONFIG_MVIN-owned state reads end at final request acceptance.
    // Data/output/cache dependencies and ROB/DMA credits retain result lifetime.
    std::vector<ValueId> load_publish_reads=command.reads;
    const auto release_load_configuration=[&](Cycle start,std::optional<Cycle> accepted) {
      if(!config_.load_configuration_request_lifetime)return true;
      if(command.group!=0 || command.config || command.kind!="load" || !accepted || *accepted<start)return false;
      std::vector<ValueId> configuration;
      for(const auto value:command.reads)
        if(load_configuration_values_.count(value))configuration.push_back(value);
      // Unknown configuration custody preserves the old conservative path.
      if(configuration.empty())return true;
      Event lease{start,{configuration.data(),configuration.size()},{},{},*accepted-start,true};
      const auto released=submit_observed(lease);
      if(!released.ready || *released.ready!=*accepted)return false;
      load_publish_reads.erase(std::remove_if(load_publish_reads.begin(),load_publish_reads.end(),
          [&](ValueId value){return load_configuration_values_.count(value)!=0;}),load_publish_reads.end());
      return true;
    };
    Result result;
    std::optional<Cycle> feed_ready;
    std::optional<Cycle> load_requests_complete;
    if(command.transfer_phase && !command.transfer_phase->reader_packets.empty()) {
      const auto &phase=*command.transfer_phase;
      if(!packet_load_stream_ || command.group!=0 || command.kind!="load" || !known ||
          !command.latency || !command.occupancy || !phase.row_memory ||
          phase.row_bytes<1 || phase.row_bytes>(phase.individual_row_publication?127:16) || command.writes.empty() ||
          command.writes.size()>(phase.individual_row_publication?128:16) || phase.row_transfers.size()!=phase.reader_packets.size())
        return unknown(effect);
      for(const auto value:command.writes)
        if(value<local_base_ || value-local_base_>=scratchpad_rows_)return unknown(effect);
      auto destinations=phase.reader_destinations;
      if(destinations.size()!=command.writes.size())return unknown(effect);
      auto sorted_destinations=destinations;std::sort(sorted_destinations.begin(),sorted_destinations.end());
      if(std::adjacent_find(sorted_destinations.begin(),sorted_destinations.end())!=sorted_destinations.end() ||
          sorted_destinations!=command.writes)return unknown(effect);
      std::vector<std::uint64_t> masks(destinations.size(),0),finals(destinations.size(),0);
      for(const auto &packet:phase.reader_packets)for(const auto &fragment:packet.outputs) {
        if(fragment.destination>=destinations.size() || masks[fragment.destination]&fragment.mask)
          return unknown(effect);
        masks[fragment.destination]|=fragment.mask;
        finals[fragment.destination]+=fragment.destination_complete;
      }
      for(std::size_t i=0;i<destinations.size();++i)
        if(!masks[i] || finals[i]!=1)return unknown(effect);
      auto initial=command.demands;
      for(auto &d:initial){if(!d.occupancy)return unknown(effect);d.occupancy=0;}
      Event admission=effect;admission.writes={};admission.latency=0;
      admission.demands={initial.data(),initial.size()};admission.hold_reads_until_ready=false;
      const auto admitted=submit_observed(admission);if(!admitted.start)return unknown(effect);
      const auto stream=packet_load_stream_->schedule(phase.reader_packets,*admitted.start,
          [&](std::size_t i,Cycle at) {
        const auto memory=phase.row_memory({&phase.row_transfers[i],1});
        for(const auto &d:memory.demands) {
          for(auto bank:config_.scratchpad_bank_resources)if(d.resource==bank)return Result{};
          for(const auto &local:command.demands)if(d.resource==local.resource)return Result{};
        }
        Event transfer{at,{memory.reads.data(),memory.reads.size()},
            {memory.writes.data(),memory.writes.size()},
            {memory.demands.data(),memory.demands.size()},memory.minimum_latency,true};
        return submit_observed(transfer);
      },[&](std::size_t row,bool last,Cycle at) {
        if(row>=destinations.size())return Result{};
        const ValueId destination=destinations[row];
        const auto bank=(destination-local_base_)/config_.scratchpad_bank_rows;
        const Demand port{config_.scratchpad_bank_resources.at(bank),1,Cycle{1}};
        // Multiple actual masked writes retain the port hazard, but full-row
        // readiness is published only after the final actual packet fragment.
        Event write{at,{},last ? View<ValueId>{&destination,1}:View<ValueId>{},
            {&port,1},Cycle{1}};
        return submit_observed(write);
      });
      if(!stream.complete || !stream.requests_complete ||
          *command.latency>std::numeric_limits<Cycle>::max()-*admitted.start)return unknown(effect);
      auto controller=command.demands;
      for(auto &d:controller)d.occupancy=std::max(*d.occupancy,*stream.requests_complete-*admitted.start);
      Event request_hold{*admitted.start,{},{},{controller.data(),controller.size()},Cycle{0}};
      const auto held=submit_observed(request_hold);if(held.start!=admitted.start)return unknown(effect);
      // Retain old aggregate service floor for now; source-owned removal is a
      // separate experiment. Only DMA-flight bank monopolization changes here.
      if(!release_load_configuration(*admitted.start,stream.requests_complete))return unknown(effect);
      Event publish=effect;publish.earliest=std::max(*stream.complete,*admitted.start+*command.latency);
      publish.reads={load_publish_reads.data(),load_publish_reads.size()};
      // Exact destination fragments already published their own readiness.
      // Command/ROB/DMA completion must not overwrite every row with the
      // last row's completion. The old narrow path stays unchanged.
      if(phase.individual_row_publication)publish.writes={};
      publish.demands={};publish.latency=0;const auto done=submit_observed(publish);
      result={admitted.issue,admitted.start,done.ready,done.unknown};load_requests_complete=stream.requests_complete;
    } else if(command.transfer_phase && command.transfer_phase->scratchpad_load) {
      const auto &phase=*command.transfer_phase;
      const auto count=phase.row_transfers.size();
      if(!load_stream_ || command.group!=0 || command.kind!="load" || !known ||
          !command.latency || !command.occupancy || !phase.row_memory ||
          phase.row_bytes!=16 || !count || count>16 || command.writes.size()!=count)
        return unknown(effect);
      for(const auto value:command.writes)
        if(value<local_base_ || value-local_base_>=scratchpad_rows_) return unknown(effect);
      // Reserve controller only after the row request schedule is known. The
      // admission checks its existing frontier without reserving DMA latency
      // on a scratchpad bank. All source/WAR/WAW edges were checked above.
      auto initial=command.demands;
      for(auto &d:initial) {if(!d.occupancy)return unknown(effect);d.occupancy=0;}
      Event admission=effect;admission.writes={};admission.latency=0;
      admission.demands={initial.data(),initial.size()};admission.hold_reads_until_ready=false;
      const auto admitted=submit_observed(admission);
      if(!admitted.start)return unknown(effect);
      const auto streamed=load_stream_->schedule(count,*admitted.start,
          [&](std::size_t row,Cycle at) {
        const auto memory=phase.row_memory({&phase.row_transfers[row],1});
        for(const auto &d:memory.demands) {
          for(auto bank:config_.scratchpad_bank_resources) if(d.resource==bank)return Result{};
          for(const auto &local:command.demands) if(d.resource==local.resource)return Result{};
        }
        Event transfer{at,{memory.reads.data(),memory.reads.size()},
            {memory.writes.data(),memory.writes.size()},
            {memory.demands.data(),memory.demands.size()},memory.minimum_latency,true};
        return submit_observed(transfer);
      },[&](std::size_t row,Cycle at) {
        const ValueId destination=command.writes[row];
        const auto bank=(destination-local_base_)/config_.scratchpad_bank_rows;
        const Demand port{config_.scratchpad_bank_resources.at(bank),1,Cycle{1}};
        Event write{at,{},{&destination,1},{&port,1},Cycle{1}};
        return submit_observed(write);
      });
      if(!streamed.complete || !streamed.requests_complete ||
          *command.latency>std::numeric_limits<Cycle>::max()-*admitted.start) return unknown(effect);
      auto controller=command.demands;
      for(auto &d:controller)d.occupancy=std::max(*d.occupancy,*streamed.requests_complete-*admitted.start);
      Event request_hold{*admitted.start,{},{},{controller.data(),controller.size()},Cycle{0}};
      const auto held=submit_observed(request_hold);
      if(held.start!=admitted.start)return unknown(effect);
      if(!release_load_configuration(*admitted.start,streamed.requests_complete))return unknown(effect);
      Event publish=effect;publish.earliest=std::max(*streamed.complete,*admitted.start+*command.latency);
      publish.reads={load_publish_reads.data(),load_publish_reads.size()};
      publish.demands={};publish.latency=0;
      const auto done=submit_observed(publish);
      result={admitted.issue,admitted.start,done.ready,done.unknown};
      load_requests_complete=streamed.requests_complete;
    } else if (command.transfer_phase && (!command.transfer_phase->rows.empty() ||
        !command.transfer_phase->row_transfers.empty())) {
      const auto &phase=*command.transfer_phase;
      const auto row_count=phase.row_transfers.empty()?phase.rows.size():phase.row_transfers.size();
      if(!config_.readout_stream || !config_.conservative_local_store_holds || !known ||
          !command.latency || row_count>dim_ ||
          (!phase.row_transfers.empty() && !phase.row_memory)) return unknown(effect);
      std::vector<TransferEffects> observed_rows;
      auto initial_demands=command.demands;
      for(auto &d:initial_demands) {
        if(!d.occupancy)return unknown(effect);
        for(const auto &row:phase.rows) for(const auto &m:row.demands)
          if(d.resource==m.resource)return unknown(effect);
        d.occupancy=0;
      }
      Event admission=effect;admission.demands={initial_demands.data(),initial_demands.size()};
      admission.writes={};admission.latency=0;admission.hold_reads_until_ready=false;
      const auto admitted=submit_observed(admission);
      if(!admitted.start)return unknown(effect);
      auto packet_memory=[&](std::size_t row,std::optional<std::size_t> packet,Cycle at,Cycle beats) {
        if(packet) {
          if(row>=phase.writer_packets.size() || *packet>=phase.writer_packets[row].size())return Result{};
          const auto &p=phase.writer_packets[row][*packet];
          if(!p.full)return Result{};
          const Transfer transfer{p.address,1,p.bytes,p.bytes,true};
          observed_rows.push_back(phase.row_memory({&transfer,1}));
        } else observed_rows.push_back(phase.row_transfers.empty()?phase.rows[row]:
            phase.row_memory({&phase.row_transfers[row],1}));
        const auto &memory=observed_rows.back();
        for(const auto &d:memory.demands) for(const auto &local:command.demands)
          if(d.resource==local.resource)return Result{};
        Event transfer{at,{memory.reads.data(),memory.reads.size()},
            {memory.writes.data(),memory.writes.size()},
            {memory.demands.data(),memory.demands.size()},
            memory.minimum_latency ? std::optional<Cycle>{std::max(beats,*memory.minimum_latency)} : std::nullopt,true};
        return submit_observed(transfer);
      };
      const auto streamed=phase.writer_packets.empty() ?
          stream_readout(*config_.readout_stream,row_count,phase.row_bytes,*admitted.start,
              [&](std::size_t row,Cycle at,Cycle beats){return packet_memory(row,{},at,beats);}) :
          stream_packet_readout(*config_.readout_stream,phase.writer_packets,*admitted.start,
              [&](std::size_t row,std::size_t packet,Cycle at,Cycle beats){return packet_memory(row,packet,at,beats);});
      if(!streamed.complete || *streamed.complete<*admitted.start)return unknown(effect);
      const auto duration=std::max(*command.latency,*streamed.complete-*admitted.start);
      auto held=command.demands;
      for(auto &d:held)d.occupancy=std::max(*d.occupancy,duration);
      // All row writes have finished. Keep the existing conservative local
      // resources and source/output hazards through the entire streamed call.
      Event finish=effect;finish.earliest=*admitted.start;
      finish.demands={held.data(),held.size()};finish.latency=duration;
      // Aggregate memory tokens were already published by exact row events;
      // re-reading them here would serialize completion twice. Their final
      // hazard hold is extended below without replaying their service.
      std::vector<ValueId> local_reads,local_writes;
      std::set<ValueId> memory_tokens;
      for(const auto &row:observed_rows) for(const auto *tokens:{&row.reads,&row.writes})
        memory_tokens.insert(tokens->begin(),tokens->end());
      for(auto v:command.reads) if(!memory_tokens.count(v))local_reads.push_back(v);
      for(auto v:command.writes) if(!memory_tokens.count(v))local_writes.push_back(v);
      finish.reads={local_reads.data(),local_reads.size()};
      finish.writes={local_writes.data(),local_writes.size()};
      const auto finished=submit_observed(finish);
      if(!finished.start || *finished.start!=*admitted.start)return unknown(effect);
      auto published_reads=command.reads,published_writes=command.writes;
      for(const auto &row:observed_rows) {
        published_reads.insert(published_reads.end(),row.reads.begin(),row.reads.end());
        published_writes.insert(published_writes.end(),row.writes.begin(),row.writes.end());
      }
      Event publish=effect;publish.earliest=finished.ready.value_or(*admitted.start);
      publish.reads={published_reads.data(),published_reads.size()};
      publish.writes={published_writes.data(),published_writes.size()};
      publish.demands={};publish.latency=finished.ready ? std::optional<Cycle>{0} : std::nullopt;
      const auto published=submit_observed(publish);
      result={admitted.issue,admitted.start,published.ready,published.unknown};
    } else if (command.transfer_phase) {
      const auto &phase = *command.transfer_phase;
      if (command.group != 2 || !phase.arrival || !command.latency || *command.latency < phase.arrival)
        return unknown(effect);
      // Producer begins at the normal local/controller admission. Coherent
      // memory cannot reserve service before the first ACC data is available.
      // Retain scalar local service as a competing whole-operation floor;
      // do not add the entire local and memory durations serially.
      auto producer_demands = command.demands;
      auto consumer_demands = phase.demands;
      for (auto &demand : producer_demands) {
        if (!demand.occupancy) return unknown(effect);
        for (const auto &memory : phase.demands)
          if (memory.resource == demand.resource) return unknown(effect);
        consumer_demands.push_back({demand.resource, demand.units,
            *demand.occupancy > phase.arrival ? *demand.occupancy - phase.arrival : 0});
        demand.occupancy = std::min(*demand.occupancy, phase.arrival);
      }
      Event producer = effect;
      producer.writes = {};
      producer.demands = {producer_demands.data(), producer_demands.size()};
      producer.latency = phase.arrival;
      const auto produced = submit_observed(producer);
      Event consumer = effect;
      consumer.earliest = produced.ready.value_or(consume);
      consumer.demands = {consumer_demands.data(), consumer_demands.size()};
      consumer.latency = produced.ready ? std::optional<Cycle>{*command.latency-phase.arrival} : std::nullopt;
      const auto completed = submit_observed(consumer);
      result = {produced.issue, produced.start, completed.ready, completed.unknown};
    } else if (command.late_accumulator_port) {
      // Actual output rows reach ACC after input consumption; the two-port
      // write/RMW pipeline does not reserve ACC during the whole mesh latency.
      // Keep FULL DIM plus registered drain as conservative output-service
      // envelope anchored to the ORIGINAL result latency. No tail shortening,
      // output-row early readiness, same-address relaxation or queue grant.
      std::vector<ValueId> input_writes,output_writes;
      if(config_.bounded_ws_descriptor_consumption) {
        for(const auto value:command.writes) {
          const bool acc=value>=local_base_+scratchpad_rows_ &&
              value-local_base_-scratchpad_rows_<accumulator_rows_;
          (acc?output_writes:input_writes).push_back(value);
        }
      } else output_writes=command.writes;
      Event input=effect;input.writes={input_writes.data(),input_writes.size()};input.latency=command.occupancy;
      const auto fed=submit_observed(input);
      const Cycle duration=dim_+*config_.late_accumulator_write_pipeline;
      const auto offset=*command.latency-duration;
      const bool bounded=fed.start && offset<=std::numeric_limits<Cycle>::max()-*fed.start;
      std::vector<ValueId> late_reads;
      for(const auto value:command.reads) {
        const bool acc=value>=local_base_+scratchpad_rows_ &&
            value-local_base_-scratchpad_rows_<accumulator_rows_;
        if(config_.bounded_ws_descriptor_consumption?acc:
           value<local_base_ || value-local_base_>=scratchpad_rows_)late_reads.push_back(value);
      }
      const Demand port{*config_.accumulator_storage_resource,1,duration};
      Event output{bounded?*fed.start+offset:consume,{late_reads.data(),late_reads.size()},
          {output_writes.data(),output_writes.size()},{&port,1},
          bounded&&fed.ready?std::optional<Cycle>{duration}:std::nullopt,true,
          {command.retained.data(),command.retained.size()}};
      const auto written=submit_observed(output);
      result={fed.issue,fed.start,written.ready,written.unknown};
      if(config_.bounded_ws_descriptor_consumption) {
        feed_ready=fed.ready;last_compute_feed_ready_=fed.ready;
      } else last_compute_feed_ready_.reset();
    } else if (command.split_accumulating_ws || command.bounded_ws_operands) {
      // ExecuteController ends SP reads at about_to_fire_all_rows. Accumulator
      // RMW is a later mesh-response write; keep its old conservative resource
      // hold and every non-SP dependency/result at the original completion.
      // No earlier RS/FIFO release or MUL/PRE pairing is enabled here.
      Event input = effect; input.writes = {}; input.latency = command.occupancy;
      const auto fed = submit_observed(input);
      std::vector<ValueId> late_reads;
      for (const auto value : command.reads)
        if (value < local_base_ || value - local_base_ >= scratchpad_rows_)
          late_reads.push_back(value);
      const bool bounded = fed.start && *command.latency <=
          std::numeric_limits<Cycle>::max() - *fed.start;
      Event completed = effect;
      completed.earliest = bounded ? *fed.start + *command.latency : consume;
      completed.reads = {late_reads.data(), late_reads.size()}; completed.demands = {};
      completed.latency = bounded && fed.ready ? std::optional<Cycle>{0} : std::nullopt;
      const auto published = submit_observed(completed);
      result = {fed.issue, fed.start, published.ready, published.unknown};
      last_compute_feed_ready_.reset();
    } else if (command.split_ws) {
      // Selected ExecuteController pops consumed operands at about_to_fire_all_rows;
      // mesh tag retirement/output writes occur later. Do not retain all SP banks
      // and descriptor/PE input state through the whole result propagation.
      std::vector<ValueId> input_writes, output_writes;
      for (const auto value : command.writes) {
        const bool acc = value >= local_base_ + scratchpad_rows_ &&
            value - local_base_ - scratchpad_rows_ < accumulator_rows_;
        (acc ? output_writes : input_writes).push_back(value);
      }
      Event input = effect;
      input.writes = {input_writes.data(), input_writes.size()};
      input.latency = command.occupancy;
      const auto fed = submit_observed(input);
      feed_ready = fed.ready;
      last_compute_feed_ready_ = fed.ready;
      // A full ACC tile publishes at the old selected result latency. One
      // conservative ACC write-port reservation spans its final DIM row cycles.
      // This is structural peak row service, not a fitted sustained bandwidth.
      const auto offset = *command.latency - dim_;
      const bool bounded = fed.start && offset <= std::numeric_limits<Cycle>::max() - *fed.start;
      const Demand output_port{*config_.accumulator_storage_resource, 1, dim_};
      Event output{bounded ? *fed.start + offset : consume, {},
          {output_writes.data(), output_writes.size()}, {&output_port, 1},
          bounded && fed.ready ? std::optional<Cycle>{dim_} : std::nullopt,
          true, {command.retained.data(), command.retained.size()}};
      const auto written = submit_observed(output);
      result = {fed.issue, fed.start, written.ready, written.unknown};
    } else {
      result = submit_observed(effect);
      if (command.kind.compare(0, 8, "compute_") == 0) last_compute_feed_ready_.reset();
    }
    const bool split_release = config_.ws_feed_queue_release && command.split_ws;
    // ExecuteController pops single MUL only at about_to_fire_all_rows, not
    // when it starts consuming its FIFO entry. Other subsets retain legacy.
    auto fifo_release=load_requests_complete ? load_requests_complete :
        (split_release || (config_.bounded_ws_descriptor_consumption && command.late_accumulator_port)) ?
        feed_ready : result.start;
    if (command.preload_feed_lifetime && result.start && command.occupancy && command.latency) {
      const auto consumed=std::max(*command.occupancy,*command.latency);
      fifo_release=consumed<=std::numeric_limits<Cycle>::max()-*result.start ?
          std::optional<Cycle>{*result.start+consumed} : std::nullopt;
    }
    if (queue) controllers_[command.group]->release(*queue, fifo_release);
    if (dma_ticket) dma_[dma_index]->release(*dma_ticket, result.ready);
    if (command.kind == "preload" && command.preload_requires_result) {
      // Descriptor/feed readiness is not retirement: a non-garbage PRELOAD
      // carries the mesh output tag. Its RS entry survives through the later
      // compute's result completion, even if descriptor consumption finished.
      if (preload_retirement_) {
        // A second unretired destination requires the overlapped mesh/tag
        // protocol, outside this initial staged subset. Never reuse its entry.
        Event unresolved; unresolved.earliest = command.earliest;
        submit_observed(unresolved);
        missing("staged:overlapped_preload_tag_retirement_not_admitted");
      }
      preload_retirement_ = command.ticket;
    } else if (!command.config || command.subtype == 0) {
      auto completion = result.ready;
      // pending_completed_rob_ids is registered; mesh tag completion has
      // priority. Credit its one-cycle path ONLY if all earlier scheduled EX
      // completions have already drained, and this MUL's own output tag is
      // strictly later. Otherwise retain the conservative result lifetime.
      // This never releases the output tag or output/dependency tokens early.
      if (split_release && feed_ready && result.ready && prior_execute_complete_ &&
          *prior_execute_complete_ <= *feed_ready &&
          *feed_ready < std::numeric_limits<Cycle>::max() && *feed_ready + 1 < *result.ready)
        completion = *feed_ready + 1;
      rs.release(command.ticket, completion);
    }
    if (command.kind.compare(0, 8, "compute_") == 0 && preload_retirement_) {
      reservations_[1]->release(*preload_retirement_, result.ready);
      preload_retirement_.reset();
    }
    if (config_.serialized_execute_epochs && command.group == 2)
      last_store_ready_ = command.config ? issued.ready : result.ready;
    if (command.group == 1) {
      if (!result.ready) prior_execute_complete_.reset();
      else if (prior_execute_complete_)
        prior_execute_complete_ = std::max(*prior_execute_complete_, *result.ready);
    }
    if (config_.ws_resident_mul_pre_pairing &&
        (command.split_ws || (config_.source_bounded_mul_pre_pairing && command.bounded_ws_operands)) &&
        result.start && feed_ready &&
        issued.start && config_.issue_occupancy &&
        *config_.issue_occupancy<=std::numeric_limits<Cycle>::max()-*issued.start)
      pair_feed_=PairFeed{*result.start,*feed_ready,*issued.start+*config_.issue_occupancy,
          last_preload_source_,command.rs1,command.rs2};
    return {command.ticket.admitted, result.start, result.ready, result.unknown};
  }
};
} // namespace gemmini_annotated_spike
#endif
