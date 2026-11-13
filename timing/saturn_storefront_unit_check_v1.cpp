// Read-only whole-unit differential. Existing full-model source/objects remain
// unchanged; only the physical VMU/ATL cut is observed/replayed into the slice.
#define main source_reset_writer_main_not_called
#include "saturn_timing_reset_writers.cpp"
#undef main
#include "VComputeStorefront.h"
#include <deque>
#include <map>
#include <set>
namespace {
std::uint64_t checks=0,edges=0,requests=0,acks=0,bytes=0;
bool bad_mask=false,bad_source=false;
void need(bool value,const char*why){++checks;require(value,why);}
struct Ack{unsigned due,source;};
void scenario(unsigned seed,unsigned delay,unsigned vl){
  VerilatedContext whole_context;whole_context.threads(1);whole_context.randSeed(seed);whole_context.randReset(2);const char*args[]={"source-storefront-unit-differential"};whole_context.commandArgs(1,args);Verilated::threadContextp(&whole_context);VSaturnCompute m(&whole_context);inputs(m);
  VerilatedContext slice_context;slice_context.threads(1);slice_context.randSeed(seed+31);slice_context.randReset(2);slice_context.commandArgs(1,args);Verilated::threadContextp(&slice_context);VComputeStorefront p(&slice_context);
  p.clock=0;p.reset=1;p.io_vec_load_req_valid=0;p.io_vec_load_req_bits_addr=0;p.io_vec_load_req_bits_tag=0;p.io_vec_store_req_valid=0;p.io_vec_store_req_bits_addr=0;p.io_vec_store_req_bits_tag=0;p.io_vec_store_req_bits_mask=0;for(unsigned n=0;n<4;++n)p.io_vec_store_req_bits_data[n]=0;
  p.auto_atl_out_a_ready=0;p.auto_atl_out_d_valid=0;p.auto_atl_out_d_bits_opcode=0;p.auto_atl_out_d_bits_param=0;p.auto_atl_out_d_bits_size=0;p.auto_atl_out_d_bits_source=0;p.auto_atl_out_d_bits_sink=0;p.auto_atl_out_d_bits_denied=0;p.auto_atl_out_d_bits_corrupt=0;for(unsigned n=0;n<8;++n)p.auto_atl_out_d_bits_data[n]=0;
  auto evaluate_whole=[&]{Verilated::threadContextp(&whole_context);m.eval();};
  auto evaluate_slice=[&]{Verilated::threadContextp(&slice_context);p.eval();};
  auto commit=[&]{Verilated::threadContextp(&whole_context);m.clock=1;m.eval();m.clock=0;m.eval();Verilated::threadContextp(&slice_context);p.clock=1;p.eval();p.clock=0;p.eval();++edges;};
  m.reset=1;for(unsigned n=0;n<2;++n){evaluate_whole();evaluate_slice();commit();}m.reset=0;p.reset=0;
  for(unsigned n=0;n<70;++n){evaluate_whole();evaluate_slice();commit();}
  need(!sweep(m).active,"source reset scrub incomplete");for(unsigned eg=0;eg<64;++eg)for(unsigned w=0;w<4;++w)need(ram(m,eg,w)==0,"source architectural scrub bytes are not zero");
  std::deque<Ack>responses;std::map<unsigned,unsigned>owners;std::set<std::uint64_t>addresses;unsigned sent=0,a=0,d=0,idle=0;
  const auto per_command=(vl*4+15)/16;
  for(unsigned cycle=0;cycle<10000;++cycle){
    m.io_ex_valid=sent<4;m.io_ex_fire=0;m.io_ex_uop_inst=0x02056c27;m.io_ex_uop_pc=0x80001000+4*sent;m.io_ex_uop_rs1_data=0x80010000+128*sent;m.io_ex_vconfig_vl=vl;m.io_ex_vconfig_vtype_vill=0;m.io_ex_vconfig_vtype_vsew=2;m.io_ex_vconfig_vtype_vlmul_mag=2;m.io_ex_vconfig_vtype_vlmul_sign=0;m.io_ex_vconfig_vtype_vma=1;m.io_ex_vconfig_vtype_vta=1;m.io_mem_tlb_req_ready=1;
    m.auto_atl_out_a_ready=cycle%7!=0&&!(cycle>=40&&cycle<70);m.auto_atl_out_d_valid=!responses.empty()&&responses.front().due<=cycle;m.auto_atl_out_d_bits_source=responses.empty()?0:responses.front().source;m.auto_atl_out_d_bits_size=4;m.auto_atl_out_d_bits_opcode=0;
    evaluate_whole();m.io_mem_tlb_resp_paddr=m.io_mem_tlb_req_bits_vaddr;evaluate_whole();const bool fire=m.io_ex_valid&&m.io_ex_ready;m.io_ex_fire=fire;evaluate_whole();
    auto&r=*m.rootp;
    p.io_vec_load_req_valid=r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_load_req_valid;p.io_vec_load_req_bits_addr=r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_load_req_bits_addr;p.io_vec_load_req_bits_tag=r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_load_req_bits_tag;
    p.io_vec_store_req_valid=r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_store_req_valid;p.io_vec_store_req_bits_addr=r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_store_req_bits_addr;p.io_vec_store_req_bits_tag=r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_store_req_bits_tag;p.io_vec_store_req_bits_mask=r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_store_req_bits_mask;
    // Only actual scrub-qualified zero stores in this full-unit differential.
    // The separate raw-port proof will cover arbitrary payloads/masks.
    for(unsigned n=0;n<4;++n)p.io_vec_store_req_bits_data[n]=0;
    p.auto_atl_out_a_ready=m.auto_atl_out_a_ready;p.auto_atl_out_d_valid=m.auto_atl_out_d_valid;p.auto_atl_out_d_bits_source=m.auto_atl_out_d_bits_source;p.auto_atl_out_d_bits_size=4;p.auto_atl_out_d_bits_opcode=0;evaluate_slice();
    need(p.io_vec_load_req_ready==r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_load_req_ready,"whole-source/slice load request ready edge");need(p.io_vec_store_req_ready==r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_store_req_ready,"whole-source/slice store request ready edge");
    need(p.io_vec_load_resp_valid==r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_load_resp_valid,"whole-source/slice load response edge");need(p.io_vec_store_ack_valid==r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_store_ack_valid,"whole-source/slice ordered store ACK edge");
    if(p.io_vec_store_ack_valid)need(p.io_vec_store_ack_bits_tag==r.SaturnShuttleUnit__DOT__tl_if__DOT__io_vec_store_ack_bits_tag,"whole-source/slice ACK tag");
    need(p.io_mem_busy==bool(r.SaturnShuttleUnit__DOT__tl_if__DOT__writer__DOT__inflights||r.SaturnShuttleUnit__DOT__tl_if__DOT__reader__DOT__inflights),"whole-source/slice exact TL-only busy (not full VMU busy)");
    need(p.auto_atl_out_a_valid==m.auto_atl_out_a_valid&&p.auto_atl_out_d_ready==m.auto_atl_out_d_ready,"whole-source/slice buffered physical valid-ready phase");
    if(m.auto_atl_out_a_valid){need(p.auto_atl_out_a_bits_opcode==m.auto_atl_out_a_bits_opcode&&p.auto_atl_out_a_bits_param==m.auto_atl_out_a_bits_param&&p.auto_atl_out_a_bits_size==m.auto_atl_out_a_bits_size&&p.auto_atl_out_a_bits_source==(m.auto_atl_out_a_bits_source^(bad_source?1:0))&&p.auto_atl_out_a_bits_address==m.auto_atl_out_a_bits_address&&p.auto_atl_out_a_bits_mask==(m.auto_atl_out_a_bits_mask^(bad_mask?1:0))&&p.auto_atl_out_a_bits_corrupt==m.auto_atl_out_a_bits_corrupt,"whole-source/slice actual A metadata/mask/source");for(unsigned n=0;n<32;++n)if(m.auto_atl_out_a_bits_mask&(1u<<n))need(((p.auto_atl_out_a_bits_data[n/4]>>(8*(n%4)))&255)==((m.auto_atl_out_a_bits_data[n/4]>>(8*(n%4)))&255),"whole-source/slice actual strobed byte");}
    const bool push=m.auto_atl_out_a_valid&&m.auto_atl_out_a_ready,pop=m.auto_atl_out_d_valid&&m.auto_atl_out_d_ready;Ack incoming{};
    if(push){const auto address=m.auto_atl_out_a_bits_address;need(address>=0x80010000ULL&&address<0x80010200ULL&&!(address&15),"source VSE physical16B address domain");const unsigned offset=(address-0x80010000ULL)%128,remaining=vl*4-offset,active=std::min(16u,remaining);const auto expected_mask=((1u<<active)-1)<<((address&16)?16:0);need(m.auto_atl_out_a_bits_mask==expected_mask&&m.auto_atl_out_a_bits_size==4&&m.auto_atl_out_a_bits_source<16,"source partial mask/size/writer ID geometry");need(addresses.insert(address).second,"duplicate source VSE address");for(unsigned n=0;n<32;++n)if(expected_mask&(1u<<n)){need(((m.auto_atl_out_a_bits_data[n/4]>>(8*(n%4)))&255)==0,"source store violated actual scrub-zero golden");++bytes;}incoming={cycle+delay,unsigned(m.auto_atl_out_a_bits_source)};}
    if(pop)need(!responses.empty()&&owners.contains(responses.front().source),"source D without actual accepted owner");
    need(!m.io_com_xcpt&&!m.io_com_internal_replay,"full-unit source CPU replay outside finite witness");commit();
    if(fire)++sent;
    if(pop){owners.erase(responses.front().source);responses.pop_front();++d;++acks;}
    if(push){need(!owners.contains(incoming.source),"source reused tag before matching response");owners.emplace(incoming.source,a);responses.push_back(incoming);++a;++requests;}
    if(sent==4&&a==4*per_command&&d==a&&!m.io_backend_busy&&!m.io_trap_check_busy&&!p.io_mem_busy)++idle;else idle=0;
    if(idle==4){need(owners.empty()&&responses.empty(),"source ownership did not drain");return;}
  }throw std::runtime_error("source unit/slice did not drain finite VSE witness");
}
}
int main(int argc,char**argv){try{bad_mask=argc==2&&std::string(argv[1])=="--wrong-mask";bad_source=argc==2&&std::string(argv[1])=="--wrong-source";unsigned profiles=0;for(unsigned seed:{1u,17u})for(unsigned delay:{2u,20u,200u})for(unsigned vl:{1u,3u,8u,31u,32u}){scenario(seed,delay,vl);++profiles;}std::cout<<"{\"pass\":true,\"profiles\":"<<profiles<<",\"checks\":"<<checks<<",\"whole_source_edges\":"<<edges<<",\"accepted_physical_requests\":"<<requests<<",\"accepted_D\":"<<acks<<",\"independent_strobed_zero_bytes\":"<<bytes<<",\"native_CPU_or_System_qualified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
