#include "rocket_serial_peer.hpp"
#include "verilated.h"
#include <functional>
#include <iostream>
#include <stdexcept>
using Peer=iris::frontend::RocketSerialPeer;
int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("exact component source identities required");
 auto cfg=[&](){return Peer::Configuration{1,16,100,{"source-serial-lifecycle","+tilelink_timeout=0"},iris::serial_memory::AssertionPolicy::SuppressOnlyWhileBothExternalResets,{30,30,16,16},argv[1],argv[2]};};
 VerilatedContext foreign;Verilated::threadContextp(&foreign);unsigned checks=0,refusals=0;
 auto need=[&](bool x){++checks;if(!x)throw std::runtime_error("source composite leaked owner context or admitted invalid transition");};
 auto bad=[&](std::function<void(Peer::Configuration&)>mutate){auto c=cfg();mutate(c);bool refused=false;try{Peer peer(c);}catch(const std::exception&){refused=true;}need(refused);++refusals;need(Verilated::threadContextp()==&foreign);};
 bad([](auto&c){c.seed=0;});bad([](auto&c){c.seed=0x80000000;});bad([](auto&c){c.frontend_reset_edges=0;});bad([](auto&c){c.system_reset_phases=0;});bad([](auto&c){c.expected_system_identity="wrong";});bad([](auto&c){c.expected_latency_identity="wrong";});bad([](auto&c){c.latency.read_latency=0;});bad([](auto&c){c.latency.write_max_requests=17;});
 for(unsigned seed:{1,17}){
  {auto c=cfg();c.seed=seed;Peer peer(c);need(Verilated::threadContextp()==&foreign);
   std::vector<Peer::Input>a(peer.arbiter_input_fields().size()),s(peer.system_input_fields().size());std::vector<iris::fased::Bits>l;for(unsigned i=0;i<a.size();++i)for(unsigned b=0;b<peer.arbiter_input_fields()[i].width;++b)a[i].known.limbs[b/64]|=uint64_t(1)<<(b%64);for(unsigned i=0;i<s.size();++i)for(unsigned b=0;b<peer.system_input_fields()[i].width;++b)s[i].known.limbs[b/64]|=uint64_t(1)<<(b%64);for(const auto&f:peer.latency_input_fields())l.push_back({0,f.width==64?~uint64_t(0):(uint64_t(1)<<f.width)-1});
   iris::frontend::SavedRocketFrontend::Inputs front;front.custom_csr=0x208;
   peer.evaluate({front,a,s,l});const auto first=peer.sample();need(Verilated::threadContextp()==&foreign);peer.evaluate({front,a,s,l});need(peer.sample().system==first.system);peer.commit({true,true,true,true});need(Verilated::threadContextp()==&foreign);
   bool rejected=false;try{peer.commit({true,true,true,true});}catch(const std::logic_error&){rejected=true;}need(rejected);++refusals;
   auto joined=peer.system_input_index("rocket_tile","_frontend_auto_icache_master_out_a_valid");s[joined].value=Peer::Bits(1);rejected=false;try{peer.evaluate({front,a,s,l});}catch(const std::invalid_argument&){rejected=true;}need(rejected);++refusals;need(Verilated::threadContextp()==&foreign);rejected=false;try{peer.commit({true,true,true,true});}catch(const std::logic_error&){rejected=true;}need(rejected);++refusals;
  }need(Verilated::threadContextp()==&foreign);
 }
 std::cout<<"{\"status\":\"passed_serial_peer_failed_constructor_destructor_and_phase_guards\",\"checks\":"<<checks<<",\"refusals\":"<<refusals<<"}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
