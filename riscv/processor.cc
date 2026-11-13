// See LICENSE for license details.

#include "arith.h"
#include "processor.h"
#include "extension.h"
#include "common.h"
#include "config.h"
#include "decode_macros.h"
#include "simif.h"
#include "mmu.h"
#include "disasm.h"
#include "platform.h"
#include "vector_unit.h"
#include "debug_defines.h"
#include <cinttypes>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <iomanip>
#include <assert.h>
#include <limits.h>
#include <stdexcept>
#include <sstream>
#include <string>
#include <algorithm>
#include <cstring>

iris_definedness::Value<uint64_t> processor_t::iris_frontend_read_beat(reg_t address) {
  // Source I-cache requests use a physical, side-effect-free instruction port.
  // Do not route these through a data MMU or interpret MPRV as fetch privilege.
  if(address&7)throw std::runtime_error("IRIS_FRONTEND_UNALIGNED_BEAT");
  const auto physical=iris_board::storage_address(id,address);
  if(!iris_board::permits(physical,8,iris_board::Access::Execute))
    throw std::runtime_error("IRIS_FRONTEND_REFILL_PHYSICAL_ROUTE_UNMODELED");
  iris_definedness::Value<uint64_t> value;std::array<uint8_t,8> bytes{};
  if(sim->addr_to_mem(physical)) {
    for(unsigned i=0;i<8;++i) {
      const auto* p=sim->addr_to_mem(physical+i);
      if(!p)throw std::runtime_error("IRIS_FRONTEND_REFILL_RAM_HOLE");
      bytes[i]=uint8_t(*p);
    }
    sim->iris_memory_definedness.read_into(physical,value.known);
  } else {
    if(physical<0x10000 || physical+8>0x20000 || !sim->mmio_fetch(physical,8,bytes.data()))
      throw std::runtime_error("IRIS_FRONTEND_REFILL_DEVICE_UNMODELED");
    value.known.fill(0xff);
  }
  value.value=0;for(unsigned i=0;i<8;++i)value.value|=uint64_t(bytes[i])<<(8*i);
  return value;
}

void processor_t::iris_fabric_commit_cached_store(reg_t address,unsigned bytes,uint64_t value) {
  if(!bytes||bytes>8||address<0x80000000||address>=0x180000000ULL||bytes>0x180000000ULL-address)throw std::runtime_error("IRIS_ROCKET_SOURCE_CACHED_STORE_MIRROR_RANGE");
  for(unsigned n=0;n<bytes;++n){auto*p=sim->addr_to_mem(address+n);if(!p)throw std::runtime_error("IRIS_ROCKET_SOURCE_CACHED_STORE_MIRROR_HOLE");*p=value>>(8*n);}
  sim->iris_memory_definedness.define(address,bytes);
}

uint64_t processor_t::iris_fabric_external_io_read(reg_t address,unsigned size) {
  if(!size||size>8||sim->addr_to_mem(address))throw std::runtime_error("IRIS_ROCKET_FABRIC_EXTERNAL_IO_READ_SCOPE");
  std::array<uint8_t,8> data{};
  if(!sim->mmio_load(address,size,data.data()))throw std::runtime_error("IRIS_ROCKET_FABRIC_EXTERNAL_IO_READ_REFUSED");
  uint64_t value=0;for(unsigned i=0;i<size;++i)value|=uint64_t(data[i])<<(8*i);return value;
}
void processor_t::iris_fabric_external_io_write(reg_t address,unsigned size,uint64_t value,uint64_t mask) {
  if(!size||size>8||sim->addr_to_mem(address))throw std::runtime_error("IRIS_ROCKET_FABRIC_EXTERNAL_IO_WRITE_SCOPE");
  for(unsigned i=0;i<size;){if(!(mask&(uint64_t(1)<<i))){++i;continue;}unsigned count=1;while(i+count<size&&(mask&(uint64_t(1)<<(i+count))))++count;
    if(count!=1&&count!=2&&count!=4&&count!=8)throw std::runtime_error("IRIS_ROCKET_FABRIC_EXTERNAL_IO_MASK_UNMODELED");
    std::array<uint8_t,8> data{};for(unsigned n=0;n<count;++n)data[n]=value>>(8*(i+n));
    if(!sim->mmio_store(address+i,count,data.data()))throw std::runtime_error("IRIS_ROCKET_FABRIC_EXTERNAL_IO_WRITE_REFUSED");i+=count;
  }
}

std::array<std::pair<uint8_t,uint64_t>,8> processor_t::iris_frontend_pmp() const {
  if(n_pmp!=8 || lg_pmp_granularity!=2)throw std::runtime_error("IRIS_ROCKET_FRONTEND_PMP_SOURCE_CONFIG_MISMATCH");
  const auto cfg=state.csrmap.at(CSR_PMPCFG0)->read();std::array<std::pair<uint8_t,uint64_t>,8> out;
  for(unsigned i=0;i<8;++i){const auto address=state.pmpaddr[i]->read();
    if(address>>33)throw std::runtime_error("IRIS_ROCKET_FRONTEND_PMP_ADDRESS_WIDTH_UNMODELED");
    out[i]={uint8_t(cfg>>(i*8)),address};}
  return out;
}

bool processor_t::iris_pipeline_context_safe() const {
  return xlen == 64 && state.prv == PRV_M && !state.v && !state.debug_mode &&
      state.single_step == state_t::STEP_NONE && !debug && halt_request == HR_NONE &&
      !halt_on_reset && !check_triggers_icount && !mmu->iris_execute_trigger_enabled() &&
      state.elp == elp_t::NO_LP_EXPECTED;
}

