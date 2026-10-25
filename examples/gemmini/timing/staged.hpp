#ifndef GEMMINI_STAGED_TIMING_V2_HPP
#define GEMMINI_STAGED_TIMING_V2_HPP

#include "provider.hpp"
#include "streamed_readout.hpp"
#include "scratchpad_load.hpp"
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
  // Selected full-WS subset: FIFO pop follows operand consumption. COMPUTE's
  // RS completion can precede its PRELOAD output tag only when the registered
  // completion path is provably idle in the retained conservative schedule.
  bool ws_feed_queue_release = false;
  bool ws_resident_mul_pre_pairing = false;
  std::optional<ReadoutStreamConfig> readout_stream;
  std::optional<ScratchpadLoadConfig> scratchpad_load_stream;
  // Source-bound arrival floor, not controller occupancy or per-row latency.
  Cycle load_frontend_registered_cycles = 0;
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
    if(config_.load_frontend_registered_cycles &&
        (!config_.scratchpad_load_stream || config_.load_frontend_registered_cycles!=6))
      throw std::invalid_argument("unsupported selected row-load frontend pipeline");
    if(config_.scratchpad_load_stream) {
      if(!config_.conservative_local_store_holds || dim_!=16)
        throw std::invalid_argument("scratchpad row loads require selected local resources and DIM16");
      load_stream_=std::make_unique<ScratchpadLoadStream>(*config_.scratchpad_load_stream);
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
    if (funct == 7 || funct == 126) { pair_feed_.reset(); return engine_.submit_detached(source); }
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
      if (!pair_preload(*pending, ticket->admitted, funct, rs1, rs2)) schedule(*pending);
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
    }
    const auto result = schedule(*command);
    if (group == 1 && (funct == 4 || funct == 5)) last_compute_ready_ = result.ready;
    return result;
  }

  bool pending_preload() const { return bool(pending_); }

