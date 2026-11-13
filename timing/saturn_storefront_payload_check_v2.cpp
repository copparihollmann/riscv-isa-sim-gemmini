#include "VComputeStorefront.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <optional>
#include <random>
#include <stdexcept>
namespace {
std::uint64_t checks=0,edges=0,read_requests=0,write_requests=0,byte_checks=0,full_windows=0;
bool bad_half=false,bad_id=false;
void need(bool value,const char*text){++checks;if(!value)throw std::runtime_error(text);}
struct Owner{bool load=false;unsigned tag=0,stage=0,request_edge=0,a_edge=0,d_edge=0,due=0;std::uint64_t address=0;unsigned mask=0;std::array<std::uint32_t,4>data{},returned{};};
struct D{unsigned index;std::array<std::uint32_t,8>data;};
void run(unsigned seed,bool mixed){
  VerilatedContext context;context.threads(1);context.randReset(2);context.randSeed(seed);const char*args[]={"storefront-independent-payloads"};context.commandArgs(1,args);Verilated::threadContextp(&context);VComputeStorefront p(&context);
  p.clock=0;p.reset=1;p.io_vec_load_req_valid=0;p.io_vec_load_req_bits_addr=0;p.io_vec_load_req_bits_tag=0;p.io_vec_store_req_valid=0;p.io_vec_store_req_bits_addr=0;p.io_vec_store_req_bits_tag=0;p.io_vec_store_req_bits_mask=0;
  p.auto_atl_out_a_ready=0;p.auto_atl_out_d_valid=0;p.auto_atl_out_d_bits_opcode=0;p.auto_atl_out_d_bits_param=0;p.auto_atl_out_d_bits_size=4;p.auto_atl_out_d_bits_source=0;p.auto_atl_out_d_bits_sink=0;p.auto_atl_out_d_bits_denied=0;p.auto_atl_out_d_bits_corrupt=0;for(unsigned n=0;n<4;++n)p.io_vec_store_req_bits_data[n]=0;for(unsigned n=0;n<8;++n)p.auto_atl_out_d_bits_data[n]=0;
  auto edge=[&]{p.clock=1;p.eval();p.clock=0;p.eval();++edges;};for(unsigned n=0;n<2;++n){p.eval();edge();}p.reset=0;
  std::mt19937 random(seed);std::array<std::optional<Owner>,32>owners;std::optional<Owner>load,store;std::optional<D>response;unsigned sent_load=0,sent_store=0,done_load=0,done_store=0;constexpr unsigned count=1000;
  auto pending=[&](bool is_load,unsigned ordinal)->std::optional<Owner>{const unsigned base=is_load?16:0;for(unsigned n=0;n<16;++n)if(!owners[base+n]){Owner o;o.load=is_load;o.tag=n;o.address=0x80010000ULL+16*(ordinal%256)+(is_load?0x10000:0);o.mask=is_load||ordinal%4==0?65535:(random()%65535+1);for(auto&v:o.data)v=random();return o;}return{};};
  for(unsigned cycle=0;cycle<100000;++cycle){
    if(!store&&sent_store<count)store=pending(false,sent_store);
    if(mixed&&!load&&sent_load<count)load=pending(true,sent_load);
    p.io_vec_store_req_valid=bool(store);if(store){p.io_vec_store_req_bits_addr=store->address;p.io_vec_store_req_bits_tag=store->tag;p.io_vec_store_req_bits_mask=store->mask;for(unsigned n=0;n<4;++n)p.io_vec_store_req_bits_data[n]=store->data[n];}
    p.io_vec_load_req_valid=bool(load);if(load){p.io_vec_load_req_bits_addr=load->address;p.io_vec_load_req_bits_tag=load->tag;}
    p.auto_atl_out_a_ready=cycle%97>=17&&random()%5!=0;
    if(!response){const unsigned start=random()%32;for(unsigned n=0;n<32;++n){const auto index=(start+n)%32;if(owners[index]&&owners[index]->stage==2&&owners[index]->due<=cycle){D d;d.index=index;for(auto&v:d.data)v=random();response=d;break;}}}
    p.auto_atl_out_d_valid=bool(response);if(response){p.auto_atl_out_d_bits_source=response->index;p.auto_atl_out_d_bits_opcode=owners[response->index]->load?1:0;for(unsigned n=0;n<8;++n)p.auto_atl_out_d_bits_data[n]=response->data[n];}
    p.eval();
    unsigned inflights[2]{};for(const auto&o:owners)if(o)++inflights[o->load];if(inflights[0]==16||inflights[1]==16)++full_windows;
    need(p.io_mem_busy==bool((inflights[0]&15)||(inflights[1]&15)),"exact modulo16 TL-only busy; not a substitute for upstream maybe_full");
    const bool lf=load&&p.io_vec_load_req_ready,sf=store&&p.io_vec_store_req_ready,af=p.auto_atl_out_a_valid&&p.auto_atl_out_a_ready,df=response&&p.auto_atl_out_d_ready;
    if(lf){auto o=*load;o.stage=1;o.request_edge=cycle;need(!owners[16+o.tag],"load tag generation already owned");owners[16+o.tag]=o;}
    if(sf){auto o=*store;o.stage=1;o.request_edge=cycle;need(!owners[o.tag],"store tag generation already owned");owners[o.tag]=o;}
    if(p.auto_atl_out_a_valid){const unsigned index=p.auto_atl_out_a_bits_source;need(index<32&&bool(owners[index]),"actual A lacks accepted VMU request owner");const auto&o=*owners[index];need(o.stage==1&&p.auto_atl_out_a_bits_address==o.address&&p.auto_atl_out_a_bits_size==4&&p.auto_atl_out_a_bits_param==0&&!p.auto_atl_out_a_bits_corrupt,"source A accepted metadata ownership");const unsigned mask=o.mask<<((o.address&16)?16:0);need(p.auto_atl_out_a_bits_mask==mask,"source sixteen-byte half-word mask mapping");need(p.auto_atl_out_a_bits_opcode==(o.load?4:1),"source Get/always-PutPartial opcode including full mask");if(!o.load)for(unsigned byte=0;byte<32;++byte)if(mask&(1u<<byte)){const auto actual=(p.auto_atl_out_a_bits_data[byte/4]>>(8*(byte%4)))&255,golden=(o.data[(byte%16)/4]>>(8*(byte%4)))&255;need(actual==golden,"source arbitrary strobed payload byte mapping");++byte_checks;}}
    if(af){auto&o=*owners[p.auto_atl_out_a_bits_source];need(cycle>o.request_edge,"source A bypassed nonflow Saturn TLBuffer");o.a_edge=cycle;o.stage=2;o.due=cycle+1+random()%100;if(o.load)++read_requests;else++write_requests;}
    if(df){auto&o=*owners[response->index];need(o.stage==2&&cycle>o.a_edge,"source D before owned physical A");o.stage=3;o.d_edge=cycle;const unsigned half=((o.address>>4)&1)^(bad_half?1:0);for(unsigned n=0;n<4;++n)o.returned[n]=response->data[half*4+n];}
    std::optional<unsigned>finished_load,finished_store;
    if(p.io_vec_load_resp_valid){const unsigned tag=p.io_vec_load_resp_bits_tag^(bad_id?1:0);need(tag<16&&owners[16+tag]&&owners[16+tag]->stage==3,"actual load response tag/generation owner");const auto&o=*owners[16+tag];need(cycle>o.d_edge,"load response bypassed source registered D buffer");for(unsigned n=0;n<4;++n)need(p.io_vec_load_resp_bits_data[n]==o.returned[n],"source returned load half-word payload");finished_load=16+tag;++done_load;}
    if(p.io_vec_store_ack_valid){const unsigned tag=p.io_vec_store_ack_bits_tag;need(tag<16&&owners[tag]&&owners[tag]->stage==3,"actual store ACK tag/generation owner");need(cycle>owners[tag]->d_edge,"store ACK bypassed source registered D buffer");finished_store=tag;++done_store;}
    edge();if(lf){++sent_load;load.reset();}if(sf){++sent_store;store.reset();}if(df)response.reset();if(finished_load)owners[*finished_load].reset();if(finished_store)owners[*finished_store].reset();
    if(done_store==count&&done_load==(mixed?count:0)){need(sent_store==count&&sent_load==(mixed?count:0),"source duplicate/lost request accounting");for(const auto&o:owners)need(!o,"source leftover transaction owner");return;}
  }throw std::runtime_error("finite source payload test did not drain");
}
}
int main(int argc,char**argv){try{bad_half=argc==2&&std::string(argv[1])=="--wrong-half";bad_id=argc==2&&std::string(argv[1])=="--wrong-id";for(unsigned seed:{1u,17u})for(bool mixed:{false,true})run(seed,mixed);std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"source_edges\":"<<edges<<",\"load_requests\":"<<read_requests<<",\"store_requests\":"<<write_requests<<",\"arbitrary_strobed_bytes\":"<<byte_checks<<",\"full16_tag_windows\":"<<full_windows<<",\"native_or_System_qualified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