bool processor_t::iris_pipeline_can_prefetch(reg_t pc, bool allow_compressed, bool allow_split_pages) const {
  if (!iris_pipeline_context_safe() || (pc & 1) || pc>std::numeric_limits<reg_t>::max()-1) return false;
  auto* low=sim->addr_to_mem(pc);auto* high=sim->addr_to_mem(pc+1);
  if (!low || !high) return false;
  if (!allow_split_pages && reinterpret_cast<uintptr_t>(high)!=reinterpret_cast<uintptr_t>(low)+1) return false;
  // mem_t uses separately allocated host pages. Guest RAM at a page boundary
  // need not have contiguous host pointers. Read only the required mapped
  // bytes here; the ordinary MMU fetch retains its architectural access checks.
  const uint16_t half=uint8_t(*low)|(uint16_t(uint8_t(*high))<<8);
  const unsigned length=insn_length(half);
  if (length==2) return allow_compressed && extension_enabled(EXT_ZCA);
  return length==4 && pc<=std::numeric_limits<reg_t>::max()-3 &&
      sim->addr_to_mem(pc+2) && sim->addr_to_mem(pc+3) &&
      (allow_split_pages || reinterpret_cast<uintptr_t>(sim->addr_to_mem(pc+3))==reinterpret_cast<uintptr_t>(low)+3);
}

std::exception_ptr processor_t::iris_pipeline_interrupt_exception() {
  if (!iris_pipeline_context_safe())
    throw std::runtime_error("IRIS_PIPELINE_INTERRUPT_PROBE_CONTEXT_UNMODELED");
  // take_interrupt normally exits WFI even for a masked interrupt. Preserve
  // that architectural flag while reusing its precise priority implementation.
  const bool waiting = state.in_wfi;
  try { take_pending_interrupt(); }
  catch (trap_t&) { state.in_wfi = waiting; return std::current_exception(); }
  state.in_wfi = waiting;
  return {};
}

#ifdef __GNUC__
# pragma GCC diagnostic ignored "-Wunused-variable"
#endif

#undef STATE
#define STATE state

processor_t::processor_t(const char* isa_str, const char* priv_str,
                         const cfg_t *cfg,
                         simif_t* sim, uint32_t id, bool halt_on_reset,
                         FILE* log_file, std::ostream& sout_)
: debug(false), halt_request(HR_NONE), isa(isa_str, priv_str), cfg(cfg),
  sim(sim), id(id), xlen(isa.get_max_xlen()),
  histogram_enabled(false), log_commits_enabled(false),
  log_file(log_file), sout_(sout_.rdbuf()), halt_on_reset(halt_on_reset),
  check_triggers_icount(false),
  impl_table(256, false), extension_enable_table(isa.get_extension_table()),
  last_pc(1), executions(1), TM(cfg->trigger_count)
{
  if (cfg->iris_vme && id == 2 && isa.extension_enabled(EXT_ZVTBASE))
    throw std::invalid_argument("Iris hart 2 must not advertise VME/Zvt; supply a non-VME --hart-isa=2:ISA");
  VU.p = this;
  VU.iris_mode = cfg->iris_vme;
  TM.proc = this;

#ifndef HAVE_INT128
  if (isa.has_any_vector()) {
    fprintf(stderr, "V extension is not supported on platforms without __int128 type\n");
    abort();
  }

  if (isa.extension_enabled(EXT_ZACAS) && isa.get_max_xlen() == 64) {
    fprintf(stderr, "Zacas extension is not supported on 64-bit platforms without __int128 type\n");
    abort();
  }
#endif

  VU.VLEN = isa.get_vlen();
  VU.ELEN = isa.get_elen();
  VU.TE = isa.get_te();
  VU.vlenb = isa.get_vlen() / 8;
  VU.vstart_alu = 0;

  mmu = new mmu_t(sim, cfg->endianness, this, cfg->cache_blocksz);

  set_pmp_granularity(cfg->pmpgranularity);
  set_pmp_num(cfg->pmpregions);

  set_max_vaddr_bits(0);
  set_impl(IMPL_MMU_ASID, true);
  set_impl(IMPL_MMU_VMID, true);

  reset();

  register_base_instructions();

  disassembler = new disassembler_t(&isa);
  for (auto e : isa.get_extensions())
    register_extension(find_extension(e.c_str())());
}

processor_t::~processor_t()
{
  if (histogram_enabled)
  {
    std::vector<std::pair<reg_t, uint64_t>> ordered_histo(pc_histogram.begin(), pc_histogram.end());
    std::sort(ordered_histo.begin(), ordered_histo.end(),
              [](auto& lhs, auto& rhs) { return lhs.second < rhs.second; });

    fprintf(stderr, "PC Histogram size:%zu\n", ordered_histo.size());
    for (auto it : ordered_histo)
      fprintf(stderr, "%0" PRIx64 " %" PRIu64 "\n", it.first, it.second);
  }

  delete mmu;
  delete disassembler;
}

void state_t::reset(processor_t* const proc, reg_t max_isa)
{
  pc = proc->get_cfg().iris_bootrom_file.empty() ? DEFAULT_RSTVEC : 0x10000;
  XPR.reset();
  FPR.reset();

  prv = prev_prv = PRV_M;
  v = prev_v = false;
  prv_changed = false;
  v_changed = false;

  in_wfi = false;
  serialized = false;
  debug_mode = false;
  single_step = STEP_NONE;

  log_reg_write.clear();
  log_mem_read.clear();
  log_mem_write.clear();
  last_inst_priv = 0;
  last_inst_xlen = 0;
  last_inst_flen = 0;

  elp = elp_t::NO_LP_EXPECTED;

  critical_error = false;

  csr_init(proc, max_isa);
}

void processor_t::set_debug(bool value)
{
  debug = value;

  for (auto e : custom_extensions)
    e.second->set_debug(value, *this);
}

void processor_t::set_histogram(bool value)
{
  histogram_enabled = value;
}

void processor_t::enable_log_commits()
{
  log_commits_enabled = true;
  mmu->flush_tlb(); // the TLB caches this setting
  build_opcode_map();
}

