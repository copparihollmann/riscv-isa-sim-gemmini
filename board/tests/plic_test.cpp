#include "iris_plic.hpp"
#include <array>
#include <iostream>
#include <stdexcept>

using iris_board::PlicRegisters;

static void check(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}
template<class F> static void unknown(F action) {
  bool failed = false;
  try { action(); } catch (const std::runtime_error&) { failed = true; }
  check(failed, "unknown PLIC observation did not fail closed");
}
static void write(PlicRegisters& plic, reg_t address, uint32_t value) {
  uint8_t data[4];
  for (unsigned i = 0; i < 4; ++i) data[i] = uint8_t(value >> (i * 8));
  check(plic.store(address, 4, data), "PLIC word write failed");
}
static uint64_t read(PlicRegisters& plic, reg_t address, size_t bytes = 4) {
  uint8_t data[8] = {};
  check(plic.load(address, bytes, data), "PLIC read failed");
  uint64_t value = 0;
  for (unsigned i = 0; i < bytes; ++i) value |= uint64_t(data[i]) << (i * 8);
  return value;
}
static void initialize(PlicRegisters& plic, bool enable_all = true) {
  write(plic, 4, 1);
  for (unsigned c = 0; c < PlicRegisters::contexts; ++c) {
    write(plic, PlicRegisters::enable_base(c), enable_all ? 2 : 0);
    write(plic, PlicRegisters::control_base(c), 0);
  }
}
static void source(PlicRegisters& plic, bool level) {
  plic.set_source_level(level);
  plic.advance_gateway();
}

