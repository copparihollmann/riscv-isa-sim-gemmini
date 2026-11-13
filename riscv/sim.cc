// See LICENSE for license details.

#include "config.h"
#include "dtb_discovery.h"
#include "sim.h"
#include "iris_timing_adapter.h"
#include "iris_clocked_device.h"
extern "C" uint64_t iris_device_clock_abi_v4() { return 4; }
#include "../../../board/iris_boot.hpp"
#include "../../../board/physical_map.hpp"
#include "mmu.h"
#include "dts.h"
#include "remote_bitbang.h"
#include "byteorder.h"
#include "platform.h"
#include "libfdt.h"
#include "socketif.h"
#include <fstream>
#include <map>
#include <iostream>
#include <sstream>
#include <climits>
#include <cstdlib>
#include <cassert>
#include <algorithm>
#include <signal.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/types.h>

volatile bool ctrlc_pressed = false;
static void handle_signal(int sig)
{
  if (ctrlc_pressed)
    exit(-1);
  ctrlc_pressed = true;
  signal(sig, &handle_signal);
}

const size_t sim_t::INTERLEAVE;

extern device_factory_t* clint_factory;
extern device_factory_t* plic_factory;
extern device_factory_t* ns16550_factory;

sim_t::sim_t(const cfg_t *cfg, bool halted,
             std::vector<std::pair<reg_t, abstract_mem_t*>> mems,
             const std::vector<device_factory_sargs_t>& plugin_device_factories,
             const bool dtb_discovery,
             const std::vector<std::string>& args,
             const debug_module_config_t &dm_config,
             const char *log_path,
             bool dtb_enabled, const char *dtb_file,
             bool socket_enabled,
             FILE *cmd_file, // needed for command line option --cmd
             std::optional<unsigned long long> instruction_limit)
  : htif_t(args),
    cfg(cfg),
    mems(mems),
    dtb_discovery(dtb_discovery),
    dtb_enabled(dtb_enabled),
    log_file(log_path),
    cmd_file(cmd_file),
    instruction_limit(instruction_limit),
    sout_(nullptr),
    current_step(0),
    current_proc(0),
    debug(false),
    histogram_enabled(false),
    log(false),
    remote_bitbang(NULL),
    debug_module(this, dm_config)
{
  signal(SIGINT, &handle_signal);

  sout_.rdbuf(std::cerr.rdbuf()); // debug output goes to stderr by default

  bus.add_device(DEBUG_START, &debug_module);

  socketif = NULL;
#ifdef HAVE_BOOST_ASIO
  if (socket_enabled) {
    socketif = new socketif_t();
  }
#else
  if (socket_enabled) {
    fputs("Socket support requires compilation with boost asio; "
          "please rebuild the riscv-isa-sim project using "
          "\"configure --with-boost-asio\".\n",
          stderr);
    abort();
  }
#endif

#ifndef RISCV_ENABLE_DUAL_ENDIAN
  if (cfg->endianness != endianness_little) {
    fputs("Big-endian support has not been properly enabled; "
          "please rebuild the riscv-isa-sim project using "
          "\"configure --enable-dual-endian\".\n",
          stderr);
    abort();
  }
#endif

  debug_mmu = new mmu_t(this, cfg->endianness, NULL, cfg->cache_blocksz);

  std::optional<iris_timing_adapter::Profile> timing_profile;
  if (!cfg->iris_timing_fixture.empty()) {
    if (!dtb_enabled || cfg->real_time_clint || halted)
      throw std::runtime_error("timing integration requires DTB and deterministic non-halted devices");
    timing_profile = iris_timing_adapter::Profile::load(cfg->iris_timing_fixture, cfg->nprocs());
    if (!cfg->iris_bootrom_file.empty() &&
        timing_profile->base_hz / timing_profile->rtc_divider != iris_board::mtime_hz)
      throw std::runtime_error("Iris physical boot requires its 500kHz timebase");
  }

  // When running without using a dtb, skip the fdt-based configuration steps
  if (!dtb_enabled) {
    for (size_t i = 0; i < cfg->nprocs(); i++) {
      procs.push_back(new processor_t(cfg->isa_for_hart(cfg->hartids[i]), cfg->priv,
                                      cfg, this, cfg->hartids[i], halted,
                                      log_file.get(), sout_));
      harts[cfg->hartids[i]] = procs[i];
    }
    for (auto& x : mems) {
      bus.add_device(x.first, x.second);
    }
    for (auto& pair : harts) {
      if (auto pc = cfg->start_pc.get(pair.first)) {
        pair.second->get_state()->pc = *pc;
      }
    }
    return;
  } // otherwise, generate the procs by parsing the DTS

  // Only make a CLINT (Core-Local INTerrupt controller) and PLIC (Platform-
  // Level-Interrupt-Controller) if they are specified in the device tree
  // configuration.
  //
  // This isn't *quite* as general as we could get (because you might have one
  // that's not bus-accessible), but it should handle the normal use cases. In
  // particular, the default device tree configuration that you get without
  // setting the dtb_file argument has one.
  std::vector<device_factory_sargs_t> device_factories = {
    {clint_factory, {}},
    {plic_factory, {}},
    {ns16550_factory, {}}};

  // Load dtb_file if provided, otherwise self-generate a dts/dtb
  if (dtb_file) {
    std::ifstream fin(dtb_file, std::ios::binary);
    if (!fin.good()) {
      std::cerr << "can't find dtb file: " << dtb_file << std::endl;
      exit(-1);
    }
    std::stringstream strstream;
    strstream << fin.rdbuf();
    dtb = strstream.str();
  } else {
    std::string device_nodes;
    for (const device_factory_sargs_t& factory_sargs: device_factories) {
      const device_factory_t* factory = factory_sargs.first;
      const std::vector<std::string>& sargs = factory_sargs.second;
      device_nodes.append(factory->generate_dts(this, sargs));
    }
    // Explicit plugin nodes must be present before parsing their devices.
    for (const auto& factory_sargs : plugin_device_factories)
      device_nodes.append(factory_sargs.first->generate_dts(this, factory_sargs.second));
    std::vector<size_t> hart_clocks;
    if (timing_profile)
      for (const auto& hart : timing_profile->harts) hart_clocks.push_back(timing_profile->base_hz / hart.divider);
    dts = make_dts(timing_profile ? timing_profile->rtc_divider : INSNS_PER_RTC_TICK,
                   timing_profile ? timing_profile->base_hz : CPU_HZ, cfg, mems, device_nodes, hart_clocks);
    dtb = dts_to_dtb(dts);
  }

  int fdt_code = fdt_check_header(dtb.c_str());
  if (fdt_code) {
    std::cerr << "Failed to read DTB from ";
    if (!dtb_file) {
      std::cerr << "auto-generated DTS string";
    } else {
      std::cerr << "`" << dtb_file << "'";
    }
    std::cerr << ": " << fdt_strerror(fdt_code) << ".\n";
    exit(-1);
  }

  void *fdt = (void *)dtb.c_str();
  if (timing_profile && dtb_file) {
    const int cpus_node = fdt_path_offset(fdt, "/cpus");
    int length = 0;
    const auto* timebase = static_cast<const fdt32_t*>(fdt_getprop(fdt, cpus_node, "timebase-frequency", &length));
    if (!timebase || length != 4 || fdt32_to_cpu(*timebase) != timing_profile->base_hz / timing_profile->rtc_divider)
      throw std::runtime_error("supplied DTB timebase disagrees with timing fixture");
  }

  // per core attribute
  int cpu_offset = 0, cpu_map_offset, rc;
  size_t cpu_idx = 0;
  cpu_offset = fdt_get_offset(fdt, "/cpus");
  cpu_map_offset = fdt_get_offset(fdt, "/cpus/cpu-map");
  if (cpu_offset < 0)
    return;

  for (cpu_offset = fdt_get_first_subnode(fdt, cpu_offset); cpu_offset >= 0;
       cpu_offset = fdt_get_next_subnode(fdt, cpu_offset)) {

    if (!(cpu_map_offset < 0) && cpu_offset == cpu_map_offset)
      continue;

    if (cpu_idx != procs.size()) {
      std::cerr << "Spike only supports contiguous CPU IDs in the DTS" << std::endl;
      exit(1);
    }

    // handle isa string
    const char* isa_str;
    rc = fdt_parse_isa(fdt, cpu_offset, &isa_str);
    if (rc != 0) {
      std::cerr << "core (" << cpu_idx << ") has an invalid or missing 'riscv,isa'\n";
      exit(1);
    }

    // handle hartid
    uint32_t hartid;
    rc = fdt_parse_hartid(fdt, cpu_offset, &hartid);
    if (timing_profile && dtb_file && rc == 0) {
      int length = 0;
      const auto* frequency = static_cast<const fdt32_t*>(fdt_getprop(fdt, cpu_offset, "clock-frequency", &length));
      if (hartid >= timing_profile->harts.size()) throw std::runtime_error("DTB hart absent from timing fixture");
      if (frequency && (length != 4 || (fdt32_to_cpu(*frequency) != 0 &&
          fdt32_to_cpu(*frequency) != timing_profile->base_hz / timing_profile->harts[hartid].divider)))
        throw std::runtime_error("supplied DTB CPU clock disagrees with timing fixture");
    }
    if (rc != 0) {
      std::cerr << "core (" << cpu_idx << ") has an invalid or missing `reg` (hartid)\n";
      exit(1);
    }

    if (cfg->hart_isa.count(hartid)) isa_str = cfg->isa_for_hart(hartid);
    procs.push_back(new processor_t(isa_str, cfg->priv,
                                    cfg, this, hartid, halted,
                                    log_file.get(), sout_));
    harts[hartid] = procs[cpu_idx];

    // handle pmp
    reg_t pmp_num, pmp_granularity;
    if (fdt_parse_pmp_num(fdt, cpu_offset, &pmp_num) != 0)
      pmp_num = 0;
    procs[cpu_idx]->set_pmp_num(pmp_num);

    if (fdt_parse_pmp_alignment(fdt, cpu_offset, &pmp_granularity) == 0) {
      procs[cpu_idx]->set_pmp_granularity(pmp_granularity);
    }

    // handle mmu-type
    const char *mmu_type;
    rc = fdt_parse_mmu_type(fdt, cpu_offset, &mmu_type);
    procs[cpu_idx]->set_max_vaddr_bits(0);
    if (rc == 0) {
      if (strncmp(mmu_type, "riscv,sv32", strlen("riscv,sv32")) == 0) {
        procs[cpu_idx]->set_max_vaddr_bits(32);
      } else if (strncmp(mmu_type, "riscv,sv39", strlen("riscv,sv39")) == 0) {
        procs[cpu_idx]->set_max_vaddr_bits(39);
      } else if (strncmp(mmu_type, "riscv,sv48", strlen("riscv,sv48")) == 0) {
        procs[cpu_idx]->set_max_vaddr_bits(48);
      } else if (strncmp(mmu_type, "riscv,sv57", strlen("riscv,sv57")) == 0) {
        procs[cpu_idx]->set_max_vaddr_bits(57);
      } else if (strncmp(mmu_type, "riscv,sbare", strlen("riscv,sbare")) == 0) {
        // has been set in the beginning
      } else {
        std::cerr << "core ("
                  << cpu_idx
                  << ") has an invalid 'mmu-type': "
                  << mmu_type << ").\n";
        exit(1);
      }
    }

    procs[cpu_idx]->reset();

    cpu_idx++;
  }

  if (dtb_discovery)
  {
    //Add dtb discovered devices
    std::vector<device_factory_sargs_t> dtb_discovery_plugin_device_factories;
    dtb_discovery::discover_devices_from_dtb(fdt, dtb_discovery_plugin_device_factories);
    device_factories.insert(device_factories.end(),
                          dtb_discovery_plugin_device_factories.begin(),
                          dtb_discovery_plugin_device_factories.end());

    //Remove default memories and use dtb discovered memories
    mems.clear();
    dtb_discovery::discover_memory_from_dtb(fdt, mems);
  }
  //clint, plic, ns16550 are always discovered via dtb, independently from the --dtb_discovery flag
  device_factories.insert(device_factories.end(),
                          plugin_device_factories.begin(),
                          plugin_device_factories.end());

  if (!cfg->iris_bootrom_file.empty()) {
    // A physical board run must not turn a hole/MMIO aperture into ordinary RAM
    // through a permissive upstream -m argument, or silently remove real RAM.
    using Range = std::pair<reg_t, reg_t>;
    auto normalize = [](std::vector<Range> ranges) {
      std::sort(ranges.begin(), ranges.end());
      std::vector<Range> result;
      for (const auto& range : ranges) {
        if (!range.second || range.second > UINT64_MAX - range.first)
          throw std::runtime_error("invalid Iris physical RAM range");
        if (!result.empty() && range.first < result.back().first + result.back().second)
          throw std::runtime_error("overlapping Iris physical RAM ranges");
        if (!result.empty() && range.first == result.back().first + result.back().second)
          result.back().second += range.second;
        else result.push_back(range);
      }
      return result;
    };
    std::vector<Range> expected, actual;
    for (const auto& region : iris_board::regions)
      if (std::string(region.name).rfind("memory@", 0) == 0)
        expected.emplace_back(region.base, region.size);
    for (const auto& memory : mems) actual.emplace_back(memory.first, memory.second->size());
    if (normalize(actual) != normalize(expected))
      throw std::runtime_error("IRIS_PHYSICAL_RAM_MAP_MISMATCH: exact elaborated DRAM/TCM/scratchpad ranges required");
  }

  for (auto& x : mems)
  {
      bus.add_device(x.first, x.second);
  }

  // must be located after procs/harts are set (devices might use sim_t get_* member functions)
  for (size_t i = 0; i < device_factories.size(); i++) {
    const device_factory_t* factory = device_factories[i].first;
    const std::vector<std::string>& sargs = device_factories[i].second;
    reg_t device_base = 0;
    abstract_device_t* device = factory->parse_from_fdt(fdt, this, &device_base, sargs);
    if (device) {
      assert(device_base);
      std::shared_ptr<abstract_device_t> dev_ptr(device);
      add_device(device_base, dev_ptr);

      if (dynamic_cast<clint_t*>(&*dev_ptr)) {
        assert(!clint);
        clint = std::static_pointer_cast<clint_t>(dev_ptr);
      }

      if (dynamic_cast<plic_t*>(&*dev_ptr)) {
        assert(!plic);
        plic = std::static_pointer_cast<plic_t>(dev_ptr);
      }
    }
  }

  for (auto& pair : harts) {
    if (auto pc = cfg->start_pc.get(pair.first); pc && cfg->iris_bootrom_file.empty()) {
      pair.second->get_state()->pc = *pc;
    }
  }
  iris_counter_edges.resize(procs.size());
  if (timing_profile) {
    if (!clint) throw std::runtime_error("timing integration requires a CLINT");
    for (const auto& device : devices)
      if (auto* clocked = dynamic_cast<iris_clocked_device_t*>(device.get()))
        timing_profile->clocked_devices.push_back(clocked);
    iris_timing = std::make_unique<iris_timing_adapter>(std::move(*timing_profile), procs,
      [this](uint64_t from, uint64_t to) { iris_advance_clock(from, to); },
      [this] { return iris_next_timer_event(); },
      [this] {
        auto address = get_tohost_addr();
        if (address && ((address & 7) || !dynamic_cast<abstract_mem_t*>(bus.find_device(address, 8).second)))
          throw std::runtime_error("IRIS_TIMING_INVALID_TOHOST: aligned 8-byte RAM symbol required");
        auto* data = address ? addr_to_mem(address) : nullptr;
        if (!data) return false;
        for (unsigned i = 0; i < 8; ++i) if (data[i]) return true;
        return false;
      }, cfg->iris_schedule_seed);
  }
}

