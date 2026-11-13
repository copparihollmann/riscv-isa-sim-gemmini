#include "iris_boot.hpp"
#include "iris_clint.hpp"
#include "physical_map.hpp"
#include "processor.h"
#include "simif.h"
#include "mmu.h"
#include "devices.h"
#include "encoding.h"
#include <array>
#include <cstring>
#include <dlfcn.h>
#include <iostream>
#include <memory>
#include <sstream>

using namespace iris_board;

static void check(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}

struct Fixture : simif_t {
  cfg_t cfg;
  std::map<size_t, processor_t*> harts;
  std::vector<std::unique_ptr<processor_t>> procs;
  BootAddressRegister address;
  ReadOnlyBootROM rom;
  std::unique_ptr<clint_t> clint;
  alignas(4096) std::array<char, 0x2000> ram{};
  Fixture(const std::vector<char>& prefix, const std::vector<char>& dtb)
      : rom(prefix, dtb) {
    cfg.isa = "rv64imac_zicsr_zifencei";
    cfg.priv = "MSU";
    cfg.hartids = {0, 1, 2};
    for (unsigned h = 0; h < 3; ++h) {
      auto proc = std::make_unique<processor_t>(cfg.isa, cfg.priv, &cfg, this, h,
                                               false, nullptr, std::cerr);
      proc->get_state()->pc = reset_pc;  // Proposed core hook, not installed globally.
      harts[h] = proc.get();
      procs.push_back(std::move(proc));
    }
    clint = std::make_unique<clint_t>(this, mtime_hz, false);
  }
  char* addr_to_mem(reg_t addr) override {
    return addr >= 0x80000000 && addr < 0x80002000 ? ram.data() + addr - 0x80000000 : nullptr;
  }
  bool mmio_load(reg_t addr, size_t bytes, uint8_t* data) override {
    if (addr >= rom_base && addr < rom_base + rom_size) return rom.load(addr - rom_base, bytes, data);
    if (addr >= bootreg_base && addr < bootreg_base + address.size()) return address.load(addr - bootreg_base, bytes, data);
    if (addr >= clint_base && addr < clint_base + clint->size()) return clint->load(addr - clint_base, bytes, data);
    return false;
  }
  bool mmio_store(reg_t addr, size_t bytes, const uint8_t* data) override {
    if (addr >= bootreg_base && addr < bootreg_base + address.size()) return address.store(addr - bootreg_base, bytes, data);
    if (addr >= clint_base && addr < clint_base + clint->size()) return clint->store(addr - clint_base, bytes, data);
    return false;
  }
  void proc_reset(unsigned) override {}
  const cfg_t& get_cfg() const override { return cfg; }
  const std::map<size_t, processor_t*>& get_harts() const override { return harts; }
  const char* get_symbol(uint64_t) override { return nullptr; }
  void release(uint64_t entry) {
    uint8_t raw[8];
    for (unsigned i = 0; i < 8; ++i) raw[i] = uint8_t(entry >> (8 * i));
    check(address.store(0, 8, raw), "boot entry write failed");
    const uint8_t msip[4] = {1, 0, 0, 0};
    check(clint->store(0, 4, msip), "hart0 release failed");
  }
};