int main() {
  try {
    {
      PlicRegisters plic;
      check(plic.size() == 0x4000000 && !plic.pending() && !plic.in_flight(), "PLIC reset geometry/state");
      unknown([&] { read(plic, 4); });
      for (unsigned c = 0; c < PlicRegisters::contexts; ++c) {
        unknown([&] { read(plic, PlicRegisters::enable_base(c)); });
        unknown([&] { read(plic, PlicRegisters::control_base(c)); });
        check(plic.irq(c) == false, "known zero pending must dominate unknown registers");
        check(read(plic, PlicRegisters::control_base(c) + 4) == 0, "no pending claim must return zero");
      }
      check(read(plic, 5, 1) == 0, "unused priority upper byte must read zero");
      uint8_t one = 1;
      check(plic.store(5, 1, &one), "upper-byte store failed");
      unknown([&] { read(plic, 4); });
      source(plic, true);
      check(!plic.irq(0).has_value(), "pending with unknown configuration must remain unknown");
      unknown([&] { plic.require_irq(0); });
      unknown([&] { read(plic, PlicRegisters::control_base(0) + 4); });
      write(plic, PlicRegisters::control_base(0) + 4, 0);
      check(plic.in_flight(), "source-zero completion must not depend on unknown enable");
      write(plic, PlicRegisters::enable_base(0), 0);
      check(plic.irq(0) == false && read(plic, PlicRegisters::control_base(0) + 4) == 0,
            "disabled context must mask unknown priority and threshold");
      write(plic, PlicRegisters::control_base(1), 1);
      check(plic.irq(1) == false, "maximum threshold must mask unknown priority and enable");
    }
    {
      PlicRegisters plic;
      initialize(plic);
      plic.set_source_level(true);
      check(!plic.pending(), "source input must not silently clock the gateway");
      plic.advance_gateway();
      check(plic.pending() && plic.in_flight(), "gateway did not latch source");
      source(plic, false);
      check(plic.pending(), "source deassertion must not erase latched pending interrupt");
      for (unsigned c = 0; c < PlicRegisters::contexts; ++c)
        check(plic.require_irq(c), "one source must reach every enabled context");
      // Threshold masks notification, not claim selection, in this actual RTL.
      write(plic, PlicRegisters::control_base(3), 1);
      check(!plic.require_irq(3), "threshold did not mask IRQ");
      check(read(plic, PlicRegisters::control_base(3) + 4) == 1, "claim incorrectly applied threshold");
      check(!plic.pending() && plic.in_flight(), "claim must clear pending while gateway stays in flight");
      for (unsigned c = 0; c < PlicRegisters::contexts; ++c) {
        check(!plic.require_irq(c), "claim failed to clear other contexts' notification");
        check(read(plic, PlicRegisters::control_base(c) + 4) == 0, "source claimed twice");
      }
      // Any enabled context may complete; no claiming-hart ownership restriction.
      write(plic, PlicRegisters::control_base(5) + 4, 3);
      check(!plic.in_flight(), "one-bit completion ID 3 must alias source 1");
      plic.advance_gateway();
      check(!plic.pending(), "deasserted level must not retrigger after completion");
      source(plic, true);
      check(plic.pending(), "new source edge did not trigger after completion");
    }
    {
      PlicRegisters plic;
      initialize(plic);
      source(plic, true);
      write(plic, 4, 0);
      check(!plic.require_irq(0) && read(plic, PlicRegisters::control_base(0) + 4) == 0,
            "priority zero must suppress notification and claim");
      check(plic.pending(), "priority changes must not erase latched pending state");
      write(plic, 4, 1);
      check(plic.require_irq(0) && read(plic, PlicRegisters::control_base(0) + 4) == 1,
            "raising priority of already-pending source must update eligibility");
    }
    {
      PlicRegisters plic;
      initialize(plic);
      source(plic, true);
      check(read(plic, PlicRegisters::control_base(0) + 4) == 1, "first claim failed");
      for (unsigned i = 0; i < 5; ++i) plic.advance_gateway();
      check(!plic.pending(), "high level must wait for completion before retrigger");
      write(plic, PlicRegisters::enable_base(1), 0);
      write(plic, PlicRegisters::control_base(1) + 4, 1);
      check(plic.in_flight(), "disabled context completion must be ignored");
      uint8_t one = 1;
      check(plic.store(PlicRegisters::control_base(0) + 4, 1, &one), "partial completion write failed");
      check(plic.in_flight(), "partial write must not fire the 32-bit completion field");
      write(plic, PlicRegisters::control_base(0) + 4, 2);
      check(plic.in_flight(), "even completion IDs truncate to reserved source zero");
      write(plic, PlicRegisters::control_base(0) + 4, 1);
      check(!plic.in_flight() && !plic.pending(), "completion must not synthesize an immediate pending bit");
      plic.advance_gateway();
      check(plic.pending() && plic.in_flight(), "persistent level did not retrigger after gateway edge");
      // Any byte read of the 32-bit claim field has its side effect, even if
      // the returned high byte is zero.
      check(read(plic, PlicRegisters::control_base(2) + 7, 1) == 0 && !plic.pending(),
            "upper-byte claim read must claim and return that byte");
    }
    {
      PlicRegisters plic;
      write(plic, 4, 1);
      write(plic, PlicRegisters::enable_base(0), 2);
      source(plic, true);
      // Doubleword read spans threshold and claim. Unknown threshold must
      // abort before the otherwise valid claim's side effect.
      unknown([&] { read(plic, PlicRegisters::control_base(0), 8); });
      check(plic.pending(), "failed multi-field read must not partially claim");
      write(plic, PlicRegisters::control_base(0), 0);
      check(read(plic, PlicRegisters::control_base(0), 8) == (1ULL << 32), "threshold/claim doubleword packing");
      // Completion in a combined threshold/claim write depends on enable.
      uint8_t combined[8] = {1, 0, 0, 0, 1, 0, 0, 0};
      unknown([&] { plic.store(PlicRegisters::control_base(1), 8, combined); });
      unknown([&] { read(plic, PlicRegisters::control_base(1)); });
      check(plic.in_flight(), "failed multi-field write partially completed gateway");
    }
    {
      PlicRegisters plic;
      initialize(plic);
      write(plic, 4, 0xfffffffe); check(read(plic, 4) == 0, "priority width must be one bit");
      write(plic, 4, 0xffffffff); check(read(plic, 4) == 1, "priority width clipping");
      write(plic, PlicRegisters::enable_base(0), 0xffffffff);
      check(read(plic, PlicRegisters::enable_base(0)) == 2, "only source 1 enable bit exists");
      write(plic, PlicRegisters::control_base(0), 0xfffffffe);
      check(read(plic, PlicRegisters::control_base(0)) == 0, "threshold width clipping");
      check(read(plic, 0) == 0 && read(plic, 8) == 0, "source 0/absent source register zero behavior");
      check(read(plic, PlicRegisters::aperture - 1, 1) == 0, "64-MiB reserved tail must be mapped zero");
      uint8_t one = 1;
      check(plic.store(PlicRegisters::aperture - 1, 1, &one), "reserved tail write should be ignored");
      check(!plic.load(PlicRegisters::aperture, 1, &one), "out-of-aperture read accepted");
      check(!plic.store(UINT64_MAX - 1, 8, &one), "overflowing MMIO access accepted");
      check(read(plic, PlicRegisters::control_base(6)) == 0, "nonexistent context must read zero");
      unsigned notifications = 0;
      plic.on_interrupt([&](unsigned context, unsigned hart, bool supervisor, PlicRegisters::Line) {
        check(hart == context / 2 && supervisor == bool(context % 2), "M/S context ordering");
        ++notifications;
      });
      check(notifications == 6, "missing context registration callbacks");
      source(plic, true);
      check(notifications == 12, "IRQ transitions not delivered to every context");
      plic.on_interrupt([&](unsigned, unsigned, bool, PlicRegisters::Line) {
        plic.on_interrupt({});
      });
    }
    std::cout << "{\"plic_register_helper\":\"pass\",\"contexts\":6,\"sources\":1,"
                 "\"unknown_register_guards\":true,\"pipeline_timing_certified\":false,\"core_integration\":false}\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
