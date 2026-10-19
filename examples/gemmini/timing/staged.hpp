#ifndef GEMMINI_STAGED_TIMING_V2_HPP
#define GEMMINI_STAGED_TIMING_V2_HPP

#include "provider.hpp"
#include <merlin_timing/reservations.hpp>
#include <memory>

namespace gemmini_annotated_spike {

struct StagedConfig {
  std::array<std::size_t, 3> reservations, controller_entries;
  std::array<std::size_t, 2> dma_commands;
  std::array<ResourceId, 3> issue_resources, controller_resources;
  std::optional<Cycle> issue_latency, issue_occupancy;
  bool require_fenced_phases = false;
};

// Version 2 explicitly distinguishes CPU admission, reservation issue, FIFO
// consumption and final effects. It schedules the actual typed v1-observed row
// and memory effects, not a separate decorative plan. Prices remain external.
class StagedObserver {
public:
  StagedObserver(Engine &engine, StagedConfig config, ValueId execute_configuration,
      std::function<void(const std::string &)> unresolved = {},
      ValueId local_base = 0, std::uint32_t scratchpad_rows = 0, std::uint32_t dim = 0)
      : engine_(engine), config_(config), execute_configuration_(execute_configuration),
        unresolved_(std::move(unresolved)), local_base_(local_base), scratchpad_rows_(scratchpad_rows), dim_(dim) {
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
    if (!config && config_.require_fenced_phases && last_data_group_ && *last_data_group_ != group) {
      missing("staged:cross_controller_phase_without_completion_fence");
      semantic_scope_known_ = false;
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
    if (funct == 6) {
      command->reads.push_back(execute_configuration_);
      if (std::uint32_t(rs1) != 0xffffffffu && scratchpad_rows_) {
        const auto address = std::uint32_t(rs1);
        const auto rows = std::min<std::uint32_t>(rs1 >> 48, dim_);
        if (std::uint64_t(address) + rows > scratchpad_rows_) {
          missing("staged:preload_local_address_outside_selected_store");
          return unknown(source);
        }
        for (std::uint32_t row = 0; row < rows; ++row) command->reads.push_back(local_base_ + address + row);
      }
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
  bool audit_pending_preload_ = false, computed_since_fence_ = false, semantic_scope_known_ = true;
  std::function<void(const std::string &)> unresolved_;
  ValueId local_base_;
  std::uint32_t scratchpad_rows_, dim_;

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