sim_t::~sim_t()
{
  for (size_t i = 0; i < procs.size(); i++)
    delete procs[i];
  delete debug_mmu;
}

int sim_t::run()
{
  if (!debug && log)
    set_procs_debug(true);

  htif_t::set_expected_xlen(harts.begin()->second->get_isa().get_max_xlen());

  // htif_t::run() will repeatedly call back into sim_t::idle(), each
  // invocation of which will advance target time
  try {
    int result = htif_t::run();
    if (iris_timing) iris_timing->write_json(cfg->iris_timing_trace);
    return result;
  } catch (...) {
    if (iris_timing) iris_timing->write_json(cfg->iris_timing_trace);
    throw;
  }
}

const insn_fetch_t* sim_t::iris_completion_fetch(unsigned hart) const {
  return iris_timing ? iris_timing->completion_fetch(hart) : nullptr;
}
std::exception_ptr sim_t::iris_completion_exception(unsigned hart) const {
  return iris_timing ? iris_timing->completion_exception(hart) : std::exception_ptr{};
}
void sim_t::iris_issue(unsigned hart, reg_t pc, const insn_fetch_t& fetch) {
  if (iris_timing) iris_timing->issue(hart, pc, fetch);
}
void sim_t::iris_retired(unsigned hart, size_t count) {
  if (iris_timing) iris_timing->retired(hart, count);
}
void sim_t::iris_counter_read(unsigned hart, reg_t pc, uint32_t raw, unsigned csr, reg_t value, unsigned destination, const char* phase) {
  if (iris_timing) iris_timing->counter_read(hart, pc, raw, csr, value, destination, phase);
}
std::optional<reg_t> sim_t::iris_mcycle_pre_edge(unsigned hart) const {
  if (!iris_timing) return {};
  if (hart>=iris_counter_edges.size() || !iris_counter_edges[hart] || *iris_counter_edges[hart]!=iris_timing->now())
    throw std::runtime_error("IRIS_COUNTER_READ_UNMODELED_EDGE_PHASE hart="+std::to_string(hart));
  const auto sample=procs.at(hart)->get_state()->mcycle->iris_read_pre_edge();
  if (!sample) throw std::runtime_error("IRIS_COUNTER_READ_PRE_EDGE_SAMPLE_MISSING");
  return sample;
}
void sim_t::iris_validate_interrupts(unsigned hart, bool read_pending) const {
  if (clint) clint->validate_iris_interrupts(hart, read_pending);
  if (plic) plic->validate_iris_interrupts(hart, read_pending);
}
bool sim_t::reservable(reg_t paddr) {
  // Rocket/Shuttle TLBs allow LR/SC only on AcquireB-capable cacheable RAM.
  // TCM supports arithmetic/logical AMOs but is not cacheable; its aliases
  // resolve to the same non-reservable backing storage before reaching here.
  if (cfg->iris_vme || !cfg->iris_bootrom_file.empty())
    return paddr >= 0x80000000ULL && paddr - 0x80000000ULL < 0x100000000ULL && addr_to_mem(paddr);
  return addr_to_mem(paddr);
}
void sim_t::iris_advance_clock(uint64_t before, uint64_t after) {
  const auto& profile = iris_timing->profile();
  for (size_t i = 0; i < procs.size(); ++i) {
    const auto& clock = profile.harts[i];
    const auto edges=after / clock.divider - before / clock.divider;
    if (edges) {
      bool enabled=clock.count_wfi || !procs[i]->is_waiting_for_interrupt();
      if(profile.source_counter_clock&&profile.empirical) {
        const auto last=after/clock.divider*clock.divider;
        const auto counts=iris_timing->source_counter_span(i,last);
        if(counts.first)procs[i]->get_state()->mcycle->advance_time(counts.first,false);
        if(counts.second)procs[i]->get_state()->mcycle->advance_time(counts.second,true);
      }else{
        if(profile.source_counter_clock) {
          if(edges!=1 || after%clock.divider)throw std::runtime_error("IRIS_SOURCE_COUNTER_SKIPPED_UNGATED_EDGE");
          enabled=iris_timing->source_counter_pre_edge(i,after);
        }
        procs[i]->get_state()->mcycle->advance_time(edges,enabled);
      }
      iris_counter_edges.at(i)=after / clock.divider * clock.divider;
    }
  }
  uint64_t ticks = after / profile.rtc_divider - before / profile.rtc_divider;
  for (auto* clocked : profile.clocked_devices)
    clocked->iris_advance_model_clock(before, after, profile.base_hz);
  // All device time advances from the model clock, never instruction retirement.
  for (auto& device : devices) device->tick(ticks);
}
std::optional<uint64_t> sim_t::iris_next_timer_event() {
  const auto now = iris_timing->now(), divider = iris_timing->profile().rtc_divider;
  const uint64_t current = clint->get_mtime(), max = UINT64_MAX;
  std::optional<uint64_t> earliest;
  for (const auto& pair : harts) {
    auto known_compare = clint->timer_compare(pair.first);
    if (!known_compare) continue;
    uint64_t compare = *known_compare;
    if (current >= compare && compare == 0) continue;
    // Include timer deassertion on unsigned mtime wrap.
    uint64_t ticks = current < compare ? compare - current : max - current + 1;
    uint64_t first = divider - now % divider;
    if (first >= max - now) continue;
    uint64_t edge = now + first;
    if (ticks - 1 > (max - 1 - edge) / divider) continue;
    edge += (ticks - 1) * divider;
    if (!earliest || edge < *earliest) earliest = edge;
  }
  for (auto* clocked : iris_timing->profile().clocked_devices) {
    auto edge = clocked->iris_next_model_event(now, iris_timing->profile().base_hz);
    if (edge && *edge <= now)
      throw std::runtime_error("IRIS_DEVICE_INVALID_DEADLINE: device event must be future");
    if (edge && (!earliest || *edge < *earliest)) earliest = edge;
  }
  return earliest;
}