void processor_t::reset()
{
  xlen = isa.get_max_xlen();
  state.reset(this, isa.get_max_isa());
  mmu->flush_tlb();
  if (any_vector_extensions())
    VU.reset();

  if (n_pmp > 0 && !cfg->iris_vme) {
    // Iris PMP resets A/L to zero in the saved CSRFile; upstream compatibility
    // initialization is not a source power-on policy. Other PMP bits remain
    // outside current production-definedness qualification.
    // For backwards compatibility with software that is unaware of PMP,
    // initialize PMP to permit unprivileged access to all of memory.
    put_csr(CSR_PMPADDR0, ~reg_t(0));
    put_csr(CSR_PMPCFG0, PMP_R | PMP_W | PMP_X | PMP_NAPOT);
  }

  for (auto e : custom_extensions) { // reset any extensions
    for (auto &csr: e.second->get_csrs(*this))
      state.add_csr(csr->address, csr);
    e.second->reset(*this);
  }

  if (sim)
    sim->proc_reset(id);
}

extension_t* processor_t::get_extension()
{
  switch (custom_extensions.size()) {
    case 0: return NULL;
    case 1: return custom_extensions.begin()->second;
    default:
      fprintf(stderr, "processor_t::get_extension() is ambiguous when multiple extensions\n");
      fprintf(stderr, "are present!\n");
      abort();
  }
}

extension_t* processor_t::get_extension(const char* name)
{
  auto it = custom_extensions.find(name);
  if (it == custom_extensions.end())
    abort();
  return it->second;
}

void processor_t::set_pmp_num(reg_t n)
{
  // check the number of pmp is in a reasonable range
  if (n > state.max_pmp) {
    fprintf(stderr, "error: number of PMP regions requested (%" PRIu64 ") exceeds maximum (%d)\n", n, state.max_pmp);
    abort();
  }
  n_pmp = n;
}

void processor_t::set_pmp_granularity(reg_t gran)
{
  // check the pmp granularity is set from dtb(!=0) and is power of 2
  unsigned min = 1 << PMP_SHIFT;
  if (gran < min || (gran & (gran - 1)) != 0) {
    fprintf(stderr, "error: PMP granularity (%" PRIu64 ") must be a power of two and at least %u\n", gran, min);
    abort();
  }

  lg_pmp_granularity = ctz(gran);
}

void processor_t::set_spmp_addr_entry()
{
  for (size_t i = 0; i < state.max_pmp; ++i) {
    state.mireg[0]->add_ireg_proxy(0x100+i, std::make_shared<const_csr_t>(this, 0x100+i, 0));
    state.nonvirtual_sireg[0]->add_ireg_proxy(0x100+i, std::make_shared<const_csr_t>(this, 0x100+i, 0));
  }

  for (size_t i = 0; i < (state.max_pmp - n_pmp); ++i) {
    state.pmpaddr[n_pmp+i] = std::make_shared<spmpaddr_csr_t>(this, n_pmp+i);
    state.mireg[0]->add_ireg_proxy(0x100+i, state.pmpaddr[n_pmp+i]);
    state.nonvirtual_sireg[0]->add_ireg_proxy(0x100+i, state.pmpaddr[n_pmp+i]);
  }
}

void processor_t::set_max_vaddr_bits(unsigned n)
{
  switch (n) {
    case 0:
      break;
    case 32:
      if (isa.get_max_xlen() != 32)
        abort();
      break;
    case 39:
    case 48:
    case 57:
      if (isa.get_max_xlen() != 64)
        abort();
      break;
    default:
      abort();
  }

  max_vaddr_bits = n;
}

reg_t processor_t::select_an_interrupt_with_default_priority(reg_t enabled_interrupts) const
{
  // nonstandard interrupts have highest priority
  if (enabled_interrupts >> (IRQ_LCOF + 1))
    enabled_interrupts = enabled_interrupts >> (IRQ_LCOF + 1) << (IRQ_LCOF + 1);
  // standard interrupt priority is MEI, MSI, MTI, SEI, SSI, STI
  else if (enabled_interrupts & MIP_MEIP)
    enabled_interrupts = MIP_MEIP;
  else if (enabled_interrupts & MIP_MSIP)
    enabled_interrupts = MIP_MSIP;
  else if (enabled_interrupts & MIP_MTIP)
    enabled_interrupts = MIP_MTIP;
  else if (enabled_interrupts & MIP_SEIP)
    enabled_interrupts = MIP_SEIP;
  else if (enabled_interrupts & MIP_SSIP)
    enabled_interrupts = MIP_SSIP;
  else if (enabled_interrupts & MIP_STIP)
    enabled_interrupts = MIP_STIP;
  else if (enabled_interrupts & MIP_LCOFIP)
    enabled_interrupts = MIP_LCOFIP;
  else if (enabled_interrupts & MIP_VSEIP)
    enabled_interrupts = MIP_VSEIP;
  else if (enabled_interrupts & MIP_VSSIP)
    enabled_interrupts = MIP_VSSIP;
  else if (enabled_interrupts & MIP_VSTIP)
    enabled_interrupts = MIP_VSTIP;

  return enabled_interrupts;
}