static void boot_case(const std::vector<char>& prefix, const std::vector<char>& dtb,
                      bool release_early, const std::array<unsigned, 3>& order) {
  Fixture fixture(prefix, dtb);
  constexpr uint64_t entry = 0x80001000;
  if (release_early) fixture.release(entry);
  else {
    for (unsigned round = 0; round < 30; ++round)
      for (auto h : order) fixture.procs[h]->step(1);
    for (const auto& proc : fixture.procs) {
      const auto* state = proc->get_state();
      check(state->pc == 0x10034 || state->pc == 0x10038, "hart did not park in physical boot ROM");
      check((state->mtvec->read() & ~3ULL) == 0x10040, "boot trap vector mismatch");
      check(state->mie->read() == MIP_MSIP, "ROM must enable only software interrupts");
    }
    fixture.release(entry);
  }
  std::array<bool, 3> reached{};
  for (unsigned round = 0; round < 300; ++round) {
    for (auto h : order) {
      if (!reached[h]) fixture.procs[h]->step(1);
      reached[h] = fixture.procs[h]->get_state()->pc == entry;
    }
    if (reached[0] && reached[1] && reached[2]) break;
  }
  for (unsigned h = 0; h < 3; ++h) {
    check(reached[h], "physical three-hart boot did not reach loader entry");
    const auto* state = fixture.procs[h]->get_state();
    check(state->XPR[10] == h, "a0 must contain architectural hart id");
    check(state->XPR[11] == rom_base + dtb_offset, "a1 must point to appended DTB");
    check((state->mip->read() & MIP_MSIP) == 0, "ROM did not clear per-hart MSIP");
    check((state->mstatus->read() & MSTATUS_MIE) == 0, "mret must leave global interrupts disabled");
    check(state->prv == PRV_M, "boot must enter program in machine mode");
    check(fixture.procs[h]->get_mmu()->load<uint32_t>(rom_base + dtb_offset) == 0xedfe0dd0,
          "guest cannot read appended DTB magic");
  }
  uint8_t raw[4] = {};
  check(fixture.clint->load(12, 4, raw) && raw[0] == 0,
        "nonexistent hart MSIP must read zero, terminating hart0 probe loop");
}

