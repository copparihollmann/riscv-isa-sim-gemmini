// Actual processor catch-path regression, using an isolated in-memory simif.
// No Iris RAM/VRF definedness policy or target timing costs are changed.
#include "processor.h"
#include "simif.h"
#include "csrs.h"
#include "encoding.h"
#include "debug_defines.h"
#include <array>
#include <cstring>
#include <iostream>
#include <map>
#include <stdexcept>

namespace {
constexpr reg_t code_base = 0x80000000;
class Fixture : public simif_t {
 public:
  cfg_t cfg;
  std::array<char,4096> code{};
  std::array<char,4096> debug{};
  std::map<size_t,processor_t*> harts;
  bool wait = false;
  Fixture() {
    cfg.isa = "rv64imac_zicsr_zifencei";
    cfg.iris_timing_fixture = "step-outcome-unit-test"; // select the actual slow catch loop
    for (size_t off=0;off<4096;off+=4) {
      const uint32_t nop = 0x13;
      std::memcpy(code.data()+off,&nop,4);
      std::memcpy(debug.data()+off,&nop,4);
    }
  }
  char* addr_to_mem(reg_t p) override {
    if (p>=code_base && p<code_base+code.size()) return code.data()+p-code_base;
    if (p>=DEBUG_ROM_ENTRY && p<DEBUG_ROM_ENTRY+debug.size()) return debug.data()+p-DEBUG_ROM_ENTRY;
    return nullptr;
  }
  bool mmio_load(reg_t,size_t,uint8_t*) override { return false; }
  bool mmio_store(reg_t,size_t,const uint8_t*) override { return false; }
  void proc_reset(unsigned) override {}
  const cfg_t& get_cfg() const override { return cfg; }
  const std::map<size_t,processor_t*>& get_harts() const override { return harts; }
  const char* get_symbol(uint64_t) override { return nullptr; }
  void iris_issue(unsigned,reg_t,const insn_fetch_t&) override {
    if (wait) throw iris_timing_wait{};
  }
  void word(uint32_t bits) { std::memcpy(code.data(),&bits,4); }
};
void require(bool value,const char* message) {
  if (!value) throw std::runtime_error(message);
}
struct Core {
  Fixture fixture;
  processor_t p;
  Core() : p(fixture.cfg.isa,"M",&fixture.cfg,&fixture,0,false,nullptr,std::cerr) {
    fixture.harts[0]=&p;
    p.get_state()->pc=code_base;
    p.put_csr(CSR_MTVEC,code_base+0x100);
  }
};
void architectural(Core& c,reg_t cause,const char* name) {
  c.p.step(1);
  require(!c.p.iris_step_timing_waited(),"architectural event mislabeled timing wait");
  require(c.p.iris_step_architectural_event(),"architectural event outcome missing");
  require(c.p.get_state()->mcause->read()==cause,"wrong architectural cause");
  require(c.p.get_state()->pc==code_base+0x100,"trap vector was not entered");
  std::cout << "STEP_OUTCOME " << name << " pass\n";
}
}
int main() {
  try {
    {
      Core c;c.fixture.wait=true;c.p.step(1);
      require(c.p.iris_step_timing_waited(),"timing wait outcome missing");
      require(!c.p.iris_step_architectural_event(),"timing wait became architectural event");
      require(c.p.get_state()->pc==code_base,"timing wait changed PC");
      c.fixture.wait=false;c.p.step(1);
      require(!c.p.iris_step_timing_waited()&&!c.p.iris_step_architectural_event(),"step outcomes did not reset");
      require(c.p.get_state()->pc==code_base+4,"retry did not execute original instruction");
      std::cout << "STEP_OUTCOME timing_wait_and_retry pass\n";
    }
    {Core c;c.fixture.word(0);architectural(c,CAUSE_ILLEGAL_INSTRUCTION,"illegal_instruction");}
    {Core c;c.fixture.word(0x00053283);c.p.get_state()->XPR.write(10,0x30000000);architectural(c,CAUSE_LOAD_ACCESS,"load_access_fault");}
    {Core c;c.p.put_csr(CSR_MIE,MIP_MSIP);c.p.put_csr(CSR_MSTATUS,MSTATUS_MIE);c.p.get_state()->mip->backdoor_write_with_mask(MIP_MSIP,MIP_MSIP);architectural(c,(reg_t(1)<<63)|IRQ_M_SOFT,"software_interrupt");}
    {
      Core c;c.fixture.word(0x00100073);c.p.get_state()->dcsr->ebreakm=true;c.p.step(1);
      require(!c.p.iris_step_timing_waited()&&c.p.iris_step_architectural_event(),"debug catch outcome missing");
      require(c.p.get_state()->debug_mode,"EBREAK did not enter debug");
      std::cout << "STEP_OUTCOME debug_entry pass\n";
    }
    {
      Core c;
      c.p.put_csr(CSR_TSELECT,0);c.p.put_csr(CSR_TDATA2,code_base);
      c.p.put_csr(CSR_TDATA1,(reg_t(2)<<60)|CSR_MCONTROL_M|CSR_MCONTROL_EXECUTE);
      architectural(c,CAUSE_BREAKPOINT,"execute_trigger");
    }
    std::cout << "STEP_OUTCOME DONE 6\n";
    return 0;
  } catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
