#include "VSaturnRocket.h"
#include "VSaturnRocket___024root.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <deque>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include "burst_inputs.hpp"
#define R(x) m.rootp->SaturnRocketUnit__DOT__##x
static void require(bool value,const char*why){if(!value)throw std::runtime_error(why);}
static unsigned reserved(VSaturnRocket&m){
 const unsigned enq=R(vmu__DOT__lifq__DOT__enq_ptr_value),deq=R(vmu__DOT__lifq__DOT__deq_ptr_value);
 return enq==deq?(R(vmu__DOT__lifq__DOT__maybe_full)?32:0):((enq+32-deq)%32);
}
static std::uint8_t pattern(std::uint64_t address){const auto n=address-0x80010000ULL;return (0x5d+13*n+(n>>8))&255;}
struct Reply {unsigned source,size,beat=0,total;std::uint64_t address;};
int main(int argc,char**argv){try{
 if(argc!=3)throw std::invalid_argument("lmul_log2 seed");const unsigned lmul=std::stoul(argv[1]),seed=std::stoul(argv[2]);require(lmul==2||lmul==3,"Only requested LMUL4/8 controls");const unsigned bytes=32u<<lmul,target=4*bytes/32;
 VerilatedContext context;context.threads(1);context.randSeed(seed);context.randReset(2);const char*args[]={"iris-saturn-load-burst"};context.commandArgs(1,args);VSaturnRocket m(&context);known_inputs(m);m.io_core_status_prv=3;m.io_core_resp_ready=1;m.io_dmem_req_ready=1;m.auto_atl_out_a_ready=1;
 auto tick=[&]{m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;m.eval();tick();tick();m.reset=0;
 for(unsigned e=0;e<40;++e){m.eval();tick();}require(!R(vu__DOT__vrf__DOT__resetting),"Actual VRF scrub not complete");
 for(unsigned eg=0;eg<32;++eg)for(unsigned w=0;w<8;++w)require(R(vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__vrf_ext__DOT__Memory)[eg][w]==0,"VRF zero scrub not observed");
 std::deque<Reply> replies;std::map<unsigned,Reply> owned;unsigned retired=0,attempts=0,requests=0,dbeats=0,responses=0,peak_owned=0,peak_reserved=0,peak_inflight=0,capacity_edge=~0u,release_edge=~0u,drained=~0u,hold_checks=0,front_replays=0;bool sent=false;std::uint64_t tlb_s1=0;unsigned inflight_at_capacity=~0u;
 for(unsigned edge=0;edge<10000;++edge){
  const bool releasing=release_edge!=~0u;const bool issuing=retired<4&&!sent;
  m.io_core_ex_valid=issuing;m.io_core_ex_inst=0x02050007u+((retired*(1u<<lmul))<<7);m.io_core_ex_pc=0x80001000ULL+4*retired;m.io_core_ex_rs1=0x80010000ULL+retired*bytes;m.io_core_ex_rs2=0;m.io_core_ex_vconfig_vl=bytes;m.io_core_ex_vconfig_vtype_vsew=0;m.io_core_ex_vconfig_vtype_vlmul_sign=0;m.io_core_ex_vconfig_vtype_vlmul_mag=lmul;m.io_core_ex_vconfig_vtype_vma=1;m.io_core_ex_vconfig_vtype_vta=1;m.io_core_ex_vstart=0;m.io_tlb_s1_resp_paddr=tlb_s1;
  m.auto_atl_out_d_valid=releasing&&!replies.empty();
  if(m.auto_atl_out_d_valid){const auto&r=replies.front();m.auto_atl_out_d_bits_opcode=1;m.auto_atl_out_d_bits_param=0;m.auto_atl_out_d_bits_size=r.size;m.auto_atl_out_d_bits_source=r.source;m.auto_atl_out_d_bits_denied=0;m.auto_atl_out_d_bits_corrupt=0;m.auto_atl_out_d_bits_data=0;for(unsigned b=0;b<8;++b)m.auto_atl_out_d_bits_data|=std::uint64_t(pattern(r.address+r.beat*8+b))<<(8*b);}
  m.eval();const auto next_tlb=m.io_tlb_req_valid?m.io_tlb_req_bits_vaddr:tlb_s1;require(!m.io_core_wb_xcpt,"Unexpected source load exception");require(!m.io_dmem_req_valid,"Fixed ATL route unexpectedly used Hella");
  const bool exfire=issuing&&m.io_core_ex_ready,afire=m.auto_atl_out_a_valid&&m.auto_atl_out_a_ready,dfire=m.auto_atl_out_d_valid&&m.auto_atl_out_d_ready;const unsigned occupancy=reserved(m),inflight=R(tl_if__DOT__reader__DOT__inflights);peak_reserved=std::max(peak_reserved,occupancy);peak_inflight=std::max(peak_inflight,inflight);
  if(!owned.empty())require(m.io_core_backend_busy,"Backend idle with accepted unreturned load request");
  if(capacity_edge!=~0u&&!releasing){require(requests==target&&owned.size()==target,"Capacity hold changed accepted ownership");require(occupancy==target,"Capacity hold lost reserved load slots");require(m.io_core_backend_busy,"Premature backend idle at capacity");require(m.io_core_backend_busy||m.io_core_trap_check_busy,"Source scalar vector-CSR gate opened at capacity");++hold_checks;}
  std::cout<<"BURST_STATE "<<lmul<<','<<seed<<','<<edge<<','<<retired<<','<<requests<<','<<dbeats<<','<<owned.size()<<','<<occupancy<<','<<inflight<<','<<unsigned(m.io_core_backend_busy)<<','<<unsigned(m.io_core_trap_check_busy)<<','<<unsigned(releasing)<<'\n';
  if(exfire){require(!sent,"Repeated EX acceptance");sent=true;++attempts;std::cout<<"BURST_EX "<<edge<<','<<retired<<','<<m.io_core_ex_inst<<','<<m.io_core_ex_rs1<<'\n';}
  if(m.io_core_wb_replay){require(sent&&m.io_core_wb_pc==0x80001000ULL+4*retired,"Unowned source WB replay");std::cout<<"BURST_WB "<<edge<<",replay,"<<m.io_core_wb_pc<<','<<m.io_core_wb_inst<<'\n';sent=false;++front_replays;}
  if(m.io_core_wb_retire){require(sent&&m.io_core_wb_pc==0x80001000ULL+4*retired,"Unowned source WB retirement");std::cout<<"BURST_WB "<<edge<<",retire,"<<m.io_core_wb_pc<<','<<m.io_core_wb_inst<<'\n';++retired;sent=false;}
  // Capture accepted physical events, then advance exactly one source edge.
  Reply incoming{};if(afire){require(m.auto_atl_out_a_bits_opcode==4&&m.auto_atl_out_a_bits_size==5,"Unexpected non-32B Get");incoming={unsigned(m.auto_atl_out_a_bits_source),unsigned(m.auto_atl_out_a_bits_size),0,4,m.auto_atl_out_a_bits_address};require(incoming.source>=IRIS_READER_SOURCE_BASE&&incoming.source<IRIS_READER_SOURCE_BASE+32,"Load escaped source-derived reader range");require(incoming.address>=0x80010000ULL&&incoming.address+32<=0x80010000ULL+4*bytes&&!(incoming.address&31),"Get outside exact restore image");}
  if(dfire){require(!replies.empty()&&owned.contains(replies.front().source),"External response without owner");const auto&r=replies.front();std::cout<<"BURST_D "<<edge<<','<<r.source<<','<<r.size<<','<<r.beat<<','<<m.auto_atl_out_d_bits_data<<'\n';}
  tick();tlb_s1=next_tlb;
  if(dfire){++dbeats;if(++replies.front().beat==replies.front().total){owned.erase(replies.front().source);replies.pop_front();++responses;}}
  if(afire){require(!owned.contains(incoming.source),"Physical source tag reused before final D beat");owned.emplace(incoming.source,incoming);replies.push_back(incoming);++requests;peak_owned=std::max(peak_owned,unsigned(owned.size()));std::cout<<"BURST_A "<<edge<<','<<incoming.source<<','<<incoming.size<<','<<incoming.address<<'\n';}
  if(capacity_edge==~0u&&requests==target&&retired==4&&reserved(m)==target){capacity_edge=edge;inflight_at_capacity=R(tl_if__DOT__reader__DOT__inflights);require(inflight_at_capacity==(target%32),"Source inflight counter differs from modulo32");}
  if(capacity_edge!=~0u&&hold_checks==512&&release_edge==~0u)release_edge=edge+1;
  if(releasing&&owned.empty()&&retired==4&&!m.io_core_backend_busy&&!m.io_core_trap_check_busy&&reserved(m)==0){drained=edge;break;}
 }
 require(drained!=~0u&&capacity_edge!=~0u&&hold_checks==512,"Finite restore-sized burst did not reach/hold/drain capacity");require(requests==target&&responses==target&&dbeats==target*4,"Unexpected request/replay/response totals");require(peak_owned==target&&peak_reserved==target,"Did not exercise requested actual reservation peak");
 std::cout<<"BURST_POST "<<drained<<','<<unsigned(m.io_core_backend_busy)<<','<<unsigned(m.io_core_trap_check_busy)<<','<<reserved(m)<<','<<unsigned(R(tl_if__DOT__reader__DOT__inflights))<<','<<owned.size()<<'\n';
 for(unsigned eg=0;eg<32;++eg)for(unsigned word=0;word<8;++word){std::uint32_t want=0;const unsigned offset=eg*32+word*4;for(unsigned b=0;b<4;++b)if(offset+b<4*bytes)want|=std::uint32_t(pattern(0x80010000ULL+offset+b))<<(8*b);const auto actual=R(vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__vrf_ext__DOT__Memory)[eg][word];require(actual==want,"Physical VRF byte pattern differs after full drain");std::cout<<"BURST_VRF "<<eg<<','<<word<<','<<actual<<'\n';}
 std::cout<<"BURST_RESULT {\"lmul\":"<<(1u<<lmul)<<",\"seed\":"<<seed<<",\"four_load_bytes\":"<<4*bytes<<",\"actual_EX_attempts\":"<<attempts<<",\"WB_replays\":"<<front_replays<<",\"WB_retired_loads\":"<<retired<<",\"accepted_Get_requests\":"<<requests<<",\"accepted_D_beats\":"<<dbeats<<",\"completed_responses\":"<<responses<<",\"peak_outstanding_sources\":"<<peak_owned<<",\"peak_reserved_load_slots\":"<<peak_reserved<<",\"peak_nonwrapped_inflight\":"<<peak_inflight<<",\"counter_at_capacity\":"<<inflight_at_capacity<<",\"capacity_edge\":"<<capacity_edge<<",\"hold_edges\":"<<hold_checks<<",\"release_edge\":"<<release_edge<<",\"drained_edge\":"<<drained<<",\"VRF_word_checks\":256,\"no_premature_backend_idle\":true,\"derived_scalar_vector_CSR_gate_held\":true}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