void sim_t::step(size_t n)
{
  if (iris_timing) { iris_timing->step(n); return; }
  if (iris_hart_order.empty()) {
    for (size_t hart = 0; hart < procs.size(); ++hart) iris_hart_order.push_back(hart);
    if (cfg->iris_schedule_seed) {
      iris_schedule_rng.seed(*cfg->iris_schedule_seed);
      std::shuffle(iris_hart_order.begin(), iris_hart_order.end(), iris_schedule_rng);
    }
  }
  for (size_t i = 0, steps = 0; i < n; i += steps)
  {
    steps = std::min(n - i, INTERLEAVE - current_step);
    procs[iris_hart_order[current_proc]]->step(steps);

    current_step += steps;
    if (current_step == INTERLEAVE)
    {
      current_step = 0;
      procs[iris_hart_order[current_proc]]->get_mmu()->yield_load_reservation();
      if (++current_proc == procs.size()) {
        current_proc = 0;
        reg_t rtc_ticks = INTERLEAVE / INSNS_PER_RTC_TICK;
        for (auto &dev : devices) dev->tick(rtc_ticks);
        if (cfg->iris_schedule_seed)
          std::shuffle(iris_hart_order.begin(), iris_hart_order.end(), iris_schedule_rng);
      }
    }
  }
}
const char* sim_t::get_dts() {
  dts = dtb_to_dts(dtb);
  return dts.c_str(); 
}
void sim_t::add_device(reg_t addr, std::shared_ptr<abstract_device_t> dev) {
  bus.add_device(addr, dev.get());
  devices.push_back(dev);
  if (auto* clocked = dynamic_cast<iris_clocked_device_t*>(dev.get()))
    if (iris_timing) iris_timing->register_clocked_device(clocked);
}