private:
  using Window = merlin_timing::ReservationWindow;
  struct Preissued { Window::Ticket queue; Result issued; };
  struct Command {
    std::string kind;
    std::vector<ValueId> reads, writes, retained;
    std::vector<Demand> demands;
    std::optional<Cycle> latency, occupancy;
    Window::Ticket ticket;
    std::size_t group;
    bool config;
    bool preload_requires_result = false, split_ws = false, preload_feed_lifetime = false;
    bool split_accumulating_ws = false;
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
  std::array<std::unique_ptr<Window>, 3> reservations_, controllers_;
  std::array<std::unique_ptr<Window>, 2> dma_;
  std::unique_ptr<ScratchpadLoadStream> load_stream_;
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
    const auto result = engine_.submit_detached(event);
    engine_.advance_issue({});
    return result;
  }
  bool pair_preload(Command &command, Cycle third_arrival, std::uint32_t funct,
                    std::uint64_t a, std::uint64_t b) {
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
    const Cycle earliest_issue=std::max({third_arrival,command.ticket.admitted,
        engine_.issue_frontier().value_or(std::numeric_limits<Cycle>::max()),feed.next_issue});
    // A full FIFO at CPU admission does not preclude resident pairing: earlier
    // entries can be consumed before this already-reserved feed starts. Preview
    // both real admission times without changing queue ownership or backdating
    // a command. A later admission is legal only if BOTH issue beats complete
    // before the feed; never delay the feed to manufacture pairing.
    auto preview=*controllers_[1];
    const auto available=preview.allocate(earliest_issue);
    if (!available || available->admitted>feed.start ||
        *config_.issue_occupancy>feed.start-available->admitted) return false;
    const Cycle issue_start=available->admitted;
    const auto third_available=preview.allocate(issue_start+*config_.issue_occupancy);
    if (!third_available || third_available->admitted>feed.start ||
        *config_.issue_latency>feed.start-third_available->admitted ||
        *config_.issue_latency>feed.start-issue_start) return false;
    const Cycle third_issue_start=third_available->admitted;
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
    const auto queue=controllers_[1]->allocate(issue_start);
    const auto third_queue=controllers_[1]->allocate(third_issue_start);
    if (!queue || !third_queue) throw std::logic_error("paired FIFO preview changed without an intervening event");
    const Demand issue_demand{config_.issue_resources[1],1,config_.issue_occupancy};
    Event issued_event{issue_start,{},{},{&issue_demand,1},config_.issue_latency};
    const auto issued=engine_.submit_detached(issued_event);
    if (!issued.ready || *issued.ready>feed.start)
      throw std::logic_error("paired issue timing differs from retained same-controller frontier");
    Event third_issue=issued_event; third_issue.earliest=third_issue_start;
    const auto issued_third=engine_.submit_detached(third_issue);
    if (!issued_third.ready || *issued_third.ready>feed.start)
      throw std::logic_error("third command did not enter FIFO before paired feed start");
    preissued_compute_=Preissued{*third_queue,issued_third};
    // Same weight rows already occupy the compute's SP bank reservation;
    // they are PRELOAD D input while compute consumes A. No extra SRAM port
    // or execute feed is added. Publish only the NEXT descriptor at consumed.
    Event published{feed.consumed,{command.reads.data(),command.reads.size()},
        {command.writes.data(),command.writes.size()},{},Cycle{0},true};
    const auto done=engine_.submit_detached(published);
    if (!done.ready || *done.ready!=feed.consumed)
      throw std::logic_error("paired descriptor changed a retained dependency lifetime");
    controllers_[1]->release(*queue,feed.consumed);
    preload_retirement_=command.ticket; // final result is the following MUL's tag
    return true;
  }
  Result schedule(Command &command) {
    auto &rs = *reservations_[command.group];
    Cycle earliest = command.earliest;
    bool known = true;
    // Arrival through raw/loop passthrough/unrolled/RS/controller registers
    // overlaps CPU work and dependency waits. Do not add these stages after
    // hazard resolution, reserve a controller for them, or repeat per row.
    if(command.transfer_phase && command.transfer_phase->scratchpad_load &&
        config_.load_frontend_registered_cycles) {
      if(earliest>std::numeric_limits<Cycle>::max()-config_.load_frontend_registered_cycles)
        known=false;
      else earliest+=config_.load_frontend_registered_cycles;
    }
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
    const auto issued = command.preissued ? command.preissued->issued : engine_.submit_detached(issue);
    if (command.config && command.subtype != 0) rs.release(command.ticket, issued.ready);

    std::optional<Window::Ticket> dma_ticket;
    std::size_t dma_index = command.group == 2 ? 1 : 0;
    Cycle consume = std::max(issued.ready.value_or(earliest),earliest);
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
          else if (row - scratchpad_rows_ < accumulator_rows_ && !command.split_ws)
            stores.insert(*config_.accumulator_storage_resource);
        }
      const auto hold = command.split_ws ? command.occupancy : command.latency && command.occupancy ?
          std::optional<Cycle>{std::max(*command.latency, *command.occupancy)} : std::nullopt;
      for (const auto store : stores) {
        const bool sp_feed = command.split_accumulating_ws &&
            store != *config_.accumulator_storage_resource;
        command.demands.push_back({store, 1, sp_feed ? command.occupancy : hold});
      }
    }
    Event effect{consume, {command.reads.data(), command.reads.size()},
        {command.writes.data(), command.writes.size()}, {command.demands.data(), command.demands.size()},
        known ? command.latency : std::nullopt, true, {command.retained.data(), command.retained.size()}};
    Result result;
    std::optional<Cycle> feed_ready;
    std::optional<Cycle> load_requests_complete;
    if(command.transfer_phase && command.transfer_phase->scratchpad_load) {
      const auto &phase=*command.transfer_phase;
      const auto count=phase.row_transfers.size();
      if(!load_stream_ || command.group!=0 || command.kind!="load" || !known ||
          !command.latency || !command.occupancy || !phase.row_memory ||
          (phase.row_bytes!=16 && !(config_.scratchpad_load_stream->partial_single_beat_rows &&
              phase.row_bytes && phase.row_bytes<16)) ||
          !count || count>16 || command.writes.size()!=count)
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
      const auto admitted=engine_.submit_detached(admission);
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
        return engine_.submit_detached(transfer);
      },[&](std::size_t row,Cycle at) {
        const ValueId destination=command.writes[row];
        const auto bank=(destination-local_base_)/config_.scratchpad_bank_rows;
        const Demand port{config_.scratchpad_bank_resources.at(bank),1,Cycle{1}};
        Event write{at,{},{&destination,1},{&port,1},Cycle{1}};
        return engine_.submit_detached(write);
      },phase.row_bytes<16);
      if(!streamed.complete || !streamed.requests_complete ||
          *command.latency>std::numeric_limits<Cycle>::max()-*admitted.start) return unknown(effect);
      auto controller=command.demands;
      for(auto &d:controller)d.occupancy=std::max(*d.occupancy,*streamed.requests_complete-*admitted.start);
      Event request_hold{*admitted.start,{},{},{controller.data(),controller.size()},Cycle{0}};
      const auto held=engine_.submit_detached(request_hold);
      if(held.start!=admitted.start)return unknown(effect);
      Event publish=effect;publish.earliest=std::max(*streamed.complete,*admitted.start+*command.latency);
      publish.demands={};publish.latency=0;
      const auto done=engine_.submit_detached(publish);
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
      const auto admitted=engine_.submit_detached(admission);
      if(!admitted.start)return unknown(effect);
      const auto streamed=stream_readout(*config_.readout_stream,row_count,phase.row_bytes,
          *admitted.start,[&](std::size_t row,Cycle at,Cycle beats) {
        observed_rows.push_back(phase.row_transfers.empty()?phase.rows[row]:
            phase.row_memory({&phase.row_transfers[row],1}));
        const auto &memory=observed_rows.back();
        for(const auto &d:memory.demands) for(const auto &local:command.demands)
          if(d.resource==local.resource)return Result{};
        // Accepted A requests may queue before the private probe controller.
        // Delay its service, not A admission or its transaction-credit release.
        Cycle service_at=at;
        if(config_.readout_stream->private_probe_resource &&
            std::any_of(memory.demands.begin(),memory.demands.end(),[&](const auto &d) {
              return d.resource==*config_.readout_stream->private_probe_resource;
            })) {
          if(config_.readout_stream->probe_request_cycles>std::numeric_limits<Cycle>::max()-at)
            return Result{};
          service_at+=config_.readout_stream->probe_request_cycles;
        }
        Event transfer{service_at,{memory.reads.data(),memory.reads.size()},
            {memory.writes.data(),memory.writes.size()},
            {memory.demands.data(),memory.demands.size()},
            memory.minimum_latency ? std::optional<Cycle>{std::max(beats,*memory.minimum_latency)} : std::nullopt,true};
        return engine_.submit_detached(transfer);
      });
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
      const auto finished=engine_.submit_detached(finish);
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
      const auto published=engine_.submit_detached(publish);
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
      const auto produced = engine_.submit_detached(producer);
      Event consumer = effect;
      consumer.earliest = produced.ready.value_or(consume);
      consumer.demands = {consumer_demands.data(), consumer_demands.size()};
      consumer.latency = produced.ready ? std::optional<Cycle>{*command.latency-phase.arrival} : std::nullopt;
      const auto completed = engine_.submit_detached(consumer);
      result = {produced.issue, produced.start, completed.ready, completed.unknown};
    } else if (command.split_accumulating_ws) {
      // ExecuteController ends SP reads at about_to_fire_all_rows. Accumulator
      // RMW is a later mesh-response write; keep its old conservative resource
      // hold and every non-SP dependency/result at the original completion.
      // No earlier RS/FIFO release or MUL/PRE pairing is enabled here.
      Event input = effect; input.writes = {}; input.latency = command.occupancy;
      const auto fed = engine_.submit_detached(input);
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
      const auto published = engine_.submit_detached(completed);
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
      const auto fed = engine_.submit_detached(input);
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
      const auto written = engine_.submit_detached(output);
      result = {fed.issue, fed.start, written.ready, written.unknown};
    } else {
      result = engine_.submit_detached(effect);
      if (command.kind.compare(0, 8, "compute_") == 0) last_compute_feed_ready_.reset();
    }
    const bool split_release = config_.ws_feed_queue_release && command.split_ws;
    // ExecuteController pops single MUL only at about_to_fire_all_rows, not
    // when it starts consuming its FIFO entry. Other subsets retain legacy.
    auto fifo_release=load_requests_complete ? load_requests_complete : split_release ? feed_ready : result.start;
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
        engine_.submit_detached(unresolved);
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
    if (config_.ws_resident_mul_pre_pairing && command.split_ws && result.start && feed_ready &&
        issued.start && config_.issue_occupancy &&
        *config_.issue_occupancy<=std::numeric_limits<Cycle>::max()-*issued.start)
      pair_feed_=PairFeed{*result.start,*feed_ready,*issued.start+*config_.issue_occupancy,
          last_preload_source_,command.rs1,command.rs2};
    return {command.ticket.admitted, result.start, result.ready, result.unknown};
  }
};
} // namespace gemmini_annotated_spike
#endif
