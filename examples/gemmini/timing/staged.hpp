#ifndef GEMMINI_STAGED_TIMING_V2_HPP
#define GEMMINI_STAGED_TIMING_V2_HPP

#include "provider.hpp"
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
};

// Exact cross-controller RS completion ancestry, independent of event prices.
// Same-LD/EX arrival order proves issue order only. Same-ST entries, however,
// retain their dependencies until completion in the selected source.
class DependencyPhases {
public:
  using Ids = std::set<std::uint64_t>;
  using Rows = std::set<ValueId>;
  bool observe(std::size_t group, const Rows &reads, const Rows &writes,
               bool preload = false, bool compute = false, bool execute_config = false) {
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
    for (const auto &entry : nodes_)
      if (entry.second.group != group && !ancestors.count(entry.first)) ordered = false;
    const auto identity = ++sequence_;
    nodes_.emplace(identity, Node{group, reads, writes, dependencies});
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
  struct Node { std::size_t group; Rows reads, writes; Ids parents; };
  std::map<std::uint64_t, Node> nodes_;
  Ids execute_drain_;
  std::uint64_t sequence_ = 0;
  std::optional<std::uint64_t> last_preload_;
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
        unresolved_(std::move(unresolved)), local_base_(local_base), scratchpad_rows_(scratchpad_rows), dim_(dim), accumulator_rows_(accumulator_rows) {
    for (std::size_t i = 0; i < 3; ++i) {
      reservations_[i] = std::make_unique<merlin_timing::ReservationWindow>(config.reservations[i]);
      controllers_[i] = std::make_unique<merlin_timing::ReservationWindow>(config.controller_entries[i]);
    }
    for (std::size_t i = 0; i < 2; ++i)
      dma_[i] = std::make_unique<merlin_timing::ReservationWindow>(config.dma_commands[i]);
  }

  Result submit(const std::string &kind, const Event &source, std::optional<Cycle> occupancy,
                std::uint32_t funct, std::uint64_t rs1, std::uint64_t rs2) {
    if (kind == "fence") {
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
    if (funct == 7 || funct == 126) return engine_.submit_detached(source);
    const bool config = funct == 0;
    const auto subtype = config ? rs1 & 3 : 0;
    const std::size_t group = config ? (subtype == 1 ? 0 : subtype >= 2 ? 2 : 1) :
        (funct == 1 || funct == 2 || funct == 14) ? 0 : funct == 3 ? 2 : 1;
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
    const bool dependency_ordered = config ? (subtype != 0 || phases_.observe(group, {}, {}, false, false, true)) :
        phases_.observe(group, rs_reads, rs_writes, funct == 6, funct == 4 || funct == 5);
    // Audit actual command order independently of priced Engine progress. An
    // unpriced first event must not hide unsupported later commands.
    if (config_.require_fenced_phases && group == 1) {
      if (audit_pending_preload_ && funct != 4 && funct != 5) {
        missing("staged:preload_followed_by_noncompute_not_admitted");
        semantic_scope_known_ = false;
      }
      if (funct == 6) {
        if (computed_since_fence_) {
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
      if (!config_.allow_dependency_ordered_phases || !dependency_ordered) {
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
      schedule(*pending);
    }
    auto command = std::make_unique<Command>(kind, source, occupancy, *ticket, group, config, subtype);
    command->earliest = ticket->admitted;
    command->reads.insert(command->reads.end(), extra_reads.begin(), extra_reads.end());
    if (funct == 6) {
      command->preload_requires_result = std::uint32_t(rs2) != 0xffffffffu;
      pending_ = std::move(command);
      return {ticket->admitted, ticket->admitted, ticket->admitted, merlin_timing::UnknownReason::none};
    }
    (void)rs2;
    return schedule(*command);
  }

  bool pending_preload() const { return bool(pending_); }

private:
  using Window = merlin_timing::ReservationWindow;
  struct Command {
    std::string kind;
    std::vector<ValueId> reads, writes, retained;
    std::vector<Demand> demands;
    std::optional<Cycle> latency, occupancy;
    Window::Ticket ticket;
    std::size_t group;
    bool config;
    bool preload_requires_result = false;
    std::uint64_t subtype;
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
  std::unique_ptr<Command> pending_;
  std::optional<Window::Ticket> preload_retirement_;
  std::optional<std::size_t> last_data_group_;
  DependencyPhases phases_;
  bool audit_pending_preload_ = false, computed_since_fence_ = false, semantic_scope_known_ = true;
  std::function<void(const std::string &)> unresolved_;
  ValueId local_base_;
  std::uint32_t scratchpad_rows_, dim_, accumulator_rows_;
  std::uint32_t a_stride_ = 0, c_stride_ = 0;
  bool a_transpose_ = false;

  void missing(const std::string &reason) { if (unresolved_) unresolved_(reason); }

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
  Result schedule(Command &command) {
    auto &rs = *reservations_[command.group];
    Cycle earliest = command.earliest;
    bool known = true;
    for (const auto value : command.reads) known = extend(earliest, engine_.ready(value)) && known;
    for (const auto value : command.writes) known = extend(earliest, engine_.last_use(value)) && known;
    if (command.config && command.subtype == 0)
      known = extend(earliest, rs.drained(earliest, command.ticket)) && known;
    auto queue = controllers_[command.group]->allocate(earliest);
    known = bool(queue) && known;
    if (queue) earliest = std::max(earliest, queue->admitted);
    const Demand issue_demand{config_.issue_resources[command.group], 1, config_.issue_occupancy};
    Event issue{earliest, {}, {}, {&issue_demand, 1}, known ? config_.issue_latency : std::nullopt};
    const auto issued = engine_.submit_detached(issue);
    if (command.config && command.subtype != 0) rs.release(command.ticket, issued.ready);

    std::optional<Window::Ticket> dma_ticket;
    std::size_t dma_index = command.group == 2 ? 1 : 0;
    Cycle consume = issued.ready.value_or(earliest);
    known = bool(issued.ready) && known;
    if (!command.config && command.group != 1) {
      dma_ticket = dma_[dma_index]->allocate(consume);
      known = bool(dma_ticket) && known;
      if (dma_ticket) consume = std::max(consume, dma_ticket->admitted);
    }
    command.demands.push_back({config_.controller_resources[command.group], 1, command.occupancy});
    Event effect{consume, {command.reads.data(), command.reads.size()},
        {command.writes.data(), command.writes.size()}, {command.demands.data(), command.demands.size()},
        known ? command.latency : std::nullopt, true, {command.retained.data(), command.retained.size()}};
    const auto result = engine_.submit_detached(effect);
    if (queue) controllers_[command.group]->release(*queue, result.start);
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
    } else if (!command.config || command.subtype == 0) rs.release(command.ticket, result.ready);
    if (command.kind.compare(0, 8, "compute_") == 0 && preload_retirement_) {
      reservations_[1]->release(*preload_retirement_, result.ready);
      preload_retirement_.reset();
    }
    return {command.ticket.admitted, result.start, result.ready, result.unknown};
  }
};
} // namespace gemmini_annotated_spike
#endif
