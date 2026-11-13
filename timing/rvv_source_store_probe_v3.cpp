// Read-only source observer; only explicit physical inputs are driven.
#define main qualified_reset_writer_original_main
#include "saturn_timing_reset_writers.cpp"
#undef main
#include <map>
struct StoreAck{unsigned due,source,size;};
int main(){try{for(unsigned seed:{1u,17u})for(unsigned delay:{2u,20u}){
 VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);const char*args[]={"source-store-geometry"};context.commandArgs(1,args);Verilated::threadContextp(&context);VSaturnCompute m(&context);inputs(m);m.auto_atl_out_a_ready=1;m.io_mem_tlb_req_ready=1;
 auto edge=[&]{Verilated::threadContextp(&context);m.clock=1;m.eval();m.clock=0;m.eval();};m.reset=1;m.eval();edge();edge();m.reset=0;for(unsigned n=0;n<70;++n){m.eval();edge();}require(!sweep(m).active,"Actual64EGscrub incomplete");
 for(unsigned eg=0;eg<64;++eg)for(unsigned w=0;w<4;++w)require(ram(m,eg,w)==0,"Source reset-scrub zeros missing");
 unsigned sent=0,requests=0,responses=0,peak=0,first=~0u,last=0,done=~0u;std::uint64_t tlb=0;std::deque<StoreAck>acks;std::map<unsigned,StoreAck>owned;std::set<uint64_t>addresses;
 for(unsigned cycle=0;cycle<1200;++cycle){
  m.io_ex_valid=sent<4;m.io_ex_fire=0;m.io_ex_uop_inst=0x02056c27;m.io_ex_uop_pc=0x80001000ULL+4*sent;m.io_ex_uop_rs1_data=0x80010000ULL+128*sent;m.io_ex_uop_rs2_data=0;m.io_ex_vconfig_vl=32;m.io_ex_vconfig_vtype_vill=0;m.io_ex_vconfig_vtype_vsew=2;m.io_ex_vconfig_vtype_vlmul_mag=2;m.io_ex_vconfig_vtype_vlmul_sign=0;m.io_ex_vconfig_vtype_vma=1;m.io_ex_vconfig_vtype_vta=1;m.io_ex_vstart=0;m.io_mem_tlb_resp_paddr=tlb;
  m.auto_atl_out_d_valid=!acks.empty()&&acks.front().due<=cycle;m.auto_atl_out_d_bits_opcode=0;m.auto_atl_out_d_bits_param=0;m.auto_atl_out_d_bits_size=acks.empty()?0:acks.front().size;m.auto_atl_out_d_bits_source=acks.empty()?0:acks.front().source;m.auto_atl_out_d_bits_denied=0;m.auto_atl_out_d_bits_corrupt=0;for(unsigned w=0;w<8;++w)m.auto_atl_out_d_bits_data[w]=0;
  m.eval();m.io_mem_tlb_resp_paddr=m.io_mem_tlb_req_bits_vaddr;m.eval();bool accept=m.io_ex_valid&&m.io_ex_ready;m.io_ex_fire=accept;m.eval();const uint64_t nexttlb=m.io_mem_tlb_req_bits_vaddr;
  if(accept){std::cout<<"EX {\"seed\":"<<seed<<",\"delay\":"<<delay<<",\"edge\":"<<cycle<<",\"ordinal\":"<<sent<<",\"pc\":"<<m.io_ex_uop_pc<<",\"address\":"<<m.io_ex_uop_rs1_data<<"}\n";++sent;}
  require(!m.io_com_xcpt&&!m.io_com_internal_replay,"Unexpected source exception/replay (would require CPU owner replay)");
  const bool apush=m.auto_atl_out_a_valid&&m.auto_atl_out_a_ready,dpop=m.auto_atl_out_d_valid&&m.auto_atl_out_d_ready;StoreAck incoming{};
  if(apush){unsigned size=m.auto_atl_out_a_bits_size,mask=m.auto_atl_out_a_bits_mask;uint64_t address=m.auto_atl_out_a_bits_address;require(m.auto_atl_out_a_bits_opcode==0||m.auto_atl_out_a_bits_opcode==1,"Source A is not Put");require(size==4,"Compute source internal transfer size must16B");require(address>=0x80010000ULL&&address<0x80010200ULL&&!(address&15),"Exact store512Bspan/16Baddress");require(mask==0xffffU||mask==0xffff0000U,"16Bpayload on256bitphysicalport");for(unsigned b=0;b<32;++b)if(mask&(1u<<b))require(((m.auto_atl_out_a_bits_data[b/4]>>((b%4)*8))&255)==0,"Only scrub-known zero bytes are transported");require(addresses.insert(address).second,"Duplicate physical store address");incoming={cycle+delay,unsigned(m.auto_atl_out_a_bits_source),size};if(first==~0u)first=cycle;last=cycle;std::cout<<"A {\"seed\":"<<seed<<",\"delay\":"<<delay<<",\"edge\":"<<cycle<<",\"source\":"<<incoming.source<<",\"size\":"<<size<<",\"mask\":"<<mask<<",\"address\":"<<address<<"}\n";}
  const bool read_fire=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vss__DOT_____io_dis_ready_T_1;
  if(read_fire)std::cout<<"READ {\"seed\":"<<seed<<",\"delay\":"<<delay<<",\"edge\":"<<cycle<<",\"eg\":"<<m.rootp->SaturnShuttleUnit__DOT__vu__DOT___vss_io_rvd_bits_eg<<",\"eidx\":"<<unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vss__DOT__eidx)<<",\"debug_id\":"<<m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vss__DOT__inst_debug_id<<",\"rintent\":"<<m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vss__DOT__rvd_mask<<"}\n";
  std::cout<<"STATE {\"seed\":"<<seed<<",\"delay\":"<<delay<<",\"edge\":"<<cycle<<",\"backend_busy\":"<<unsigned(m.io_backend_busy)<<",\"sequence_active\":"<<unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vss__DOT__valid)<<",\"writer_inflights\":"<<unsigned(m.rootp->SaturnShuttleUnit__DOT__tl_if__DOT__writer__DOT__inflights)<<",\"owned\":"<<owned.size()<<"}\n";
  if(!owned.empty())require(m.io_backend_busy,"Backend idle before accepted store acknowledgment");
  if(dpop){require(!acks.empty()&&owned.count(acks.front().source),"Ack without owned request");std::cout<<"D {\"seed\":"<<seed<<",\"delay\":"<<delay<<",\"edge\":"<<cycle<<",\"source\":"<<acks.front().source<<"}\n";}
  edge();tlb=nexttlb;if(dpop){owned.erase(acks.front().source);acks.pop_front();++responses;}if(apush){require(!owned.count(incoming.source),"Source tag reused before matching ack");owned.emplace(incoming.source,incoming);acks.push_back(incoming);++requests;peak=std::max(peak,unsigned(owned.size()));}
  if(sent==4&&requests==32&&responses==32&&!m.io_backend_busy&&!m.io_trap_check_busy){done=cycle;break;}
 }
 require(done!=~0u&&sent==4&&requests==32&&responses==32&&owned.empty(),"Four128Bstores didnot actually drain32source requests");
 std::cout<<"RESULT {\"seed\":"<<seed<<",\"delay\":"<<delay<<",\"macro_stores\":4,\"bytes\":512,\"requests\":"<<requests<<",\"responses\":"<<responses<<",\"peak_owned\":"<<peak<<",\"first_A\":"<<first<<",\"last_A\":"<<last<<",\"unit_drained\":"<<done<<"}\n";
 }return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
