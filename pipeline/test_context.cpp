// Native guards on the actual isolated processor, with no guest/hardware timing claim.
#include "processor.h"
#include "simif.h"
#include "encoding.h"
#include "debug_defines.h"
#include "mmu.h"
#include "trap.h"
#include <array>
#include <cassert>
#include <cstring>
#include <iostream>
#include <limits>

struct fixture_sim final : simif_t {
  cfg_t cfg;
  std::map<size_t,processor_t*> harts;
  std::array<unsigned char,8> bytes{};
  std::array<unsigned char,4096> page_a{},padding{},page_b{};
  static constexpr reg_t base=0x80000000;
  static constexpr reg_t split_base=0x90000000;
  char* addr_to_mem(reg_t address) override {
    if (address>=split_base && address<split_base+4096)return reinterpret_cast<char*>(page_a.data()+address-split_base);
    if (address>=split_base+4096 && address<split_base+8192)return reinterpret_cast<char*>(page_b.data()+address-split_base-4096);
    return address>=base && address<base+bytes.size() ? reinterpret_cast<char*>(bytes.data()+address-base) : nullptr;
  }
  bool mmio_load(reg_t,size_t,uint8_t*) override {return false;}
  bool mmio_store(reg_t,size_t,const uint8_t*) override {return false;}
  void proc_reset(unsigned) override {}
  const cfg_t& get_cfg() const override {return cfg;}
  const std::map<size_t,processor_t*>& get_harts() const override {return harts;}
  const char* get_symbol(uint64_t) override {return nullptr;}
};

int main() {
  fixture_sim sim;
  processor_t p("rv64imac_zicsr", "MSU", &sim.cfg, &sim, 0, false, nullptr, std::cerr);
  sim.harts[0]=&p;
  auto* s=p.get_state();
  assert(p.iris_pipeline_context_safe());
  uint32_t addi=0x001e0e13;
  std::memcpy(sim.bytes.data(),&addi,sizeof addi);
  assert(p.iris_pipeline_can_prefetch(sim.base));
  assert(!p.iris_pipeline_can_prefetch(sim.base+1));
  assert(!p.iris_pipeline_can_prefetch(sim.base+6));
  assert(!p.iris_pipeline_can_prefetch(sim.base+8));
  assert(!p.iris_pipeline_can_prefetch(std::numeric_limits<reg_t>::max()-1));
  std::memcpy(sim.page_a.data()+4094,&addi,2);std::memcpy(sim.page_b.data(),reinterpret_cast<char*>(&addi)+2,2);
#ifdef IRIS_TEST_SPLIT_FETCH
  assert(sim.addr_to_mem(sim.split_base+4096)!=sim.addr_to_mem(sim.split_base+4095)+1);
  assert(!p.iris_pipeline_can_prefetch(sim.split_base+4094,true));
  assert(p.iris_pipeline_can_prefetch(sim.split_base+4094,true,true));
  auto split=p.get_mmu()->load_insn(sim.split_base+4094);assert(uint32_t(split.insn.bits())==addi);
  sim.page_b[4094]=0x13;sim.page_b[4095]=0;
  assert(!p.iris_pipeline_can_prefetch(sim.split_base+8190,true,true));
#endif
  sim.bytes[0]=1; sim.bytes[1]=0; // C.NOP is a serialized boundary.
  assert(!p.iris_pipeline_can_prefetch(sim.base));
#ifdef IRIS_TEST_RVC
  assert(p.iris_pipeline_can_prefetch(sim.base,true));
  sim.bytes[6]=1;sim.bytes[7]=0;
  assert(p.iris_pipeline_can_prefetch(sim.base+6,true));
  assert(!p.iris_pipeline_can_prefetch(sim.base+8,true));
  processor_t noc("rv64ima_zicsr", "MSU", &sim.cfg, &sim, 2, false, nullptr, std::cerr);
  assert(!noc.iris_pipeline_can_prefetch(sim.base,true));
#endif
  s->prv=PRV_S; assert(!p.iris_pipeline_context_safe()); s->prv=PRV_M;
  s->v=true; assert(!p.iris_pipeline_context_safe()); s->v=false;
  s->debug_mode=true; assert(!p.iris_pipeline_context_safe()); s->debug_mode=false;
  s->single_step=state_t::STEP_STEPPING; assert(!p.iris_pipeline_context_safe()); s->single_step=state_t::STEP_NONE;
  p.set_debug(true); assert(!p.iris_pipeline_context_safe()); p.set_debug(false);
  p.halt_request=processor_t::HR_REGULAR; assert(!p.iris_pipeline_context_safe()); p.halt_request=processor_t::HR_NONE;
  s->csrmap.at(CSR_TDATA1)->write((reg_t(3)<<60)|CSR_ICOUNT_M|(reg_t(9)<<CSR_ICOUNT_COUNT_OFFSET));
  assert(!p.iris_pipeline_context_safe());
  s->csrmap.at(CSR_TDATA1)->write(0);
  s->csrmap.at(CSR_TDATA1)->write((reg_t(2)<<60)|CSR_MCONTROL_M|CSR_MCONTROL_EXECUTE);
  assert(p.get_mmu()->iris_execute_trigger_enabled() && !p.iris_pipeline_context_safe());
  s->csrmap.at(CSR_TDATA1)->write(0);
  assert(!p.get_mmu()->iris_execute_trigger_enabled());
  assert(p.iris_pipeline_context_safe());
  const reg_t pc=s->pc;
  s->in_wfi=true;
  s->mie->write(MIP_MSIP);
  s->mip->backdoor_write_with_mask(MIP_MSIP,MIP_MSIP);
  s->mstatus->write(s->mstatus->read()&~MSTATUS_MIE);
  assert(!p.iris_pipeline_interrupt_exception());
  assert(s->in_wfi && s->pc==pc);
  s->mstatus->write(s->mstatus->read()|MSTATUS_MIE);
  auto captured=p.iris_pipeline_interrupt_exception();
  assert(captured && s->in_wfi && s->pc==pc && (s->mip->read()&MIP_MSIP));
  s->mip->backdoor_write_with_mask(MIP_MSIP,0);
  bool caught=false;
  try {std::rethrow_exception(captured);}
  catch(trap_t& t) {caught=true;assert(t.cause()==((reg_t(1)<<63)|3));}
  assert(caught && s->pc==pc);
  processor_t rv32("rv32imac_zicsr", "MSU", &sim.cfg, &sim, 1, false, nullptr, std::cerr);
  assert(!rv32.iris_pipeline_context_safe());
  std::cout<<"PASS actual processor context/prefetch/latched-interrupt guards\n";
}