void processor_t::take_interrupt(reg_t pending_interrupts)
{
  reg_t s_pending_interrupts = 0;
  reg_t vstopi = 0;
  reg_t vs_pending_interrupt = 0;

  if (extension_enabled_const(EXT_SSAIA)) {
    s_pending_interrupts = state.nonvirtual_sip->read() & state.nonvirtual_sie->read();
    vstopi = state.vstopi->read();
    // Legacy VS interrupts (VSEIP/VSTIP/VSSIP) come in through pending_interrupts but are shifted
    // down 1 in vstopi. AIA-extended and VTI are not shifted. Clear S bits (VS shifted down by 1).
    vs_pending_interrupt = vstopi ? (reg_t(1) << get_field(vstopi, MTOPI_IID)) : 0;
    vs_pending_interrupt &= ~MIP_S_MASK;
  }

  // Do nothing if no pending interrupts
  if (!pending_interrupts && !s_pending_interrupts && !vs_pending_interrupt) {
    return;
  }

  // Exit WFI if there are any pending interrupts
  clear_waiting_for_interrupt();

  // M-ints have higher priority over HS-ints and VS-ints
  const reg_t mie = get_field(state.mstatus->read(), MSTATUS_MIE);
  const reg_t m_enabled = state.prv < PRV_M || (state.prv == PRV_M && mie);
  reg_t enabled_interrupts = pending_interrupts & ~state.mideleg->read() & -m_enabled;
  if (enabled_interrupts == 0) {
    // HS-ints have higher priority over VS-ints
    const reg_t deleg_to_hs = state.mideleg->read() & ~state.hideleg->read();
    const reg_t sie = get_field(state.sstatus->read(), MSTATUS_SIE);
    const reg_t hs_enabled = state.v || state.prv < PRV_S || (state.prv == PRV_S && sie);
    enabled_interrupts = ((pending_interrupts & deleg_to_hs) | (s_pending_interrupts & ~state.hideleg->read())) & -hs_enabled;
    if (state.v && enabled_interrupts == 0) {
      // VS-ints have least priority and can only be taken with virt enabled
      const reg_t deleg_to_vs = state.hideleg->read();
      const reg_t vs_enabled = state.prv < PRV_S || (state.prv == PRV_S && sie);
      enabled_interrupts = ((pending_interrupts & deleg_to_vs) | vs_pending_interrupt) & -vs_enabled;
    }
  }

  const bool nmie = !(state.mnstatus && !get_field(state.mnstatus->read(), MNSTATUS_NMIE));
  if (!state.debug_mode && nmie && enabled_interrupts) {
    reg_t selected_interrupt = select_an_interrupt_with_default_priority(enabled_interrupts);
    if (check_triggers_icount) TM.detect_icount_match();
    throw trap_t(((reg_t)1 << (isa.get_max_xlen() - 1)) | ctz(selected_interrupt));
  }
}

reg_t processor_t::legalize_privilege(reg_t prv)
{
  assert(prv <= PRV_M);

  if (!extension_enabled('U'))
    return PRV_M;

  if (prv == PRV_HS || (prv == PRV_S && !extension_enabled('S')))
    return PRV_U;

  return prv;
}

void processor_t::set_privilege(reg_t prv, bool virt)
{
  mmu->flush_tlb();
  state.prev_prv = state.prv;
  state.prev_v = state.v;
  state.prv = legalize_privilege(prv);
  state.v = virt && state.prv != PRV_M;
  state.prv_changed = state.prv != state.prev_prv;
  state.v_changed = state.v != state.prev_v;
}

const char* processor_t::get_privilege_string() const
{
  if (state.debug_mode)
    return "D";
  if (state.v) {
    switch (state.prv) {
    case 0x0: return "VU";
    case 0x1: return "VS";
    }
  } else {
    switch (state.prv) {
    case 0x0: return "U";
    case 0x1: return "S";
    case 0x3: return "M";
    }
  }
  fprintf(stderr, "Invalid prv=%lx v=%x\n", (unsigned long)state.prv, state.v);
  abort();
}

void processor_t::enter_debug_mode(uint8_t cause, uint8_t extcause)
{
  const bool has_zicfilp = extension_enabled(EXT_ZICFILP);
  state.debug_mode = true;
  state.dcsr->update_fields(cause, extcause, state.prv, state.v, state.elp);
  state.elp = elp_t::NO_LP_EXPECTED;
  set_privilege(PRV_M, false);
  state.dpc->write(state.pc);
  state.pc = DEBUG_ROM_ENTRY;
  clear_waiting_for_interrupt();
}

void processor_t::debug_output_log(std::stringstream *s)
{
  if (log_file == stderr) {
    std::ostream out(sout_.rdbuf());
    out << s->str(); // handles command line options -d -s -l
  } else {
    fputs(s->str().c_str(), log_file); // handles command line option --log
  }
}

