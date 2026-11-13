#include "VShuttleLSUPhase.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <optional>
#include <stdexcept>
void need(bool v,const char*s){if(!v)throw std::runtime_error(s);}
int main(){try{for(unsigned seed:{1U,17U,31U})for(unsigned mask=0;mask<8;++mask){
 VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);const char*args[]={"opu-fence-source"};context.commandArgs(1,args);Verilated::threadContextp(&context);VShuttleLSUPhase m(&context);
 #include "initialize.hpp"
 m.io_dmem_req_ready=1;m.io_dmem_ordered=1;m.io_vector_ex_ready=1;m.io_vector_com_scalar_check_ready=1;m.io_ptw_tlb_req_ready=1;
 auto edge=[&]{Verilated::threadContextp(&context);m.clock=0;m.eval();m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;for(unsigned i=0;i<10;++i)edge();m.reset=0;
 const std::array<unsigned,4>code={0x00000013,0x00000013,0x0ff0000f,0x00100513};unsigned next=0;std::optional<unsigned>accept,retire;unsigned expected=12;
 if(mask&1)expected=20;if(mask&2)expected=22;if(mask&4)expected=24;
 for(unsigned cycle=0;cycle<48;++cycle){
  m.io_vector_backend_busy=(mask&1)&&cycle<20;m.io_vector_trap_check_busy=(mask&2)&&cycle<22;m.io_dmem_ordered=!((mask&4)&&cycle<24);
  m.io_imem_resp_0_valid=next<code.size()&&(next!=2||cycle>=12);if(next<code.size()){m.io_imem_resp_0_bits_inst=code[next];m.io_imem_resp_0_bits_raw_inst=code[next];m.io_imem_resp_0_bits_pc=0x80000000ULL+next*4;}
  m.clock=0;m.eval();const bool fire=m.io_imem_resp_0_valid&&m.io_imem_resp_0_ready;
  if(fire&&next==2){need(!accept,"duplicate FENCE RRD");accept=cycle;need(!m.io_vector_backend_busy&&!m.io_vector_trap_check_busy&&m.io_dmem_ordered,"FENCE accepted despite source busy");}
  for(unsigned lane=0;lane<2;++lane){auto valid=lane?m.io_trace_core_ingress_group_1_iretire:m.io_trace_core_ingress_group_0_iretire;auto pc=lane?m.io_trace_core_ingress_group_1_iaddr:m.io_trace_core_ingress_group_0_iaddr;if(valid&&pc==0x80000008ULL){need(!retire,"duplicate FENCE COM");retire=cycle;}}
  m.clock=1;m.eval();m.clock=0;m.eval();if(fire)++next;
 }
 need(accept&&retire&&*accept==expected&&*retire==*accept+3&&next==code.size(),"source FENCE phase predicate mismatch");
 std::cout<<"{\"seed\":"<<seed<<",\"external_busy_mask\":"<<mask<<",\"canonical_fence\":267386895,\"RRD\":"<<*accept<<",\"COM\":"<<*retire<<",\"input_mode\":\"actual_Core_physical_unit_busy_and_DCache_ordered_boundary\"}\n";
}std::cout<<"{\"status\":\"passed\",\"runs\":24,\"RTL_state_injection\":false,\"whole_CPU_VU_loop_certified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
