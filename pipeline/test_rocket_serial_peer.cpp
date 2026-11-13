#include "rocket_serial_peer.hpp"
#include "axi_functional_fixture.hpp"
#include "verilated.h"
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
using Peer=iris::frontend::RocketSerialPeer;using Bits=Peer::Bits;using Input=Peer::Input;
static unsigned checks=0;
static void need(bool value,const char*why){++checks;if(!value)throw std::runtime_error(why);}
static Bits known(unsigned width){Bits b;for(unsigned n=0;n<width;++n)b.limbs[n/64]|=uint64_t(1)<<(n%64);return b;}
static uint64_t mask(unsigned width){return width==64?~uint64_t(0):(uint64_t(1)<<width)-1;}
static uint8_t code_byte(uint64_t address){static constexpr uint8_t code[]={5,3,0x93,0x82,0x12,0};if(address<0x80000000||address>=0x80010000)throw std::runtime_error("fixture code range");return code[(address-0x80000000)%6];}
static uint64_t code_word(uint64_t address,unsigned bytes=8){uint64_t value=0;for(unsigned i=0;i<bytes;++i)value|=uint64_t(code_byte(address+i))<<(8*i);return value;}
static Peer::Configuration config(unsigned seed,const std::string&system,const std::string&lp){return {seed,16,100,{"live-source-frontend-serial-check","+tilelink_timeout=0"},iris::serial_memory::AssertionPolicy::SuppressOnlyWhileBothExternalResets,{30,30,16,16},system,lp};}
struct Harness {
  Peer peer;std::vector<Input>a,m;std::vector<iris::fased::Bits>l;Peer::Outputs out;iris::frontend::SavedRocketFrontend::Inputs front;
  std::map<std::string,unsigned>ai,ao,li,lo;iris::frontend::AxiFunctionalFixture memory;
  uint64_t tick=0,ar=0,r=0,icache_a=0,icache_d=0;unsigned cache_b=0,cache_c=0;VerilatedContext*caller;
  Harness(unsigned seed,const std::string&system,const std::string&lp):peer(config(seed,system,lp)),a(peer.arbiter_input_fields().size()),m(peer.system_input_fields().size()),memory(16,16,[](uint64_t address,unsigned bytes){return iris::frontend::AxiFunctionalFixture::Word{code_word(address,bytes),mask(bytes*8)};},[](uint64_t,unsigned,uint64_t,unsigned){throw std::runtime_error("read-only external backing got an unexpected writeback");}),caller(Verilated::threadContextp()){
    for(unsigned i=0;i<a.size();++i){auto f=peer.arbiter_input_fields()[i];ai.emplace(std::string(f.name),i);a[i].known=known(f.width);}for(unsigned i=0;i<m.size();++i)m[i].known=known(peer.system_input_fields()[i].width);
    for(unsigned i=0;i<peer.arbiter_output_fields().size();++i)ao.emplace(std::string(peer.arbiter_output_fields()[i].name),i);
    for(auto f:peer.latency_input_fields()){li.emplace(f.name,l.size());l.push_back({0,mask(f.width)});}for(auto f:peer.latency_output_fields())lo.emplace(f.name,lo.size());front.custom_csr=0x208;
  }
  void aset(const std::string&name,uint64_t value){a.at(ai.at(name)).value=Bits(value);}
  uint64_t aget(const std::string&name)const{return out.arbiter.at(ao.at(name)).limbs[0];}
  uint64_t get(const std::string&component,const std::string&field)const{return out.system.at(peer.system_output_index(component,field)).limbs[0];}
  uint64_t axi(const std::string&name)const{return get("path","fased_axi4_mem_0_bits_"+name);}
  uint64_t lp(const std::string&name)const{return out.latency.at(lo.at("tNasti_io_"+name));}
  void lset(const std::string&name,uint64_t value){l.at(li.at("tNasti_io_"+name)).value=value;}
  auto request(const std::string&channel)const{return iris::frontend::AxiFunctionalFixture::Request{axi(channel+"_bits_addr"),unsigned(axi(channel+"_bits_id")),unsigned(axi(channel+"_bits_len")),unsigned(axi(channel+"_bits_size")),unsigned(axi(channel+"_bits_burst"))};}
  void evaluate(){auto data=memory.read_payload();auto b=memory.write_payload();lset("egressResp_rBits_data",data?data->data:0);lset("egressResp_rBits_id",data?data->id:0);lset("egressResp_rBits_last",data&&data->last);lset("egressResp_bBits_id",b.value_or(0));peer.evaluate({front,a,m,l});out=peer.sample();need(Verilated::threadContextp()==caller,"evaluation/sample changed caller context");}
  void step(){
    evaluate();const bool edge=tick%2==0;
    need(bool(memory.read_payload())==bool(lp("tNasti_r_valid")),"source LP Rvalid has no owned functional snapshot");need(bool(memory.write_payload())==bool(lp("tNasti_b_valid")),"source LP Bvalid has no owned write");
    if(lp("tNasti_r_valid")&&axi("r_ready")){memory.consume_r();++r;}if(lp("tNasti_b_valid")&&axi("b_ready"))memory.consume_b();
    if(axi("ar_valid")&&lp("tNasti_ar_ready")){memory.accept_ar(request("ar"));++ar;}if(axi("aw_valid")&&lp("tNasti_aw_ready"))memory.accept_aw(request("aw"));if(axi("w_valid")&&lp("tNasti_w_ready"))memory.accept_w(axi("w_bits_data"),axi("w_bits_strb"),axi("w_bits_last"));
    if(lp("egressReq_r_valid"))memory.request_read_egress(lp("egressReq_r_bits"));if(lp("egressReq_b_valid"))memory.request_write_egress(lp("egressReq_b_bits"));
    if(edge){icache_a+=out.frontend.memory_request_valid&&get("rocket_tile","_tlMasterXbar_auto_anon_in_1_a_ready");icache_d+=get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid");cache_b+=get("rocket_tile","_widget_auto_anon_in_b_valid")&&get("rocket_cache","auto_out_b_ready");cache_c+=get("rocket_cache","auto_out_c_valid")&&get("rocket_tile","_widget_auto_anon_in_c_ready");}
    peer.commit({edge,edge,true,tick%10==0});need(Verilated::threadContextp()==caller,"commit changed caller context");++tick;
  }
  void core_step(){bool selected=false;do{selected=tick%2==0;step();}while(!selected);}
  void issue(unsigned command,unsigned tag,uint64_t address,uint64_t data=0){
    aset("io_requestor_1_req_valid",1);aset("io_requestor_1_req_bits_addr",address);aset("io_requestor_1_req_bits_tag",tag);aset("io_requestor_1_req_bits_cmd",command);aset("io_requestor_1_req_bits_size",3);aset("io_requestor_1_req_bits_dprv",3);Bits wide;wide.limbs.fill(data);a.at(ai.at("io_requestor_1_s1_data_data")).value=wide;
    unsigned wait=0;do{core_step();need(++wait<100,"source scalar request was not accepted");}while(!aget("io_requestor_1_req_ready"));aset("io_requestor_1_req_valid",0);
  }
};
static void run(unsigned seed,const std::string&system,const std::string&lp){
  VerilatedContext foreign;Verilated::threadContextp(&foreign);
  {Harness h(seed,system,lp);need(Verilated::threadContextp()==&foreign,"constructor context");h.front.redirect_valid=true;h.front.redirect_pc=0x80000000;h.front.might_request=true;h.step();h.front.redirect_valid=false;
    uint64_t expected=0x80000000;unsigned parcels=0,carried=0,replays=0;std::optional<std::pair<uint64_t,uint64_t>>correction;
    for(unsigned n=0;n<30000&&parcels<128;++n){h.front.redirect_valid=false;h.front.id_ready=h.tick%17<13;
      if(correction&&h.tick>=correction->first&&h.tick%2==0){h.front.redirect_valid=true;h.front.redirect_pc=correction->second;h.front.id_ready=false;correction.reset();}
      const bool edge=h.tick%2==0;const auto now=h.tick;h.step();const auto&u=h.out.frontend.id;
      if(edge&&u.valid&&h.front.id_ready&&!h.front.redirect_valid){if(u.replay){if(!correction)correction={{now+6,u.pc}};++replays;continue;}if(correction)continue;const bool compressed=(expected-0x80000000)%6==0;need(u.pc==expected,"actual sourced fetch PC");need(u.compressed==compressed,"source RVC length");need((u.raw&(compressed?0xffffU:0xffffffffU))==(compressed?0x0305U:0x00128293U),"source fetch bytes survive full SerialTL/FASED path");carried+=!compressed&&(expected&3)==2;expected+=compressed?2:4;++parcels;}
    }
    need(parcels==128&&carried==32,"source mixed-RVC/cross-fetch corpus incomplete");h.front.id_ready=false;h.front.might_request=false;for(unsigned n=0;n<2500;++n)h.step();
    const auto old_ar=h.ar;h.issue(0,18,0x80000008);for(unsigned n=0;n<300;++n)h.step();h.issue(0,19,0x80000008);bool response=false;for(unsigned n=0;n<80;++n){bool edge=h.tick%2==0;h.step();if(edge&&h.aget("io_requestor_1_resp_valid")){response=true;need(h.aget("io_requestor_1_resp_bits_data")==code_word(0x80000008),"scalar producer data");}}
    need(response&&h.ar==old_ar,"warm inclusive source line requires no extra AXI read");
    const auto stored=code_word(0x80000008)^(uint64_t(1)<<20);h.issue(1,20,0x80000008,stored);for(unsigned n=0;n<80;++n)h.step();const auto old_b=h.cache_b,old_c=h.cache_c;const auto old_d=h.icache_d;
    while(h.tick%2)h.step();h.front.invalidate_icache=true;h.front.redirect_valid=true;h.front.redirect_pc=0x80000008;h.front.might_request=true;h.step();h.front.invalidate_icache=false;h.front.redirect_valid=false;
    bool modified=false;for(unsigned n=0;n<2000;++n){bool edge=h.tick%2==0;h.step();if(edge&&h.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid")&&h.icache_d-old_d==2){need(h.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_bits_data")==stored,"actual Icache sees dirty Dcache value rather than backing snapshot");modified=true;}}
    need(modified&&h.cache_b==old_b+1&&h.cache_c==old_c+2&&h.ar==old_ar,"full source path preserves dirty-owner coherence");std::cout<<"{\"seed\":"<<seed<<",\"parcels\":"<<parcels<<",\"cross_fetch_32b\":"<<carried<<",\"source_replays\":"<<replays<<",\"AXI_AR\":"<<h.ar<<",\"AXI_R\":"<<h.r<<",\"icache_A\":"<<h.icache_a<<",\"icache_D\":"<<h.icache_d<<",\"virtual_ticks\":"<<h.tick<<"}\n";
  }
  need(Verilated::threadContextp()==&foreign,"destructor context");
}
int main(int argc,char**argv){try{if(argc!=3)throw std::runtime_error("explicit frozen System/LP identities required");for(unsigned seed:{1,17})run(seed,argv[1],argv[2]);std::cout<<"{\"status\":\"passed_actual_frontend_arbiter_serial_system_LP\",\"checks\":"<<checks<<",\"recorded_source_state_injected\":false,\"post_cork_fixture_removed\":true,\"functional_AXI_fixture\":true,\"timing_certified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<"source serial peer: "<<e.what()<<'\n';return 1;}}