void processor_t::take_trap(trap_t& t, reg_t epc)
{
  unsigned max_xlen = isa.get_max_xlen();

  if (debug) {
    std::stringstream s; // first put everything in a string, later send it to output
    s << "core " << std::dec << std::setfill(' ') << std::setw(3) << id
      << ": exception " << t.name() << ", epc 0x"
      << std::hex << std::setfill('0') << std::setw(max_xlen/4) << zext(epc, max_xlen) << std::endl;
    if (t.has_tval())
       s << "core " << std::dec << std::setfill(' ') << std::setw(3) << id
         << ":           tval 0x" << std::hex << std::setfill('0') << std::setw(max_xlen / 4)
         << zext(t.get_tval(), max_xlen) << std::endl;
    debug_output_log(&s);
  }

  if (state.debug_mode) {
    if (t.cause() == CAUSE_BREAKPOINT) {
      state.pc = DEBUG_ROM_ENTRY;
    } else {
      state.pc = DEBUG_ROM_TVEC;
    }
    return;
  }

  // By default, trap to M-mode, unless delegated to HS-mode or VS-mode
  reg_t vsdeleg, hsdeleg;
  reg_t bit = t.cause();
  bool curr_virt = state.v;
  const reg_t interrupt_bit = (reg_t)1 << (max_xlen - 1);
  bool interrupt = (bit & interrupt_bit) != 0;
  bool supv_double_trap = false;
  if (interrupt) {
    vsdeleg = (curr_virt && state.prv <= PRV_S) ? state.hideleg->read() : 0;
    hsdeleg = (state.prv <= PRV_S) ? (state.mideleg->read() | state.nonvirtual_sip->read()) : 0;
    bit &= ~((reg_t)1 << (max_xlen - 1));
  } else {
    vsdeleg = (curr_virt && state.prv <= PRV_S) ? (state.medeleg->read() & state.hedeleg->read()) : 0;
    hsdeleg = (state.prv <= PRV_S) ? state.medeleg->read() : 0;
  }
  // An unexpected trap - a trap when SDT is 1 - traps to M-mode
  if ((state.prv <= PRV_S && bit < max_xlen) &&
      (((vsdeleg >> bit) & 1)  || ((hsdeleg >> bit) & 1))) {
    // Trap is handled in VS-mode or HS-mode. Read the sstatus of the
    // mode that will handle the trap based on the delegation control
    reg_t s = (((vsdeleg >> bit) & 1)) ? state.sstatus->read() :
                                         state.nonvirtual_sstatus->read();
    supv_double_trap = get_field(s, MSTATUS_SDT);
    if (supv_double_trap)
      vsdeleg = hsdeleg = 0;
  }
  bool vti = false;
  if (extension_enabled_const(EXT_SSAIA) && extension_enabled('H')) {
    const reg_t hvictl = state.csrmap[CSR_HVICTL]->read();
    const reg_t iid = get_field(hvictl, HVICTL_IID);
    // It is possible that hvictl is injecting VSEIP (10) and hvictl.DPR is causing mip.VSEIP to be picked over VTI.
    // Check vstopi == hvictl.iid
    vti = (hvictl & HVICTL_VTI) && iid != IRQ_S_EXT && iid == bit && get_field(state.vstopi->read(), MTOPI_IID) == iid;
  }
  if ((state.prv <= PRV_S && bit < max_xlen && ((vsdeleg >> bit) & 1)) || vti) {
    // Handle the trap in VS-mode
    const reg_t adjusted_cause = interrupt && bit <= IRQ_VS_EXT && !vti ? bit - 1 : bit;  // VSSIP -> SSIP, etc;
    reg_t vector = (state.vstvec->read() & 1) && interrupt ? 4 * adjusted_cause : 0;
    state.pc = (state.vstvec->read() & ~(reg_t)1) + vector;
    state.vscause->write(adjusted_cause | (interrupt ? interrupt_bit : 0));
    state.vsepc->write(epc);
    state.vstval->write(t.get_tval());

    reg_t s = state.sstatus->read();
    s = set_field(s, MSTATUS_SPIE, get_field(s, MSTATUS_SIE));
    s = set_field(s, MSTATUS_SPP, state.prv);
    s = set_field(s, MSTATUS_SIE, 0);
    s = set_field(s, MSTATUS_SPELP, state.elp);
    if ((state.menvcfg->read() & MENVCFG_DTE) && (state.henvcfg->read() & HENVCFG_DTE))
      s = set_field(s, MSTATUS_SDT, 1);
    state.elp = elp_t::NO_LP_EXPECTED;
    state.sstatus->write(s);
    set_privilege(PRV_S, true);
  } else if (state.prv <= PRV_S && bit < max_xlen && ((hsdeleg >> bit) & 1)) {
    // Handle the trap in HS-mode
    reg_t vector = (state.nonvirtual_stvec->read() & 1) && interrupt ? 4 * bit : 0;
    state.pc = (state.nonvirtual_stvec->read() & ~(reg_t)1) + vector;
    state.nonvirtual_scause->write(t.cause());
    state.nonvirtual_sepc->write(epc);
    state.nonvirtual_stval->write(t.get_tval());
    state.htval->write(t.get_tval2());
    state.htinst->write(t.get_tinst());

    reg_t s = state.nonvirtual_sstatus->read();
    s = set_field(s, MSTATUS_SPIE, get_field(s, MSTATUS_SIE));
    s = set_field(s, MSTATUS_SPP, state.prv);
    s = set_field(s, MSTATUS_SIE, 0);
    s = set_field(s, MSTATUS_SPELP, state.elp);
    if (state.menvcfg->read() & MENVCFG_DTE)
      s = set_field(s, MSTATUS_SDT, 1);
    state.elp = elp_t::NO_LP_EXPECTED;
    state.nonvirtual_sstatus->write(s);
    if (extension_enabled('H')) {
      s = state.hstatus->read();
      if (curr_virt)
        s = set_field(s, HSTATUS_SPVP, state.prv);
      s = set_field(s, HSTATUS_SPV, curr_virt);
      s = set_field(s, HSTATUS_GVA, t.has_gva());
      state.hstatus->write(s);
    }
    set_privilege(PRV_S, false);
  } else {
    // Handle the trap in M-mode
    const reg_t vector = (state.mtvec->read() & 1) && interrupt ? 4 * bit : 0;
    const reg_t trap_handler_address = (state.mtvec->read() & ~(reg_t)1) + vector;
    // RNMI sources, the feature isn't very useful, so pick an invalid address.
    // RNMI exception vector is implementation-defined.  Since we don't model
    const reg_t rnmi_trap_handler_address = 0;
    const bool nmie = !(state.mnstatus && !get_field(state.mnstatus->read(), MNSTATUS_NMIE));

    reg_t s = state.mstatus->read();
    if ( extension_enabled(EXT_SMDBLTRP)) {
      if (get_field(s, MSTATUS_MDT) && (!state.mnstatus || !nmie)) {
        // Critical error - Double trap in M-mode when Smrnmi not implemented or nmie is 0
        // RNMI is not modeled else double trap in M-mode would trap to
        // RNMI handler instead of leading to a critical error
        state.critical_error = 1;
        return;
      }
      s = set_field(s, MSTATUS_MDT, 1);
    }

    state.pc = !nmie ? rnmi_trap_handler_address : trap_handler_address;
    state.mepc->write(epc);
    state.mcause->write(supv_double_trap ? CAUSE_DOUBLE_TRAP : t.cause());
    state.mtval->write(t.get_tval());
    state.mtval2->write(supv_double_trap ? t.cause() : t.get_tval2());
    state.mtinst->write(t.get_tinst());

    s = set_field(s, MSTATUS_MPIE, get_field(s, MSTATUS_MIE));
    s = set_field(s, MSTATUS_MPP, state.prv);
    s = set_field(s, MSTATUS_MIE, 0);
    s = set_field(s, MSTATUS_MPV, curr_virt);
    s = set_field(s, MSTATUS_GVA, t.has_gva());
    s = set_field(s, MSTATUS_MPELP, state.elp);
    state.elp = elp_t::NO_LP_EXPECTED;
    state.mstatus->write(s);
    if (state.mstatush) state.mstatush->write(s >> 32);  // log mstatush change
    if (state.tcontrol) state.tcontrol->write((state.tcontrol->read() & CSR_TCONTROL_MTE) ? CSR_TCONTROL_MPTE : 0);
    set_privilege(PRV_M, false);
  }
}

