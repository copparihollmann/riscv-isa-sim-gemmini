#include "iris_timing.hpp"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>

using namespace iris;
void require(bool value) { if (!value) throw std::runtime_error("test assertion failed"); }
template <class F> void fault(F f) {
  try { f(); } catch (const std::exception&) { return; }
  throw std::runtime_error("expected fault missing");
}
int main(int argc, char**) {
  Machine m(3, 10);  // Test fixture values, not Iris calibration.
  Memory mem(3, 64);
  mem.map({"shared", 0x80000000, 4096, true, true, true, true});
  mem.map({"scratch", 0x580000000, 128, true, true, false, false});
  fault([&] { mem.load(0, 8); });
  fault([&] { mem.store(0x80000fff, 8, 1); });
  fault([&] { mem.amo_add(0x580000000, 4, 1); });
  fault([&] { mem.load(0x580000000, 4, true); });
  mem.store(0x80000000, 8, 1);
  require(mem.lr(0, 0x80000000, 8) == 1);
  mem.store(0x80000008, 8, 2);  // Another hart writing same reservation granule.
  require(!mem.sc(0, 0x80000000, 8, 3));
  mem.lr(0, 0x80000000, 8);
  require(mem.sc(0, 0x80000000, 8, 3));
  require(!mem.sc(0, 0x80000000, 8, 4));
  require(mem.amo_add(0x80000000, 8, 2) == 3);
  require(mem.load(0x80000000, 8) == 5);
  m.configure_resource("scalar0", 2);
  m.configure_resource("scalar1", 2);
  m.configure_resource("serial", 1);
  m.configure_resource("vme0", 1);
  uint64_t observed = 0;
  auto store = m.issue({0, "store", "serial", 8, 4, {}, 0,
                       [&] { mem.store(0x80000000, 8, 11); }});
  auto load = m.issue({1, "load", "serial", 3, 4, {store}, 0,
                      [&] { observed = mem.load(0x80000000, 8); }});
  m.issue({0, "vme", "vme0", 20, 2, {}, 0, {}});
  // A future job must not reserve the resource ahead of a ready job.
  auto future = m.issue({2, "future", "serial", 1, 1, {}, 100, {}});
  auto ready = m.issue({1, "ready", "serial", 1, 1, {}, 0, {}});
  m.write_mtimecmp(1, 2);
  m.run_until(7);
  require(observed == 0 && m.minstret(0) == 0);
  fault([&] { std::ostringstream partial; m.write_json(partial); });
  m.run_until(11);
  require(observed == 11 && m.minstret(1) == 2);
  require(m.nodes()[load].start == 8 && m.nodes()[ready].start == 4);
  require(!m.mtip(1));
  m.run_until(20);
  require(m.mtip(1) && m.mcycle(2) == 20 && m.minstret(0) == 2);
  m.set_msip(2, true); require(m.msip(2));
  m.set_msip(2, false); require(!m.msip(2));
  m.write_mtime(5); m.run_until(30); require(m.mtime() == 6);
  m.drain(); require(m.nodes()[future].start == 100);
  // Submit a dependent operation from a completion callback (online adapter path).
  m.issue({0, "callback", "scalar0", 1, 1, {}, m.now(), [&] {
    m.issue({1, "wakeup", "scalar1", 1, 1, {}, m.now(), [&] { m.set_msip(1, true); }});
  }});
  m.drain(); require(m.msip(1) && m.now() == 103);
  fault([&] { m.issue({3, "bad", "scalar0", 1, 1}); });
  fault([&] { m.issue({0, "bad", "unknown", 1, 1}); });
  fault([&] { m.issue({0, "bad", "scalar0", 1, 1, {999}}); });
  fault([&] { m.issue({0, "bad", "scalar0", 1, 1, {}, std::numeric_limits<Cycle>::max()}); });
  // No instruction is runnable: the next timer edge must still wake the guest.
  Machine asleep(3, 10);
  bool woke = false;
  asleep.on_interrupt([&](unsigned hart, bool, bool timer) {
    if (hart == 1 && timer) {
      woke = true;
      asleep.write_mtimecmp(1, 9);  // Handler can reprogram the timer online.
    }
  });
  asleep.write_mtimecmp(1, 3);
  asleep.run_until(29); require(!woke);
  asleep.run_until(30); require(woke && !asleep.mtip(1));
  require(asleep.mcycle(0) == 30 && asleep.minstret(0) == 0);
  // Unsigned mtime wrap is an observable timer edge even with no runnable hart.
  Machine wrapping(1, 10);
  auto max = std::numeric_limits<uint64_t>::max();
  std::vector<bool> timer_edges;
  wrapping.write_mtime(max - 1);
  wrapping.write_mtimecmp(0, max);
  wrapping.on_interrupt([&](unsigned, bool, bool timer) { timer_edges.push_back(timer); });
  wrapping.run_until(9); require(!wrapping.mtip(0));
  wrapping.run_until(10); require(wrapping.mtip(0));
  wrapping.run_until(20); require(!wrapping.mtip(0));
  require(timer_edges == std::vector<bool>({false, true, false}));
  // Removing a callback from inside itself must neither destroy an executing
  // callable nor invoke an empty callback for the remaining harts.
  Machine detach(3, 10);
  unsigned notifications = 0;
  detach.on_interrupt([&](unsigned, bool, bool) {
    ++notifications;
    detach.on_interrupt({});
  });
  require(notifications == 1);
  // A valid timer edge at a nonzero sub-tick phase retains its exact deadline.
  Machine phase(1, 10);
  bool phase_woke = false;
  phase.on_interrupt([&](unsigned, bool, bool timer) { phase_woke |= timer; });
  phase.run_until(7);
  phase.write_mtimecmp(0, 2);
  phase.run_until(19); require(!phase_woke);
  phase.run_until(20); require(phase_woke);
  Machine counter_write(1, 10);
  counter_write.run_until(7);
  counter_write.write_mtime(42);
  counter_write.run_until(9); require(counter_write.mtime() == 42);
  counter_write.run_until(10); require(counter_write.mtime() == 43);
  Machine clocks(2, 100);
  clocks.configure_resource("shared", 1);
  clocks.run_until(1);
  Op slow{1, "clock-domain", "shared", 3, 1}; slow.issue_period = 4;
  auto domain_node = clocks.issue(slow);
  std::vector<Cycle> advances;
  clocks.on_advance([&](Cycle, Cycle to) { advances.push_back(to); });
  clocks.drain();
  require(clocks.nodes()[domain_node].start == 4 && clocks.now() == 8);
  require(advances == std::vector<Cycle>({4, 8}));
  Machine snapshot(1, 10);
  snapshot.configure_resource("unit", 1);
  snapshot.issue({0, "inflight", "unit", 10, 1}); snapshot.run_until(4);
  std::ostringstream prefix; snapshot.write_json(prefix, true);
  require(prefix.str().find("\"completed\":false") != std::string::npos);
  require(prefix.str().find("\"end\":4") != std::string::npos);
  // Do not silently lose a completion that collides with the no-event marker.
  Machine horizon(1, 1);
  horizon.configure_resource("unit", 1);
  horizon.run_until(max - 2);
  horizon.issue({0, "overflow", "unit", 2, 1});
  fault([&] { horizon.run_next(); });
  fault([&] { horizon.run_until(max); });
  if (argc > 1) m.write_json(std::cout);
  else std::cout << "online timing, shared memory, reservations, IRQ tests passed\n";
}