int main(int argc, char** argv) {
  try {
    if (argc != 4) throw std::runtime_error("boot_test requires ROM prefix, Iris DTB and plugin paths");
    const auto prefix = read_binary(argv[1]);
    const auto dtb = read_binary(argv[2]);
    check(dtb.size() > 40 && uint8_t(dtb[0]) == 0xd0 && uint8_t(dtb[1]) == 0x0d,
          "Iris DTB fixture is invalid");
    if (!dlopen(argv[3], RTLD_NOW | RTLD_GLOBAL)) throw std::runtime_error(dlerror());
    auto& plugins = mmio_device_map();
    check(plugins.count("iris_bootreg") && plugins.count("iris_bootrom"), "board plugin registration missing");
    reg_t device_base = 0;
    std::unique_ptr<abstract_device_t> plugin_rom(plugins.at("iris_bootrom")->parse_from_fdt(
        dtb.data(), nullptr, &device_base, {argv[1], argv[2]}));
    check(plugin_rom && device_base == rom_base, "ROM plugin DTB binding failed");
    std::unique_ptr<abstract_device_t> plugin_address(plugins.at("iris_bootreg")->parse_from_fdt(
        dtb.data(), nullptr, &device_base, {"0x80001000"}));
    check(plugin_address && device_base == bootreg_base, "boot-address plugin DTB binding failed");
    auto different_dtb = dtb;
    different_dtb[31] ^= 1; // Valid header boot_cpuid_phys change; structure remains intact.
    bool dtb_mismatch = false;
    try {
      std::unique_ptr<abstract_device_t> wrong(plugins.at("iris_bootrom")->parse_from_fdt(
          different_dtb.data(), nullptr, &device_base, {argv[1], argv[2]}));
    } catch (const std::invalid_argument&) { dtb_mismatch = true; }
    check(dtb_mismatch, "ROM plugin must reject an appended DTB differing from active DTB");
    BootAddressRegister reg;
    uint8_t raw[8] = {};
    check(reg.load(0, 8, raw) && raw[3] == 0x80, "default DRAM boot address");
    const uint8_t high[4] = {0x44, 0x33, 0x22, 0x11};
    check(reg.store(4, 4, high) && reg.value() == 0x1122334480000000,
          "partial boot register writes must preserve other bytes");
    check(reg.load(0xff8, 8, raw), "unimplemented boot register page reads must complete");
    for (auto byte : raw) check(byte == 0, "unimplemented boot register bits must read zero");
    check(!reg.store(0xffc, 8, raw), "cross-boundary boot register write accepted");
    ReadOnlyBootROM rom(prefix, dtb);
    check(rom.load(rom_size - 8, 8, raw), "ROM aperture tail read failed");
    for (auto byte : raw) check(byte == 0, "ROM tail must zero-fill");
    check(!rom.store(0, 4, raw), "ROM store must fault");
    check(!rom.load(rom_size - 1, 8, raw), "ROM load crossed physical aperture");
    check(permits(0x80000000, 8, Access::Atomic), "DRAM atomic permission");
    check(permits(0x580000000ULL, 8, Access::Execute), "scratchpad executable permission");
    check(!permits(0x580000000ULL, 8, Access::Atomic), "scratchpad atomics must be denied");
    check(!permits(rom_base, 4, Access::Write), "ROM PMA must deny writes");
    check(!permits(0x10020000, 4, Access::Execute), "UART PMA must deny instruction fetch");
    check(!permits(0x70040000, 4, Access::Read), "hole after TCM must fault");
    check(!permits(UINT64_MAX - 1, 8, Access::Read), "overflowing access must fault");
    check(permits(0x17ffffff8ULL, 8, Access::Read), "full 4-GiB DRAM last word missing");
    check(permits(0x17ffffff8ULL, 8, Access::Write), "DRAM end write permission");
    check(!permits(0x180000000ULL, 8, Access::Read), "memory beyond real DRAM must fault");
    check(!permits(0x17ffffffcULL, 8, Access::Read), "access may not overrun DRAM end");
    check(permits(0x7001fff8, 8, Access::Atomic), "hart0 TCM last word atomic permission");
    check(permits(0x70020000, 8, Access::Atomic), "hart1 TCM base atomic permission");
    check(!permits(0x6ffffff8, 8, Access::Read), "hole immediately before TCM must fault");
    check(permits(0x58001fff8ULL, 8, Access::Write), "scratchpad last word missing");
    check(!permits(0x580020000ULL, 8, Access::Read), "scratchpad must not grow beyond 128 KiB");
    check(!permits(0x58001fff8ULL, 8, Access::Atomic), "scratchpad last word must deny atomics");
    check(permits(0xfffffff, 1, Access::Read), "Iris PLIC full 64-MiB aperture missing");
    check(!permits(0x10000000, 4, Access::Read), "post-PLIC hole must remain unmapped");
    check(!permits(0x2000000, 4, Access::Execute), "CLINT must deny instruction fetch");
    check(!permits(bootreg_base, 4, Access::Execute), "boot address register must deny instruction fetch");
    check(!permits(rom_base, 8, Access::Atomic), "readonly ROM must deny atomics");
    TimerRegisters timer;
    check(timer.mtime() == 0 && !timer.msip(0) && !timer.mtip(0).has_value(),
          "CLINT reset state must preserve unknown mtimecmp");
    bool unknown_read = false;
    try { timer.load(0x4008, 8, raw); }
    catch (const std::runtime_error&) { unknown_read = true; }
    check(unknown_read, "CLINT compare reads must not silently return zero before initialization");
    const uint8_t zero[8] = {};
    check(timer.store(0x400c, 4, zero) && !timer.mtip(1).has_value(),
          "partial compare initialization must remain unknown");
    const uint8_t deadline[4] = {10, 0, 0, 0};
    check(timer.store(0x4008, 4, deadline) && timer.mtip(1) == false,
          "initialized compare must produce a known timer line");
    unsigned timer_edges = 0;
    timer.on_interrupt([&](unsigned h, bool, TimerRegisters::TimerLine line) {
      if (h == 1 && line == true) ++timer_edges;
    });
    timer.advance_rtc(9); check(timer.mtip(1) == false, "timer fired early");
    timer.advance_rtc(1); check(timer.mtip(1) == true && timer_edges == 1, "timer edge missing");
    check(timer.store(0xbff8, 8, zero) && timer.mtip(1) == false, "mtime write must deassert timer");
    const uint8_t ipi[4] = {1, 0, 0, 0};
    check(timer.store(8, 4, ipi) && timer.msip(2) && !timer.msip(1), "IPI target isolation");
    check(timer.load(12, 4, raw) && raw[0] == 0, "nonexistent CLINT hart must read zero");
    boot_case(prefix, dtb, false, {0, 1, 2});
    boot_case(prefix, dtb, true, {2, 0, 1});
    std::cout << "{\"physical_rom_boot_tests\":\"pass\",\"three_harts\":true,"
                 "\"schedules\":2,\"core_integration\":false,\"zephyr_boot_certified\":false}\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