void processor_t::take_trigger_action(triggers::action_t action, reg_t breakpoint_tval, reg_t epc, bool virt)
{
  if (debug) {
    std::stringstream s; // first put everything in a string, later send it to output
    s << "core " << std::dec << std::setfill(' ') << std::setw(3) << id
      << ": trigger action " << (int)action << std::endl;
    debug_output_log(&s);
  }

  switch (action) {
    case triggers::ACTION_DEBUG_MODE:
      enter_debug_mode(DCSR_CAUSE_HWBP, 0);
      break;
    case triggers::ACTION_DEBUG_EXCEPTION: {
      trap_breakpoint trap(virt, breakpoint_tval);
      take_trap(trap, epc);
      break;
    }
    default:
      abort();
  }
}

const char* processor_t::get_symbol(uint64_t addr)
{
  return sim->get_symbol(addr);
}

void processor_t::check_if_lpad_required()
{
  if (unlikely(state.elp == elp_t::LP_EXPECTED)) {
    // also see insns/lpad.h for more checks performed
    insn_fetch_t fetch = mmu->load_insn(state.pc);
    software_check((fetch.insn.bits() & MASK_LPAD) == MATCH_LPAD, LANDING_PAD_FAULT);
  }
}

reg_t processor_t::set_lpad_expected(reg_t pc)
{
  auto p = this;
  if (ZICFILP_xLPE(state.v, state.prv))
    state.elp = elp_t::LP_EXPECTED;
  return pc;
}

void processor_t::disasm(insn_t insn)
{
  uint64_t bits = insn.bits();
  if (last_pc != state.pc || last_bits != bits) {
    std::stringstream s;  // first put everything in a string, later send it to output

    const char* sym = get_symbol(state.pc);
    if (sym != nullptr)
    {
      s << "core " << std::dec << std::setfill(' ') << std::setw(3) << id
        << ": >>>>  " << sym << std::endl;
    }

    if (executions != 1) {
      s << "core " << std::dec << std::setfill(' ') << std::setw(3) << id
        << ": Executed " << executions << " times" << std::endl;
    }

    unsigned max_xlen = isa.get_max_xlen();

    s << "core " << std::dec << std::setfill(' ') << std::setw(3) << id
      << std::hex << ": 0x" << std::setfill('0') << std::setw(max_xlen / 4)
      << zext(state.pc, max_xlen) << " (0x" << std::setw(8) << bits << ") "
      << disassembler->disassemble(insn) << std::endl;

    debug_output_log(&s);

    last_pc = state.pc;
    last_bits = bits;
    executions = 1;
  } else {
    executions++;
  }
}

void processor_t::put_csr(int which, reg_t val)
{
  val = zext_xlen(val);
  auto search = state.csrmap.find(which);
  if (search != state.csrmap.end()) {
    search->second->write(val);
    return;
  }
}

bool processor_t::iris_fcsr_instruction(insn_t insn,reg_t pc)
{
  const unsigned csr=insn.csr();
  reg_t mask=0;
  switch(csr) {
    case CSR_FFLAGS:mask=31;break;case CSR_FRM:mask=7;break;case CSR_FCSR:mask=255;break;
    case CSR_VSTART:mask=VU.VLEN-1;break;case CSR_VXRM:mask=3;break;case CSR_VXSAT:mask=1;break;
    case CSR_VCSR:mask=7;break;case CSR_MCOUNTEREN:case CSR_SCOUNTEREN:mask=7;break;
    default:return false;
  }
  if(!VU.iris_mode)return false;
  const unsigned operation=insn.funct3()&3;
  const bool architectural_write=operation==1||insn.rs1()!=0;
  // Shuttle forwards CSR.S/C even for rs1=x0/uimm=0; Rocket changes those
  // commands to CSR.R. For these writable state CSRs, the forwarded zero
  // update still dirties FS/VS. Preserve old unknown bits through that update.
  // Scope this to the source/RTL-proved state CSRs; counter phases and other
  // asynchronous CSR interactions are handled by separate policies.
  const bool state_csr=csr==CSR_FFLAGS||csr==CSR_FRM||csr==CSR_FCSR||
    csr==CSR_VSTART||csr==CSR_VXRM||csr==CSR_VXSAT||csr==CSR_VCSR;
  const bool write=architectural_write||(get_id()<2&&state_csr&&operation!=1);
  auto cell=state.csrmap.at(csr);cell->verify_permissions(insn,architectural_write);
  const reg_t old=cell->read();
  reg_t old_known=cell->iris_known_bits()&mask;
  if(csr==CSR_FCSR)old_known=((state.frm->iris_known_bits()&7)<<5)|(state.fflags->iris_known_bits()&31);
  if(csr==CSR_VCSR)old_known=((VU.vxrm->iris_known_bits()&3)<<1)|(state.vxsat->iris_known_bits()&1);
  auto input=state.XPR.read_transport(insn.rs1());
  if(insn.funct3()&4){input.value=insn.rs1();input.known.fill(0xff);}
  reg_t input_known=0;
  for(size_t byte=0;byte<sizeof(reg_t);++byte)input_known|=reg_t(input.known[byte])<<(byte*8);
  reg_t value=old,known=old_known;
  if(write) {
    if(operation==1){value=input.value;known=input_known;}
    else if(operation==2){value=old|input.value;known=(old_known&input_known)|(old_known&old)|(input_known&input.value);}
    else {value=old&~input.value;known=(old_known&input_known)|(old_known&~old)|(input_known&input.value);}
    value&=mask;known&=mask;cell->write(value);
    if(csr==CSR_FCSR){state.frm->iris_set_known(known>>5);state.fflags->iris_set_known(known);}
    else if(csr==CSR_VCSR){VU.vxrm->iris_set_known(known>>1);state.vxsat->iris_set_known(known);}
    else cell->iris_set_known(known);
  }
  iris_definedness::Value<reg_t> result;result.value=old;result.known.fill(0xff);
  const reg_t result_known=old_known|~mask;
  for(size_t byte=0;byte<sizeof(reg_t);++byte)result.known[byte]=result_known>>(byte*8);
  iris_write_xpr_transport(insn.rd(),result);
  (void)pc;
  return true;
}