void sim_t::set_debug(bool value)
{
  debug = value;
}

void sim_t::set_histogram(bool value)
{
  histogram_enabled = value;
  for (size_t i = 0; i < procs.size(); i++) {
    procs[i]->set_histogram(histogram_enabled);
  }
}

void sim_t::configure_log(bool enable_log, bool enable_commitlog)
{
  log = enable_log;

  if (!enable_commitlog)
    return;

  for (processor_t *proc : procs) {
    proc->enable_log_commits();
  }
}

void sim_t::set_procs_debug(bool value)
{
  for (size_t i=0; i< procs.size(); i++)
    procs[i]->set_debug(value);
}

bool sim_t::is_debug_module_access(reg_t paddr, size_t len)
{
  return bus.find_device(paddr, len).second == &debug_module;
}

bool sim_t::mmio_load(reg_t paddr, size_t len, uint8_t* bytes)
{
  if (paddr + len < paddr)
    return false;
  return bus.load(paddr, len, bytes);
}

bool sim_t::mmio_store(reg_t paddr, size_t len, const uint8_t* bytes)
{
  if (paddr + len < paddr)
    return false;
  return bus.store(paddr, len, bytes);
}

void sim_t::set_rom()
{
  const int reset_vec_size = 8;

  reg_t start_pc = cfg->start_pc.get(0).value_or(get_entry_point());

  uint32_t reset_vec[reset_vec_size] = {
    0x297,                                      // auipc  t0,0x0
    0x28593 + (reset_vec_size * 4 << 20),       // addi   a1, t0, &dtb
    0xf1402573,                                 // csrr   a0, mhartid
    get_core(0)->get_xlen() == 32 ?
      0x0182a283u :                             // lw     t0,24(t0)
      0x0182b283u,                              // ld     t0,24(t0)
    0x28067,                                    // jr     t0
    0,
    (uint32_t) (start_pc & 0xffffffff),
    (uint32_t) (start_pc >> 32)
  };
  if (get_target_endianness() == endianness_big) {
    int i;
    // Instuctions are little endian
    for (i = 0; reset_vec[i] != 0; i++)
      reset_vec[i] = to_le(reset_vec[i]);
    // Data is big endian
    for (; i < reset_vec_size; i++)
      reset_vec[i] = to_be(reset_vec[i]);

    // Correct the high/low order of 64-bit start PC
    if (get_core(0)->get_xlen() != 32)
      std::swap(reset_vec[reset_vec_size-2], reset_vec[reset_vec_size-1]);
  } else {
    for (int i = 0; i < reset_vec_size; i++)
      reset_vec[i] = to_le(reset_vec[i]);
  }

  std::vector<char> rom((char*)reset_vec, (char*)reset_vec + sizeof(reset_vec));

  rom.insert(rom.end(), dtb.begin(), dtb.end());
  const int align = 0x1000;
  rom.resize((rom.size() + align - 1) / align * align);

  std::shared_ptr<rom_device_t> boot_rom(new rom_device_t(rom));
  add_device(DEFAULT_RSTVEC, boot_rom);
}

