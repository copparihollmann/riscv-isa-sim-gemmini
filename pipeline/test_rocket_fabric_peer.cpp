#include "rocket_fabric_peer.hpp"
#include <array>
#include <deque>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include "verilated.h"
using Peer=iris::frontend::RocketFabricPeer;using Bits=Peer::Bits;using Input=Peer::Input;
static unsigned checks=0;
static void expect(bool value,const std::string&why){++checks;if(!value)throw std::runtime_error(why);}
static Bits known(unsigned width){Bits b;for(unsigned n=0;n<width;++n)b.limbs[n/64]|=uint64_t(1)<<(n%64);return b;}
static uint8_t code_byte(uint64_t address){static constexpr uint8_t code[]={0x05,0x03,0x93,0x82,0x12,0x00};if(address<0x80000000||address>=0x80010000)throw std::runtime_error("explicit code backing span exceeded");return code[(address-0x80000000)%6];}
static uint64_t code_data(uint64_t address){uint64_t word=0;for(unsigned n=0;n<8;++n)word|=uint64_t(code_byte(address+n))<<(8*n);return word;}
struct Request{uint64_t source,address,size,accepted,beat=0;};
struct Harness {
  Peer peer;std::vector<Input> arb,fabric;iris::frontend::SavedRocketFrontend::Inputs front;
  Peer::Outputs out;std::map<std::string,unsigned> ai,ao,fi,fo;
  std::array<std::deque<Request>,4> requests;std::array<bool,4> serving{};
  unsigned cycle=0,outer_requests=0,outer_beats=0,cache_b=0,cache_c=0,icache_beats=0,icache_requests=0;
  bool service=false;std::deque<std::pair<unsigned,uint64_t>> replays;
  explicit Harness(unsigned seed):peer(seed,16),arb(Peer::arbiter_input_fields().size()),fabric(Peer::fabric_input_fields().size()){
    auto a=Peer::arbiter_input_fields(),f=Peer::fabric_input_fields();
    for(unsigned i=0;i<arb.size();++i){ai.emplace(std::string(a[i].name),i);arb[i].known=known(a[i].width);}
    for(unsigned i=0;i<fabric.size();++i){fi.emplace(std::string(f[i].name),i);fabric[i].known=known(f[i].width);}
    for(unsigned i=0;i<Peer::arbiter_output_fields().size();++i)ao.emplace(std::string(Peer::arbiter_output_fields()[i].name),i);
    for(unsigned i=0;i<Peer::fabric_output_fields().size();++i)fo.emplace(std::string(Peer::fabric_output_fields()[i].name),i);
    setarb("io_requestor_1_req_bits_dprv",3);setarb("io_requestor_1_req_bits_size",3);
    front.custom_csr=0x208;
  }
  unsigned input(const std::string&comp,const std::string&name)const{return iris::fabric::MemoryFabric::external_input_index(comp,name);}
  unsigned output(const std::string&comp,const std::string&name)const{return iris::fabric::MemoryFabric::output_index(comp,name);}
  void setarb(const std::string&name,uint64_t value){arb.at(ai.at(name)).value=Bits(value);}
  void set(const std::string&comp,const std::string&name,uint64_t value){fabric.at(input(comp,name)).value=Bits(value);}
  uint64_t getarb(const std::string&name)const{return out.arbiter.at(ao.at(name)).limbs[0];}
  uint64_t get(const std::string&comp,const std::string&name)const{return out.fabric.at(output(comp,name)).limbs[0];}
  static std::string port(unsigned bank){return "auto_coupler_to_bus_named_mbus_bus_xing_out_"+std::to_string(bank);}
  void evaluate(){peer.evaluate({front,arb,fabric});out=peer.sample();}
  void tick(iris::fabric::ClockEdges edges={true,true}){
    for(unsigned b=0;b<4;++b){auto p=port(b);set("manager",p+"_a_ready",service);set("manager",p+"_d_valid",0);serving[b]=false;
      if(service&&!requests[b].empty()&&cycle>=requests[b].front().accepted+3){const auto&q=requests[b].front();serving[b]=true;set("manager",p+"_d_valid",1);set("manager",p+"_d_bits_opcode",1);set("manager",p+"_d_bits_size",q.size);set("manager",p+"_d_bits_source",q.source);set("manager",p+"_d_bits_data",code_data(q.address+8*q.beat));}
    }
    evaluate();
    if(edges.uncore)for(unsigned b=0;b<4;++b){auto p=port(b);
      if(serving[b]&&get("manager",p+"_d_ready")){auto&q=requests[b].front();++outer_beats;if(++q.beat==(uint64_t(1)<<q.size)/8)requests[b].pop_front();}
      if(service&&get("manager",p+"_a_valid")){expect(get("manager",p+"_a_bits_opcode")==4,"fixture accepts only actual source-cork Get");requests[b].push_back({get("manager",p+"_a_bits_source"),get("manager",p+"_a_bits_address"),get("manager",p+"_a_bits_size"),cycle});++outer_requests;}
    }
    if(edges.rocket){
      icache_requests+=out.frontend.memory_request_valid&&get("rocket_tile","_tlMasterXbar_auto_anon_in_1_a_ready");
      icache_beats+=get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid");
      cache_b+=get("rocket_tile","_widget_auto_anon_in_b_valid")&&get("rocket_cache","auto_out_b_ready");
      cache_c+=get("rocket_cache","auto_out_c_valid")&&get("rocket_tile","_widget_auto_anon_in_c_ready");
    }
    peer.commit(edges);++cycle;
  }
  void warm_reset(){front.redirect_valid=true;front.redirect_pc=0x80000000;front.might_request=true;tick();front.redirect_valid=false;for(unsigned i=0;i<600;++i)tick();expect(get("rocket_cache","io_cpu_ordered"),"real cache reset sweep finishes");}
  void issue(unsigned cmd,unsigned tag,uint64_t address,uint64_t data=0){
    setarb("io_requestor_1_req_bits_addr",address);setarb("io_requestor_1_req_bits_tag",tag);setarb("io_requestor_1_req_bits_cmd",cmd);setarb("io_requestor_1_req_valid",1);
    Bits d;d.limbs.fill(data);arb.at(ai.at("io_requestor_1_s1_data_data")).value=d;
    unsigned wait=0;do{tick();expect(++wait<100,"actual scalar request enters source arbiter/cache");}while(!getarb("io_requestor_1_req_ready"));setarb("io_requestor_1_req_valid",0);
  }
};
static void composition(unsigned seed){
  VerilatedContext foreign;Verilated::threadContextp(&foreign);
  {
    Harness t(seed);expect(Verilated::threadContextp()==&foreign,"composition constructor restores caller context");t.warm_reset();
    for(unsigned n=0;n<250;++n){t.tick();expect(t.icache_beats==0,"no fetch completion while explicit external service blocked");}
    expect(t.icache_requests==1,"actual frontend Get accepted by source tile arbiter: accepted="+std::to_string(t.icache_requests)+" PC="+std::to_string(t.out.frontend.fetch_pc));expect(t.outer_requests==0,"blocked external service accepts nothing");
    t.service=true;t.front.id_ready=true;uint64_t expected_pc=0x80000000;unsigned count=0,replay_count=0,carried=0;
    for(unsigned n=0;n<12000&&count<512;++n){
      t.front.redirect_valid=false;t.front.id_ready=(n%13<10);
      if(!t.replays.empty()&&t.cycle>=t.replays.front().first){t.front.redirect_valid=true;t.front.redirect_pc=t.replays.front().second;t.front.id_ready=false;t.replays.clear();}
      t.tick();const auto&u=t.out.frontend.id;
      if(u.valid&&t.front.id_ready&&!t.front.redirect_valid){
        if(u.replay){if(t.replays.empty())t.replays.push_back({t.cycle+2,u.pc});++replay_count;continue;}
        // Younger parcels behind a source replay token are physically visible
        // but are squashed by this explicit three-stage test CPU's WB redirect.
        if(!t.replays.empty())continue;
        expect(u.pc==expected_pc,"actual Frontend/IBuf preserves sequential PC");
        const bool compressed=(expected_pc-0x80000000)%6==0;const auto raw=compressed?0x0305U:0x00128293U;
        expect(u.compressed==compressed,"source IBuf compressed length");expect((u.raw&(compressed?0xffffU:0xffffffffU))==raw,"actual fetch data matches independently addressed backing bytes");
        expect(!(u.first_page_fault||u.first_guest_page_fault||u.first_access_fault||u.second_page_fault||u.second_guest_page_fault||u.second_access_fault),"M-mode source fetch has no exception");
        carried+=!compressed&&(expected_pc&3)==2;expected_pc+=compressed?2:4;++count;
      }
    }
    expect(count==512&&carried>50,"512 actual mixed-RVC parcels include cross-fetch 32b instructions");
    t.front.id_ready=false;t.front.might_request=false;for(unsigned n=0;n<300;++n)t.tick();
    const auto old_outer=t.outer_requests;t.issue(0,18,0x80000008);for(unsigned n=0;n<100;++n)t.tick();
    t.issue(0,19,0x80000008);bool response=false;for(unsigned n=0;n<50;++n){t.tick();if(t.getarb("io_requestor_1_resp_valid")){response=true;expect(t.getarb("io_requestor_1_resp_bits_tag")==19,"real arbiter strips scalar client ownership tag");expect(t.getarb("io_requestor_1_resp_bits_data")==code_data(0x80000008),"scalar producer reads same line as actual source Icache");}}
    expect(response,"scalar warm response crosses actual cache and source arbiter");expect(t.outer_requests==old_outer,"Icache-warmed inclusive line needs no new external service");
    const auto stored=code_data(0x80000008)^(uint64_t(1)<<20);t.issue(1,20,0x80000008,stored);for(unsigned n=0;n<20;++n)t.tick();t.issue(0,21,0x80000008);response=false;
    for(unsigned n=0;n<30;++n){t.tick();if(t.getarb("io_requestor_1_resp_valid")){response=true;expect(t.getarb("io_requestor_1_resp_bits_data")==stored,"scalar source store/response preserves actual S1 data owner");}}expect(response,"stored line reload responds");
    const auto old_b=t.cache_b,old_c=t.cache_c;auto old_beats=t.icache_beats;t.front.invalidate_icache=true;t.front.redirect_valid=true;t.front.redirect_pc=0x80000008;t.front.might_request=true;t.tick();t.front.invalidate_icache=false;t.front.redirect_valid=false;t.front.id_ready=false;
    bool observed_word=false;for(unsigned n=0;n<500;++n){t.tick();if(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid")){const auto beat=t.icache_beats-old_beats-1;if(beat==1){expect(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_bits_data")==stored,"real frontend refill gets dirty owner data while physical DRAM backing remains old");observed_word=true;}}}
    expect(observed_word,"actual Icache performed requested refill");expect(t.cache_b==old_b+1&&t.cache_c==old_c+2,"actual Icache Get probes and receives two dirty source Dcache C beats");expect(t.outer_requests==old_outer,"coherent dirty-owner refill bypasses external DRAM fixture");
    expect(Verilated::threadContextp()==&foreign,"all composite public phases restore foreign caller");
    std::cout<<"{\"seed\":"<<seed<<",\"parcels\":"<<count<<",\"cross_fetch_32b\":"<<carried<<",\"source_replay_tokens\":"<<replay_count<<",\"outer_requests\":"<<t.outer_requests<<",\"outer_beats\":"<<t.outer_beats<<",\"icache_requests\":"<<t.icache_requests<<",\"icache_beats\":"<<t.icache_beats<<",\"checks\":"<<checks<<"}\n";
  }
  expect(Verilated::threadContextp()==&foreign,"composition destructor restores foreign caller");
}
static void lifecycle(){
  VerilatedContext foreign;Verilated::threadContextp(&foreign);Harness t(17);unsigned refused=0;
  auto reject=[&](auto call){try{call();}catch(const std::exception&){++refused;return;}throw std::runtime_error("composite lifecycle refusal missing");};
  reject([&]{t.peer.sample();});reject([&]{t.peer.commit({true,true});});
  t.front.memory_request_ready=true;reject([&]{t.evaluate();});t.front.memory_request_ready=false;
  t.front.memory_data=iris::frontend::SavedRocketFrontend::DataBeat{1,false};reject([&]{t.evaluate();});t.front.memory_data.reset();
  auto joined_arb=t.ai.at("io_mem_req_ready");t.arb[joined_arb].value=Bits(1);reject([&]{t.evaluate();});t.arb[joined_arb].value=Bits(0);
  auto joined_cache=t.input("rocket_cache","io_cpu_req_valid");t.fabric[joined_cache].value=Bits(1);reject([&]{t.evaluate();});t.fabric[joined_cache].value=Bits(0);
  t.evaluate();const auto original=t.out;for(unsigned i=0;i<9;++i){t.evaluate();expect(t.out.fabric==original.fabric&&t.out.arbiter==original.arbiter,"same-edge global evaluations have no hidden clock/owner advance");}
  auto unjoined=t.input("rocket_cache","io_ptw_ptbr_mode");t.fabric[unjoined].known=Bits(0);reject([&]{t.evaluate();});reject([&]{t.peer.commit({true,true});});t.fabric[unjoined].known=known(4);
  t.evaluate();reject([&]{t.peer.commit({false,false});});reject([&]{t.peer.sample();});
  t.evaluate();const auto before=t.out.frontend;t.peer.commit({false,true});t.evaluate();expect(t.out.frontend.id.valid==before.id.valid&&t.out.frontend.id.pc==before.id.pc&&t.out.frontend.id.raw==before.id.raw,"uncore-only edge does not clock Frontend/IBuf");t.peer.commit({true,false});
  expect(refused==10,"all joined-input, unknown-input and stale-phase guards exercised");expect(Verilated::threadContextp()==&foreign,"refusal/interleaved clock paths restore caller context");
}
int main(){try{lifecycle();for(unsigned seed:{1,7,31})composition(seed);std::cout<<"{\"status\":\"passed_actual_frontend_arbiter_fabric_composition\",\"checks\":"<<checks<<",\"source_state_injected\":false,\"external_service\":\"explicit synthetic fixture; not Iris latency\",\"native_integration\":false,\"timing_certified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<"Rocket composition failure after "<<checks<<" checks: "<<e.what()<<"\n";return 1;}}
