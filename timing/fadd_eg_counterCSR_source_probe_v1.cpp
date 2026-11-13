#include "VShuttleLSUPhase.h"
#include "VShuttleLSUPhase___024root.h"
#include "verilated.h"
#include <iostream>
#include <vector>
#include <stdexcept>
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
int main(){try{for(unsigned seed:{1U,17U})for(unsigned csr:{0xb00U,0xb02U,0xc00U,0xc02U})for(unsigned form:{2U,3U,6U,7U}){
 VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);VShuttleLSUPhase m(&context);
 #include "initialize.hpp"
 m.io_dmem_req_ready=1;m.io_dmem_ordered=1;m.io_vector_ex_ready=1;m.io_vector_com_scalar_check_ready=1;m.io_ptw_tlb_req_ready=1;
 auto edge=[&]{m.clock=0;m.eval();m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;for(unsigned i=0;i<10;++i)edge();m.reset=0;
 // Only actual top-level backend/trap-check signals are driven. No RF, CSR,
 // readiness, decoder or queue state is injected. This is a conditional Core
 // port-contract witness, not a whole-Saturn numerical execution claim.
 std::vector<uint32_t>code={(csr<<20)|(form<<12)|(10u<<7)|0x73,0x0330000f,(csr<<20)|(2u<<12)|(11u<<7)|0x73,0x00000013};
 unsigned next=0,counterRRD=~0u,counterCOM=~0u,fenceRRD=~0u,fenceCOM=~0u,afterCOM=~0u,blocked=0;
 for(unsigned cycle=0;cycle<100;++cycle){
  m.io_vector_backend_busy=cycle<50;m.io_vector_trap_check_busy=cycle<50;
  m.io_imem_resp_0_valid=next<code.size();m.io_imem_resp_1_valid=0;
  if(next<code.size()){m.io_imem_resp_0_bits_inst=code[next];m.io_imem_resp_0_bits_raw_inst=code[next];m.io_imem_resp_0_bits_pc=0x80000000ULL+4*next;m.io_imem_resp_0_bits_mem_size=0;}
  m.clock=0;m.eval();bool accept=m.io_imem_resp_0_valid&&m.io_imem_resp_0_ready;
  if(accept&&next==0)counterRRD=cycle;
  if(next==1&&cycle<50){need(!accept,"FENCE must remain blocked by live vector port busy");++blocked;}
  if(accept&&next==1)fenceRRD=cycle;
  for(unsigned lane=0;lane<2;++lane){bool retire=lane?m.io_trace_core_ingress_group_1_iretire:m.io_trace_core_ingress_group_0_iretire;auto pc=lane?m.io_trace_core_ingress_group_1_iaddr:m.io_trace_core_ingress_group_0_iaddr;
   if(retire&&pc==0x80000000)counterCOM=cycle;
   if(retire&&pc==0x80000004)fenceCOM=cycle;
   if(retire&&pc==0x80000008)afterCOM=cycle;
  }
  m.clock=1;m.eval();m.clock=0;m.eval();if(accept)++next;
 }
 need(counterRRD==0&&counterCOM<50&&fenceRRD==50&&fenceCOM==fenceRRD+3&&afterCOM>fenceCOM&&blocked>40,"Counter overlap / source FENCE release / counter order");
 auto*r=m.rootp;auto before=r->ShuttleCore__DOT__iregfile_10,after=r->ShuttleCore__DOT__iregfile_11;need(after>before,"Actual source counter result progresses across fence wait");
 std::cout<<"{\"seed\":"<<seed<<",\"csr\":"<<csr<<",\"form\":"<<form<<",\"counter_RRD\":"<<counterRRD<<",\"counter_COM\":"<<counterCOM<<",\"FENCE_RRD\":"<<fenceRRD<<",\"FENCE_COM\":"<<fenceCOM<<",\"after_counter_COM\":"<<afterCOM<<",\"before\":"<<before<<",\"after\":"<<after<<",\"injected_internal_state\":false,\"pass\":true}\n";
 }return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