char* sim_t::addr_to_mem(reg_t paddr) {
  auto page_offset = paddr % PGSIZE;
  auto page_addr = paddr - page_offset;

  if (auto it = addr_to_mem_cache.find(page_addr); it != addr_to_mem_cache.end())
    return it->second + page_offset;

  auto desc = bus.find_device(page_addr, PGSIZE);
  if (auto mem = dynamic_cast<abstract_mem_t*>(desc.second)) {
    auto res = mem->contents(page_addr - desc.first);
    addr_to_mem_cache.insert({page_addr, res});
    return res + page_offset;
  }

  return nullptr;
}

const char* sim_t::get_symbol(uint64_t paddr)
{
  return htif_t::get_symbol(paddr);
}

// htif

void sim_t::reset()
{
  if (cfg->iris_bootrom_file.empty()) {
    if (dtb_enabled) set_rom();
    return;
  }
  if (!dtb_enabled || !clint || cfg->hartids != std::vector<size_t>({0, 1, 2}))
    throw std::runtime_error("Iris physical boot requires DTB, CLINT and harts 0/1/2");
  auto rom = std::make_shared<iris_board::ReadOnlyBootROM>(
      iris_board::read_binary(cfg->iris_bootrom_file), std::vector<char>(dtb.begin(), dtb.end()));
  auto bootreg = std::make_shared<iris_board::BootAddressRegister>();
  add_device(iris_board::rom_base, rom); add_device(iris_board::bootreg_base, bootreg);
  reg_t entry = cfg->start_pc.get(0).value_or(get_entry_point());
  uint8_t address[8];
  for (unsigned i = 0; i < 8; ++i) address[i] = uint8_t(entry >> (8 * i));
  if (!bootreg->store(0, 8, address)) throw std::runtime_error("Iris boot address write failed");
  const uint8_t release[4] = {1, 0, 0, 0};
  if (!clint->store(0, 4, release)) throw std::runtime_error("Iris boot release failed");
}

