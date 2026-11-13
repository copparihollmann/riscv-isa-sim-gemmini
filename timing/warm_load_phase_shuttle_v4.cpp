#include "VShuttleLSUPhase.h"
#include "verilated.h"
#include <array>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <vector>
void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Reply{unsigned due,tag;uint64_t value;};
int main(){try{for(unsigned seed:{1U,17U}){
 VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);VShuttleLSUPhase m(&context);
 #include "initialize.hpp"
 m.io_dmem_req_ready=1;m.io_dmem_ordered=1;m.io_vector_ex_ready=1;m.io_vector_com_scalar_check_ready=1;m.io_ptw_tlb_req_ready=1;
 auto edge=[&]{m.clock=0;m.eval();m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;for(unsigned i=0;i<10;++i)edge();m.reset=0;
 std::vector<uint32_t>code={0x00100513,0x01f51513};for(unsigned i=0;i<16;++i){code.push_back(0x00053503);code.push_back(0x00050293);}
 unsigned next=0;std::deque<Reply>q;std::vector<unsigned>requests,responses,retires,alu_retires;uint64_t next_address=0x80000000ULL;
 for(unsigned cycle=0;cycle<180;++cycle){
  m.io_imem_resp_0_valid=next<code.size();if(next<code.size()){m.io_imem_resp_0_bits_inst=code[next];m.io_imem_resp_0_bits_raw_inst=code[next];m.io_imem_resp_0_bits_pc=0x80000000ULL+next*4;m.io_imem_resp_0_bits_mem_size=3;}
  m.io_imem_resp_1_valid=next+1<code.size();if(next+1<code.size()){m.io_imem_resp_1_bits_inst=code[next+1];m.io_imem_resp_1_bits_raw_inst=code[next+1];m.io_imem_resp_1_bits_pc=0x80000000ULL+(next+1)*4;m.io_imem_resp_1_bits_mem_size=3;}
  const bool response=!q.empty()&&q.front().due==cycle;m.io_dmem_resp_valid=response;m.io_dmem_s2_hit=response;m.io_dmem_resp_bits_has_data=response;m.io_dmem_resp_bits_tag=response?q.front().tag:0;m.io_dmem_resp_bits_data=response?q.front().value:0;m.io_dmem_resp_bits_size=3;
  m.clock=0;m.eval();unsigned accept=(m.io_imem_resp_0_valid&&m.io_imem_resp_0_ready)+(m.io_imem_resp_1_valid&&m.io_imem_resp_1_ready);if(accept){std::cout<<"RRD {\"seed\":"<<seed<<",\"edge\":"<<cycle<<",\"pc\":"<<(0x80000000ULL+next*4)<<",\"count\":"<<accept<<"}\n";}
  if(m.io_dmem_req_valid&&m.io_dmem_req_ready){need(m.io_dmem_req_bits_cmd==0&&m.io_dmem_req_bits_addr==next_address,"Actual dependent pointer address");need(m.io_dmem_req_bits_tag==20,"Actual x10 source tag");requests.push_back(cycle);q.push_back({cycle+2,20,next_address+8});std::cout<<"REQ {\"seed\":"<<seed<<",\"ordinal\":"<<requests.size()-1<<",\"edge\":"<<cycle<<",\"address\":"<<next_address<<"}\n";next_address+=8;}
  if(response){responses.push_back(cycle);std::cout<<"RESP {\"seed\":"<<seed<<",\"ordinal\":"<<responses.size()-1<<",\"edge\":"<<cycle<<",\"data\":"<<q.front().value<<"}\n";}
  for(unsigned lane=0;lane<2;++lane){auto valid=lane?m.io_trace_core_ingress_group_1_iretire:m.io_trace_core_ingress_group_0_iretire;auto pc=lane?m.io_trace_core_ingress_group_1_iaddr:m.io_trace_core_ingress_group_0_iaddr;if(valid&&pc>=0x80000008ULL&&pc<0x80000088ULL){if(((pc-0x80000008ULL)/4)%2)alu_retires.push_back(cycle);else retires.push_back(cycle);std::cout<<"COM {\"seed\":"<<seed<<",\"pc\":"<<pc<<",\"edge\":"<<cycle<<"}\n";}}
  m.clock=1;m.eval();m.clock=0;m.eval();next+=accept;if(response)q.pop_front();
 }
 need(next==34&&requests.size()==responses.size()&&requests.size()==retires.size()&&requests.size()==16&&alu_retires.size()==16,"All16 load requests/responses/retirements");for(unsigned i=0;i<16;++i){need(responses[i]==requests[i]+2,"Source cache-hit2edge contract");need(retires[i]==responses[i],"Hit response supplies COM samepreedge");need(alu_retires[i]==requests[i]+(i?5:2),"First samepacket lateALU retires atloadCOM; laterALUcoissuesnextLD afterCOMbypass");if(i)need(requests[i]==requests[i-1]+3,"Continuousdual-lanehitLD nextEX3");}
 std::cout<<"CASE {\"seed\":"<<seed<<",\"requests\":16,\"source_hit_response_latency\":2,\"steady_ordinary_ALU_EX_minus_load_EX\":3,\"next_EX_after_response\":1,\"physical_request_and_COM_observed\":true,\"RTLstate_injected\":false}\n";
 }std::cout<<"DONE passed\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
