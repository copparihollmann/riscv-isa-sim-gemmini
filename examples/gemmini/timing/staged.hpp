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
};

// Version 2 explicitly distinguishes CPU admission, reservation issue, FIFO
// consumption and final effects. It schedules the actual typed v1-observed row
// and memory effects, not a separate decorative plan. Prices remain external.
class StagedObserver {
public:
  StagedObserver(Engine &engine, StagedConfig config, ValueId execute_configuration)
      : engine_(engine), config_(config), execute_configuration_(execute_configuration) {
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
    auto ticket = reservations_[group]->allocate(source.earliest);
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
    if (!command.config || command.subtype == 0) rs.release(command.ticket, result.ready);
    return {command.ticket.admitted, result.start, result.ready, result.unknown};
  }
};
} // namespace gemmini_annotated_spike
#endif