void sim_t::idle()
{
  if (done())
    return;

  if (debug || ctrlc_pressed)
    interactive();
  else {
    if (instruction_limit.has_value()) {
      if (*instruction_limit < INTERLEAVE) {
        // Final step.
        step(*instruction_limit);
        htif_exit(0);
        *instruction_limit = 0;
        return;
      }
      *instruction_limit -= INTERLEAVE;
    }
    step(INTERLEAVE);
  }

  if (remote_bitbang)
    remote_bitbang->tick();
}

void sim_t::read_chunk(addr_t taddr, size_t len, void* dst)
{
  assert(len == 8);
  auto data = debug_mmu->to_target(debug_mmu->load<uint64_t>(taddr));
  memcpy(dst, &data, sizeof data);
}

void sim_t::iris_read_transport(addr_t address,size_t bytes,void* data,uint8_t* known) {
  if(!get_cfg().iris_vme){htif_t::iris_read_transport(address,bytes,data,known);return;}
  if((address|bytes)&7)throw std::runtime_error("IRIS_UNVERIFIED_HTIF_TRANSPORT_ALIGNMENT");
  for(size_t i=0;i<bytes;i+=8) {
    auto word=debug_mmu->load_transport<uint64_t>(address+i);
    const auto target=debug_mmu->to_target(word.value);memcpy((uint8_t*)data+i,&target,8);
    if(get_target_endianness()==endianness_big)std::reverse(word.known.begin(),word.known.end());
    std::copy(word.known.begin(),word.known.end(),known+i);
  }
}
void sim_t::iris_write_transport(addr_t address,size_t bytes,const void* data,const uint8_t* known) {
  if(!get_cfg().iris_vme){htif_t::iris_write_transport(address,bytes,data,known);return;}
  if((address|bytes)&7)throw std::runtime_error("IRIS_UNVERIFIED_HTIF_TRANSPORT_ALIGNMENT");
  for(size_t i=0;i<bytes;i+=8) {
    target_endian<uint64_t> target;memcpy(&target,(const uint8_t*)data+i,8);
    iris_definedness::Value<uint64_t> word;word.value=debug_mmu->from_target(target);
    std::copy_n(known+i,8,word.known.begin());
    if(get_target_endianness()==endianness_big)std::reverse(word.known.begin(),word.known.end());
    debug_mmu->store_transport<uint64_t>(address+i,word);
  }
}
void sim_t::iris_validate_syscall(reg_t number,const reg_t* args) {
  if(!get_cfg().iris_vme)return;
  if(number!=64&&number!=93)throw std::runtime_error("IRIS_UNVERIFIED_HTIF_SYSCALL: definedness qualified for write/exit only");
  if(number==64)for(reg_t i=0;i<args[2];++i)(void)debug_mmu->load<uint8_t>(args[1]+i);
}

void sim_t::write_chunk(addr_t taddr, size_t len, const void* src)
{
  assert(len == 8);
  target_endian<uint64_t> data;
  memcpy(&data, src, sizeof data);
  debug_mmu->store<uint64_t>(taddr, debug_mmu->from_target(data));
}

endianness_t sim_t::get_target_endianness() const
{
  return debug_mmu->is_target_big_endian()? endianness_big : endianness_little;
}

void sim_t::proc_reset(unsigned id)
{
  if (id<iris_counter_edges.size()) iris_counter_edges[id].reset();
  debug_module.proc_reset(id);
  if (harts.count(id)) {
    if (!cfg->iris_bootrom_file.empty()) {
      harts[id]->get_state()->pc = iris_board::reset_pc;
      return;
    }
    if (auto pc = cfg->start_pc.get(id)) {
      harts[id]->get_state()->pc = *pc;
    }
  }
}
