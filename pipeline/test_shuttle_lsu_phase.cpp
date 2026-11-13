#include "VShuttleLSUPhase.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <vector>
void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
int main(){try{for(unsigned seed:{1U,17U})for(bool discard:{false,true}){
 VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);VShuttleLSUPhase m(&context);
 #include "initialize.hpp"
 m.io_dmem_req_ready=1;m.io_dmem_ordered=1;m.io_vector_ex_ready=1;m.io_vector_com_scalar_check_ready=1;m.io_ptw_tlb_req_ready=1;
 auto edge=[&]{m.clock=0;m.eval();m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;for(unsigned i=0;i<10;++i)edge();m.reset=0;
 const std::array<unsigned,6>code={0x00100513,0x01f51513,discard?0x00053003U:0x00053583U,0x00700613,discard?0x00100693U:0x00158693U,0x00d53423};
 unsigned next=0;std::optional<unsigned>load_edge,store_edge,load_retire,independent_retire,dependent_retire,response_edge;bool paddr=false,store_data=false;
 constexpr unsigned delay=40;constexpr uint64_t data=0x123456789abcdef0ULL;
 for(unsigned cycle=0;cycle<160;++cycle){
  m.io_imem_resp_0_valid=next<code.size();if(next<code.size()){m.io_imem_resp_0_bits_inst=code[next];m.io_imem_resp_0_bits_raw_inst=code[next];m.io_imem_resp_0_bits_pc=0x80000000ULL+next*4;m.io_imem_resp_0_bits_mem_size=3;}
  m.io_dmem_resp_valid=load_edge&&cycle==*load_edge+delay;m.io_dmem_resp_bits_has_data=m.io_dmem_resp_valid;m.io_dmem_resp_bits_tag=discard?0:22;m.io_dmem_resp_bits_data=data;m.io_dmem_resp_bits_size=3;
  m.clock=0;m.eval();const bool accept=m.io_imem_resp_0_valid&&m.io_imem_resp_0_ready;
  if(m.io_dmem_req_valid&&m.io_dmem_req_ready){if(m.io_dmem_req_bits_cmd==0){need(!load_edge,"duplicate source load request");need(m.io_dmem_req_bits_addr==0x80000000ULL&&m.io_dmem_req_bits_tag==(discard?0U:22U),"source load address/tag");load_edge=cycle;}else{need(m.io_dmem_req_bits_cmd==1&&!store_edge&&m.io_dmem_req_bits_addr==0x80000008ULL,"source store request");store_edge=cycle;}}
  if(load_edge&&cycle==*load_edge+1){need(m.io_dmem_s1_paddr==0x80000000ULL&&!m.io_dmem_s1_kill,"source S1 physical phase");paddr=true;}
  if(store_edge&&cycle==*store_edge+1){need(m.io_dmem_s1_data_data==(discard?1:data+1)&&m.io_dmem_s1_paddr==0x80000008ULL,"source dependent store S1 value");store_data=true;}
  for(unsigned lane=0;lane<2;++lane){auto valid=lane?m.io_trace_core_ingress_group_1_iretire:m.io_trace_core_ingress_group_0_iretire;auto pc=lane?m.io_trace_core_ingress_group_1_iaddr:m.io_trace_core_ingress_group_0_iaddr;if(valid){if(pc==0x80000008ULL)load_retire=cycle;if(pc==0x8000000cULL)independent_retire=cycle;if(pc==0x80000010ULL)dependent_retire=cycle;}}
  if(m.io_dmem_resp_valid)response_edge=cycle;
  m.clock=1;m.eval();m.clock=0;m.eval();if(accept)++next;
 }
 need(next==code.size()&&load_edge&&load_retire&&independent_retire&&dependent_retire&&response_edge&&store_edge&&paddr&&store_data,"source phase witness incomplete");need(*load_retire<*response_edge&&*independent_retire<*response_edge&&(discard||*dependent_retire>*response_edge),"source early retirement/late dependency ordering");
 std::cout<<"{\"seed\":"<<seed<<",\"discard_x0\":"<<(discard?"true":"false")<<",\"load_request\":"<<*load_edge<<",\"load_COM\":"<<*load_retire<<",\"independent_COM\":"<<*independent_retire<<",\"response\":"<<*response_edge<<",\"dependent_COM\":"<<*dependent_retire<<",\"store_request\":"<<*store_edge<<",\"source_tag\":"<<(discard?0:22)<<",\"late_dependency_value\":"<<(discard?1:data+1)<<"}\n";
}std::cout<<"{\"status\":\"passed_source_ShuttleCore_LSU_phase\",\"RTL_state_or_readiness_injected\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
