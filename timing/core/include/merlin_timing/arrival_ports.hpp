#ifndef MERLIN_TIMING_ARRIVAL_PORTS_HPP
#define MERLIN_TIMING_ARRIVAL_PORTS_HPP

#include "engine.hpp"
#include <map>
#include <set>
#include <string>

namespace merlin_timing {

// Bounded offline acceptance planner for ready/valid FIFO sources sharing ports.
// Arrivals are selected post-pipeline ready times, not request timestamps or an
// aggregate latency divided by rows. Each port accepts at most one item/cycle.
// Callers supply source priority, fixed port mapping, exact dependency edges,
// and occupied intervals from other users. No hardware policy or price is inferred.
struct PortArrival {
  std::uint64_t id;
  std::size_t source, port;
  std::optional<Cycle> ready;
  std::vector<std::uint64_t> dependencies;
};
struct PortBusyInterval { std::size_t port; Cycle begin, end; };
struct PortAcceptance {
  std::uint64_t id;
  Cycle accepted, released;
  std::size_t source, port;
};
struct ArrivalPortPlan {
  bool complete = false;
  std::string unresolved;
  std::vector<PortAcceptance> accepted;
};

inline ArrivalPortPlan plan_arrival_ports(
    std::size_t ports, const std::vector<std::size_t> &source_priority,
    const std::vector<PortArrival> &rows, const std::vector<PortBusyInterval> &busy = {}) {
  constexpr std::size_t max_ports = 128, max_rows = 4096, max_sources = 256, max_busy = 4096;
  ArrivalPortPlan plan;
  const auto unknown = [&](const char *reason) {
    plan.complete = false; plan.unresolved = reason; return plan;
  };
  if (!ports || ports > max_ports || source_priority.empty() || source_priority.size() > max_sources ||
      rows.size() > max_rows || busy.size() > max_busy)
    return unknown("arrival/port/source/interval bound exceeded");
  std::map<std::uint64_t, std::size_t> ids;
  std::vector<std::vector<std::size_t>> queues(source_priority.size());
  std::vector<std::size_t> heads(source_priority.size(), 0);
  std::size_t total_dependencies = 0;
  for (std::size_t i = 0; i < rows.size(); ++i) {
    const auto &r = rows[i];
    if (!r.ready) return unknown("response arrival is unknown");
    if (r.port >= ports || r.source >= queues.size() || !ids.emplace(r.id, i).second ||
        r.dependencies.size() > max_rows)
      return unknown("invalid or duplicate row/source/port identity");
    total_dependencies += r.dependencies.size();
    if (total_dependencies > 16384) return unknown("dependency budget exceeded");
    queues[r.source].push_back(i);
  }
  for (const auto &r : rows)
    for (const auto dependency : r.dependencies)
      if (dependency == r.id || !ids.count(dependency)) return unknown("unbound dependency");
  std::vector<std::vector<PortBusyInterval>> intervals(ports);
  for (const auto &b : busy) {
    if (b.port >= ports || b.begin >= b.end) return unknown("invalid occupied interval");
    intervals[b.port].push_back(b);
  }
  for (auto &v : intervals)
    std::sort(v.begin(), v.end(), [](const auto &a, const auto &b) { return a.begin < b.begin; });
  std::vector<std::size_t> sources(source_priority.size());
  for (std::size_t i = 0; i < sources.size(); ++i) sources[i] = i;
  std::stable_sort(sources.begin(), sources.end(), [&](auto a, auto b) { return source_priority[a] < source_priority[b]; });
  // A tie requires an explicit arbiter; don't invent round-robin or source order.
  for (std::size_t i = 1; i < sources.size(); ++i)
    if (source_priority[sources[i-1]] == source_priority[sources[i]]) return unknown("ambiguous source priority");
  std::map<std::uint64_t, Cycle> released;
  std::vector<Cycle> port_free(ports, 0), source_free(source_priority.size(), 0);
  const auto available = [&](std::size_t port, Cycle at) {
    at = std::max(at, port_free[port]);
    for (const auto &b : intervals[port]) {
      if (at < b.begin) break;
      if (at < b.end) at = b.end;
    }
    return at;
  };
  Cycle now = 0;
  while (plan.accepted.size() < rows.size()) {
    std::optional<Cycle> next;
    std::vector<std::pair<std::size_t, Cycle>> candidates;
    for (const auto source : sources) {
      if (heads[source] == queues[source].size()) continue;
      const auto &r = rows[queues[source][heads[source]]];
      Cycle at = std::max({now, *r.ready, source_free[source]});
      bool bound = true;
      for (const auto dependency : r.dependencies) {
        const auto found = released.find(dependency);
        if (found == released.end()) { bound = false; break; }
        at = std::max(at, found->second);
      }
      if (!bound) continue;
      at = available(r.port, at);
      next = next ? std::min(*next, at) : at;
      candidates.emplace_back(source, at);
    }
    if (!next) return unknown("FIFO/dependency deadlock or absent predecessor completion");
    now = *next;
    if (now == std::numeric_limits<Cycle>::max()) return unknown("port completion overflow");
    bool progress = false;
    for (const auto &[source, at] : candidates) {
      if (at > now) continue;
      const auto &r = rows[queues[source][heads[source]]];
      if (available(r.port, now) > now) continue;
      plan.accepted.push_back({r.id, now, now+1, source, r.port});
      released.emplace(r.id, now+1); port_free[r.port] = now+1; source_free[source] = now+1; ++heads[source]; progress = true;
    }
    if (!progress) return unknown("unresolved port arbitration");
  }
  plan.complete = true;
  return plan;
}
} // namespace merlin_timing
#endif
