#include "VShuttleLSUPhase.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <stdexcept>
static unsigned checks=0;static void need(bool v,const char*s){++checks;if(!v)throw std::runtime_error(s);}
int main(){try{for(unsigned seed:{1U,17U})for(unsigned hart:{0U,1U}){
 VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);VShuttleLSUPhase m(&context);
 #include "initialize.hpp"
 m.io_hartid=hart;m.io_dmem_req_ready=1;m.io_dmem_ordered=1;m.io_vector_ex_ready=1;m.io_vector_com_scalar_check_ready=1;m.io_ptw_tlb_req_ready=1;
 auto edge=[&]{m.clock=0;m.eval();m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;for(unsigned i=0;i<10;++i)edge();m.reset=0;
 const std::array<unsigned,3> code={0x30445073,0x10500073,0x04d00593}; // defined CSRRWI mie=8, WFI, ADDI a1,zero,77
 unsigned next=0,wfi_retire=0,marker_retire=0,stall_edges=0,wake=0;uint64_t idle_cycle=0,postwake_cycle=0;
 for(unsigned cycle=0;cycle<256;++cycle){
  m.io_imem_resp_0_valid=next<code.size();if(next<code.size()){m.io_imem_resp_0_bits_inst=code[next];m.io_imem_resp_0_bits_raw_inst=code[next];m.io_imem_resp_0_bits_pc=0x80000000ULL+4*next;m.io_imem_resp_0_bits_mem_size=3;}
  m.io_interrupts_msip=cycle>=160;m.clock=0;m.eval();bool accept=m.io_imem_resp_0_valid&&m.io_imem_resp_0_ready;const bool redirect=m.io_imem_redirect_val;const auto redirect_pc=m.io_imem_redirect_pc;
  for(unsigned lane=0;lane<2;++lane){bool v=lane?m.io_trace_core_ingress_group_1_iretire:m.io_trace_core_ingress_group_0_iretire;auto pc=lane?m.io_trace_core_ingress_group_1_iaddr:m.io_trace_core_ingress_group_0_iaddr;if(v&&pc==0x80000004)++wfi_retire;if(v&&pc==0x80000008){++marker_retire;wake=cycle;}}
  if(cycle==64)idle_cycle=m.io_trace_core_ingress_time;
  if(cycle>=64&&cycle<160){need(m.io_trace_core_ingress_time==idle_cycle,"mcycle advanced while source WFI stalledCSR");need(!m.io_imem_resp_0_ready,"WFI did not stall source RRD");need(!m.io_dmem_req_valid,"WFI issued a scalar memory request");need(marker_retire==0,"post-WFI instruction retired before local wake");++stall_edges;}
  if(cycle==220)postwake_cycle=m.io_trace_core_ingress_time;
  m.clock=1;m.eval();m.clock=0;m.eval();if(redirect){need(redirect_pc>=0x80000000ULL&&redirect_pc<=0x8000000cULL&&!(redirect_pc&3),"source redirect outside finite physical program");next=(redirect_pc-0x80000000ULL)/4;}else if(accept)++next;
 }
 need(postwake_cycle>idle_cycle,"mcycle did not resume after source MSIP wake");need(wfi_retire==1&&marker_retire==1&&wake>=160&&stall_edges==96,"source WFI/wake witness incomplete");
 std::cout<<"{\"seed\":"<<seed<<",\"hart\":"<<hart<<",\"mcycle_before_idle\":"<<idle_cycle<<",\"mcycle_at_edge220\":"<<postwake_cycle<<",\"mcycle_idle_delta\":0,\"actual_WFI_retirements\":"<<wfi_retire<<",\"idle_RRD_edges\":"<<stall_edges<<",\"MSIP_input_edge\":160,\"post_WFI_marker_retire_edge\":"<<wake<<",\"clock_continued_during_WFI\":true,\"internal_state_or_ready_injected\":false}\n";
 }std::cout<<"{\"pass\":true,\"checks\":"<<checks<<"}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
