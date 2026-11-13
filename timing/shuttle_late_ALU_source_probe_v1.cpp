#include "VShuttleLSUPhase.h"
#include "VShuttleLSUPhase___024root.h"
#include "verilated.h"
#include <iostream>
#include <vector>
#include <deque>
#include <stdexcept>
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Reply{unsigned due,tag;uint64_t data;};
int main(){try{for(unsigned seed:{1U,17U})for(unsigned mode=0;mode<3;++mode){
 VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);VShuttleLSUPhase m(&context);
 #include "initialize.hpp"
 m.io_dmem_req_ready=1;m.io_dmem_ordered=1;m.io_vector_ex_ready=1;m.io_vector_com_scalar_check_ready=1;m.io_ptw_tlb_req_ready=1;
 auto edge=[&]{m.clock=0;m.eval();m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;for(unsigned i=0;i<10;++i)edge();m.reset=0;
 // Actual instructions establish all read operands. No RF/RTL state injection.
 const unsigned rd=mode==2?11:13;
 std::vector<uint32_t>code={0x00100513,0x01f51513,0x00500613,0x00000013};
 code.push_back(0x00053583); // LD x11,0(x10)
 code.push_back(mode==0?0x00358693:((12u<<20)|(11u<<15)|(rd<<7)|0x33)); // ADDI x13,x11,3 or ADD rd,x11,x12
 code.push_back((rd<<15)|(1u<<20)|(14u<<7)|0x13);code.push_back(0x00000013);
 std::deque<Reply>q;unsigned next=0,req=~0u,loadCOM=~0u,aluCOM=~0u,wb=~0u,dependentRRD=~0u;uint64_t data=0x123456789ULL;unsigned pairRRD=~0u;bool same=false;const uint64_t expected=data+(mode==0?3:5);
 for(unsigned cycle=0;cycle<100;++cycle){
  m.io_imem_resp_0_valid=next<code.size();m.io_imem_resp_1_valid=next+1<code.size();
  auto drive=[&](unsigned l,unsigned n){if(l){m.io_imem_resp_1_bits_inst=code[n];m.io_imem_resp_1_bits_raw_inst=code[n];m.io_imem_resp_1_bits_pc=0x80000000ULL+n*4;m.io_imem_resp_1_bits_mem_size=3;}else{m.io_imem_resp_0_bits_inst=code[n];m.io_imem_resp_0_bits_raw_inst=code[n];m.io_imem_resp_0_bits_pc=0x80000000ULL+n*4;m.io_imem_resp_0_bits_mem_size=3;}};
  if(next<code.size())drive(0,next);if(next+1<code.size())drive(1,next+1);
  bool response=!q.empty()&&q.front().due==cycle;m.io_dmem_resp_valid=response;m.io_dmem_s2_hit=response;m.io_dmem_resp_bits_has_data=response;m.io_dmem_resp_bits_tag=response?q.front().tag:0;m.io_dmem_resp_bits_data=response?q.front().data:0;m.io_dmem_resp_bits_size=3;m.clock=0;m.eval();auto*r=m.rootp;
  unsigned accept=(m.io_imem_resp_0_valid&&m.io_imem_resp_0_ready)+(m.io_imem_resp_1_valid&&m.io_imem_resp_1_ready);
  if(accept&&next==4){pairRRD=cycle;same=accept==2&&r->ShuttleCore__DOT__rrd_uops_1_bits_uses_latealu;need(same,"Actual dual-lane lateALU admission");}
  if(accept&&next<=6&&next+accept>6)dependentRRD=cycle;
  if(m.io_dmem_req_valid&&m.io_dmem_req_ready){need(req==~0u&&m.io_dmem_req_bits_addr==0x80000000ULL,"Actual load request identity");req=cycle;q.push_back({cycle+2,m.io_dmem_req_bits_tag,data});}
  for(unsigned lane=0;lane<2;++lane){bool retire=lane?m.io_trace_core_ingress_group_1_iretire:m.io_trace_core_ingress_group_0_iretire;auto pc=lane?m.io_trace_core_ingress_group_1_iaddr:m.io_trace_core_ingress_group_0_iaddr;if(retire&&pc==0x80000010)loadCOM=cycle;if(retire&&pc==0x80000014){aluCOM=cycle;need(!r->ShuttleCore__DOT__com_bypasses_1_can_bypass,"Late result cannot bypass at COM");}}
  if(r->ShuttleCore__DOT__wb_uops_reg_1_valid&&r->ShuttleCore__DOT__wb_uops_reg_1_bits_pc==0x80000014){wb=cycle;need(r->ShuttleCore__DOT__wb_bypasses_1_can_bypass&&r->ShuttleCore__DOT__wb_bypasses_1_data==expected,"Actual WB ALU result and bypass");need(r->ShuttleCore__DOT__wb_uops_reg_1_bits_rs1_data==data,"Load reply captured at COM for WB operand");}
  m.clock=1;m.eval();m.clock=0;m.eval();next+=accept;if(response)q.pop_front();
 }
 need(same&&req==pairRRD+1&&loadCOM==req+2&&aluCOM==loadCOM&&wb==aluCOM+1,"Source RRD EX COM WB edges");need(dependentRRD==wb,"Earliest dependent RRD at WB bypass edge");auto*r=m.rootp;need(r->ShuttleCore__DOT__iregfile_14==expected+1,"Independent source RF readback");
 std::cout<<"{\"seed\":"<<seed<<",\"mode\":"<<mode<<",\"RRD\":"<<pairRRD<<",\"load_EX\":"<<req<<",\"load_COM\":"<<loadCOM<<",\"ALU_COM\":"<<aluCOM<<",\"ALU_WB\":"<<wb<<",\"dependent_RRD\":"<<dependentRRD<<",\"WB_value\":"<<expected<<",\"RF_dependent_value\":"<<(expected+1)<<",\"state_injected\":false,\"pass\":true}\n";
 }return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