// Note that get_csr is sometimes called when read side-effects should not
// be actioned.  In other words, Spike cannot currently support CSRs with
// side effects on reads.
void processor_t::iris_validate_interrupts(bool read_pending) const
{
  sim->iris_validate_interrupts(id, read_pending);
}

reg_t processor_t::get_csr(int which, insn_t insn, bool write, bool peek)
{
  auto search = state.csrmap.find(which);
  if (search != state.csrmap.end()) {
    if (!peek)
      search->second->verify_permissions(insn, write);
    if(VU.iris_mode) {
      if(which==CSR_FFLAGS||which==CSR_FCSR)state.fflags->read_defined(VU.iris_pc);
      if(which==CSR_FRM||which==CSR_FCSR)state.frm->read_defined(VU.iris_pc);
      reg_t tracked_mask=which==CSR_VSTART?VU.VLEN-1:which==CSR_VXRM?3:which==CSR_VXSAT?1:
        (which==CSR_MCOUNTEREN||which==CSR_SCOUNTEREN)?7:0;
      if(which==CSR_VCSR) {
        VU.vxrm->read_defined(VU.iris_pc);
        iris_definedness::require_byte(state.vxsat->iris_known_bits(),1,0,{id,VU.iris_pc,"vxsat"});
      } else if(tracked_mask)
        for(size_t byte=0;byte<sizeof(reg_t);++byte)
          iris_definedness::require_byte(search->second->iris_known_bits()>>(byte*8),tracked_mask>>(byte*8),byte,{id,VU.iris_pc,"CSR"});
    }
    // rd=x0 does not expose the pending word. MTIP and external input bits
    // are read-only, so their unknown placeholders cannot affect a CSR write.
    if (!peek && which == CSR_MIP && insn.rd() != 0) iris_validate_interrupts(true);
    auto value=search->second->read();
    const auto raw=uint32_t(insn.bits()), funct=(raw>>12)&7;
    const bool counter=which==CSR_MCYCLE || which==CSR_MINSTRET || which==CSR_CYCLE || which==CSR_INSTRET ||
        (which>=CSR_MHPMCOUNTER3 && which<=CSR_MHPMCOUNTER31) || (which>=CSR_HPMCOUNTER3 && which<=CSR_HPMCOUNTER31);
    const bool instruction_counter_read=!peek && counter && (raw&127)==0x73 &&
        (funct==1 || funct==2 || funct==3 || funct==5 || funct==6 || funct==7) && (raw>>20)==unsigned(which);
    const char* phase="model_instruction_completion_get_csr";
    if (instruction_counter_read && cfg->iris_vme) {
      if (!cfg->iris_timing_fixture.empty()) {
        // The completion timestamp denotes the modeled retirement edge. Read
        // its pre-update counter state, then apply any explicit CSR write at
        // that edge. The global/device clock itself remains unchanged.
        const auto sample=sim->iris_mcycle_pre_edge(id);
        if (!sample) throw std::runtime_error("IRIS_COUNTER_READ_PRE_EDGE_SNAPSHOT_UNAVAILABLE");
        if (which==CSR_MCYCLE || which==CSR_CYCLE) {
          value=*sample;
        }
        phase="model_retirement_edge_pre_update";
      }
    }
    // Validate/buffer the actual instruction context before applying any
    // source-specific rewrite. Trapping instructions discard this buffer.
    if (instruction_counter_read)
      sim->iris_counter_read(id,state.pc,raw,which,value,insn.rd(),phase);
    if (instruction_counter_read && cfg->iris_vme) {
      // Shuttle does not rewrite zero-field S/C to CSR.R. CSRFile writes
      // these writable counters back, overriding the same edge's increment.
      // Do not generalize this to read-only aliases or other CSR side effects.
      if (id<2 && (which==CSR_MCYCLE || which==CSR_MINSTRET) && insn.rs1()==0 &&
          (funct==2 || funct==3 || funct==6 || funct==7))
        put_csr(which,value);
    }
    return value;
  }
  // If we get here, the CSR doesn't exist.  Unimplemented CSRs always throw
  // illegal-instruction exceptions, not virtual-instruction exceptions.
  throw trap_illegal_instruction(insn.bits());
}

const insn_desc_t insn_desc_t::illegal_instruction = {
  0, 0,
  &::illegal_instruction, &::illegal_instruction, &::illegal_instruction, &::illegal_instruction,
  &::illegal_instruction, &::illegal_instruction, &::illegal_instruction, &::illegal_instruction
};

reg_t illegal_instruction(processor_t UNUSED *p, insn_t insn, reg_t UNUSED pc)
{
  // The illegal instruction can be longer than ILEN bits, where the tval will
  // contain the first ILEN bits of the faulting instruction. We hard-code the
  // ILEN to 32 bits since all official instructions have at most 32 bits.
  throw trap_illegal_instruction(insn.bits() & 0xffffffffULL);
}

reg_t processor_t::throw_instruction_address_misaligned(reg_t pc)
{
  throw trap_instruction_address_misaligned(state.v, pc, 0, 0);
}

insn_func_t processor_t::decode_insn(insn_t insn)
{
  const auto& pool = opcode_map[insn.bits() % std::size(opcode_map)];

  for (auto p = pool.begin(); ; ++p) {
    if ((insn.bits() & p->mask) == p->match) {
      return p->func;
    }
  }
}

