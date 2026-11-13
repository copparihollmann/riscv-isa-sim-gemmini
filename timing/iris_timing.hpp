#pragma once

#include <cstdint>
#include <functional>
#include <iosfwd>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace iris {
using Cycle = uint64_t;
using NodeId = uint64_t;

// These values are supplied by a calibrated adapter, never inferred as hardware defaults.
struct Op {
  unsigned hart;
  std::string name;
  std::string resource;
  Cycle latency;
  Cycle interval;
  std::vector<NodeId> deps{};
  Cycle earliest = 0;
  std::function<void()> on_complete{};
  bool retires = true;
  uint64_t pc = 0;
  std::string region{};
  uint64_t bytes = 0;
  uint64_t macs = 0;
  Cycle issue_period = 1;
};

struct Node {
  NodeId id;
  Op op;
  bool issued = false;
  bool completed = false;
  Cycle submitted = 0;
  Cycle start = 0;
  Cycle end = 0;
  unsigned lane = 0;
};

// Single global event clock. Functional side effects belong in completion callbacks.
// The Spike adapter must not execute guest shared-memory operations ahead of this clock.
// UINT64_MAX is reserved as the no-event sentinel; reaching it fails closed.
class Machine {
 public:
  Machine(unsigned harts, uint64_t cycles_per_rtc_tick);
  void configure_resource(const std::string& name, unsigned lanes);
  NodeId issue(Op op);
  bool run_next();
  void run_until(Cycle limit);
  void drain();
  std::optional<Cycle> next_event_cycle() const;
  void on_advance(std::function<void(Cycle, Cycle)> callback);
  Cycle now() const { return now_; }
  Cycle mcycle(unsigned hart) const;
  uint64_t minstret(unsigned hart) const;
  uint64_t mtime() const;
  void write_mtime(uint64_t value);
  void set_msip(unsigned hart, bool pending);
  bool msip(unsigned hart) const;
  void write_mtimecmp(unsigned hart, uint64_t value);
  bool mtip(unsigned hart) const;
  // Callback observes line transitions. A parked hart can be resubmitted here.
  void on_interrupt(std::function<void(unsigned, bool, bool)> callback);
  const std::vector<Node>& nodes() const { return nodes_; }
  void write_json(std::ostream& out, bool snapshot = false) const;

 private:
  struct Resource { std::vector<Cycle> next_issue; };
  unsigned harts_;
  uint64_t rtc_divider_;
  Cycle now_ = 0;
  Cycle rtc_origin_ = 0;
  uint64_t rtc_value_ = 0;
  std::map<std::string, Resource> resources_;
  std::vector<Node> nodes_;
  std::set<NodeId> pending_, inflight_;
  std::function<void(Cycle, Cycle)> advance_callback_;
  std::vector<uint64_t> retired_, compares_;
  std::vector<bool> software_irq_;
  std::vector<bool> delivered_timer_irq_;
  std::function<void(unsigned, bool, bool)> interrupt_callback_;
  Cycle next_event() const;
  void check_hart(unsigned hart) const;
  void refresh_interrupts();
};

struct Region {
  std::string name;
  uint64_t base, size;
  bool read, write, execute, atomics;
};

// Sparse backing preserves real holes and avoids allocating a 4-GiB host buffer.
// Reservation granule is an explicit implementation parameter, not a guessed default.
class Memory {
 public:
  Memory(unsigned harts, uint64_t reservation_granule);
  void map(Region region);
  uint64_t load(uint64_t address, unsigned bytes, bool instruction = false) const;
  void store(uint64_t address, unsigned bytes, uint64_t value);
  uint64_t lr(unsigned hart, uint64_t address, unsigned bytes);
  bool sc(unsigned hart, uint64_t address, unsigned bytes, uint64_t value);
  uint64_t amo_add(uint64_t address, unsigned bytes, uint64_t value);
 private:
  struct Reservation { bool valid = false; uint64_t address = 0; unsigned bytes = 0; };
  uint64_t granule_;
  std::vector<Region> regions_;
  std::map<uint64_t, uint8_t> data_;
  std::vector<Reservation> reservations_;
  const Region& check(uint64_t address, unsigned bytes, char mode, bool atomic = false) const;
  void invalidate(uint64_t address, unsigned bytes);
};
}  // namespace iris