void processor_t::register_insn(insn_desc_t desc, std::vector<insn_desc_t>& pool) {
  assert(desc.fast_rv32i && desc.fast_rv64i && desc.fast_rv32e && desc.fast_rv64e &&
         desc.logged_rv32i && desc.logged_rv64i && desc.logged_rv32e && desc.logged_rv64e);

  pool.push_back(desc);
}

void processor_t::build_opcode_map()
{
  bool rve = extension_enabled('E');
  bool zca = extension_enabled(EXT_ZCA);
  const size_t N = std::size(opcode_map);

  auto build_one = [&](const insn_desc_t& desc) {
    auto func = desc.func(xlen, rve, log_commits_enabled);
    if (!zca && insn_length(desc.match) % 4)
      func = &::illegal_instruction;

    auto stride = std::min(N, size_t(1) << ctz(~desc.mask));
    for (size_t i = desc.match & (stride - 1); i < N; i += stride) {
      if ((desc.match % N) == (i & desc.mask))
        opcode_map[i].push_back({desc.match, desc.mask, func});
    }
  };

  for (auto& p : opcode_map)
    p.clear();

  for (auto& d : custom_instructions)
    build_one(d);

  for (auto& d : instructions)
    build_one(d);
}

void processor_t::register_extension(extension_t *x) {
  for (auto insn : x->get_instructions(*this))
    register_custom_insn(insn);
  build_opcode_map();

  for (auto disasm_insn : x->get_disasms(this))
    disassembler->add_insn(disasm_insn);

  if (!custom_extensions.insert(std::make_pair(x->name(), x)).second) {
    fprintf(stderr, "extensions must have unique names (got two named \"%s\"!)\n", x->name());
    abort();
  }
}

void processor_t::register_base_instructions()
{
  #define DECLARE_INSN(name, match, mask) \
    insn_bits_t name##_match = (match), name##_mask = (mask); \
    isa_extension_t name##_ext = NUM_ISA_EXTENSIONS; \
    bool name##_overlapping = false;

  #include "encoding.h"
  #undef DECLARE_INSN

  #define DEFINE_INSN(name) \
    extern reg_t fast_rv32i_##name(processor_t*, insn_t, reg_t); \
    extern reg_t fast_rv64i_##name(processor_t*, insn_t, reg_t); \
    extern reg_t fast_rv32e_##name(processor_t*, insn_t, reg_t); \
    extern reg_t fast_rv64e_##name(processor_t*, insn_t, reg_t); \
    extern reg_t logged_rv32i_##name(processor_t*, insn_t, reg_t); \
    extern reg_t logged_rv64i_##name(processor_t*, insn_t, reg_t); \
    extern reg_t logged_rv32e_##name(processor_t*, insn_t, reg_t); \
    extern reg_t logged_rv64e_##name(processor_t*, insn_t, reg_t);
  #include "insn_list.h"
  #undef DEFINE_INSN

  #define DEFINE_INSN_UNCOND(name) { \
    insn_desc_t insn = { \
      name##_match, \
      name##_mask, \
      fast_rv32i_##name, \
      fast_rv64i_##name, \
      fast_rv32e_##name, \
      fast_rv64e_##name, \
      logged_rv32i_##name, \
      logged_rv64i_##name, \
      logged_rv32e_##name, \
      logged_rv64e_##name \
    }; \
    register_base_insn(insn); \
  }

  // add overlapping instructions first, in order
  #define DECLARE_OVERLAP_INSN(name, ext) \
    name##_overlapping = true; \
    if (isa.extension_enabled(ext)) \
      DEFINE_INSN_UNCOND(name);
  #define DECLARE_OVERLAP_INSN_RV64(name, ext) \
    name##_overlapping = true; \
    if (isa.extension_enabled(ext) && xlen == 64) \
      DEFINE_INSN_UNCOND(name);
  #include "overlap_list.h"
  #undef DECLARE_OVERLAP_INSN
  #undef DECLARE_OVERLAP_INSN_RV64

  // add all other instructions.  since they are non-overlapping, the order
  // does not affect correctness, but more frequent instructions should
  // appear earlier to improve search time on opcode_cache misses.
  #define DEFINE_INSN(name) \
    if (!name##_overlapping) \
      DEFINE_INSN_UNCOND(name);
  #include "insn_list.h"
  #undef DEFINE_INSN
  #undef DEFINE_INSN_UNCOND

  // terminate instruction list with a catch-all
  register_base_insn(insn_desc_t::illegal_instruction);

  build_opcode_map();
}

bool processor_t::load(reg_t addr, size_t len, uint8_t* bytes)
{
  switch (addr)
  {
    case 0:
      if (len <= 4) {
        memset(bytes, 0, len);
        bytes[0] = get_field(state.mip->read(), MIP_MSIP);
        return true;
      }
      break;
  }

  return false;
}

bool processor_t::store(reg_t addr, size_t len, const uint8_t* bytes)
{
  switch (addr)
  {
    case 0:
      if (len <= 4) {
        state.mip->write_with_mask(MIP_MSIP, bytes[0] << IRQ_M_SOFT);
        return true;
      }
      break;
  }

  return false;
}

reg_t processor_t::size()
{
  return PGSIZE;
}

void processor_t::trigger_updated(const std::vector<triggers::trigger_t *> &triggers)
{
  mmu->flush_tlb();
  mmu->check_triggers_fetch = false;
  mmu->check_triggers_load = false;
  mmu->check_triggers_store = false;
  check_triggers_icount = false;

  for (auto trigger : triggers) {
    if (trigger->get_execute()) {
      mmu->check_triggers_fetch = true;
    }
    if (trigger->get_load()) {
      mmu->check_triggers_load = true;
    }
    if (trigger->get_store()) {
      mmu->check_triggers_store = true;
    }
    if (trigger->icount_check_needed()) {
      check_triggers_icount = true;
    }
  }
}
