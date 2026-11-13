#include "saturn_timing_live_bridge.hpp"
#include "verilated.h"
#include <iostream>
#include <map>
#include <stdexcept>
using namespace iris::saturn;
static unsigned refused=0,checks=0;
template<class F>void rejects(F f){try{f();}catch(const std::exception&){++refused;return;}throw std::runtime_error("Expected live bridge guard did not reject");}
int main(){try{
 VerilatedContext foreign;foreign.threads(1);const char*args[]={"foreign-live-bridge-guard","+owner=foreign"};foreign.commandArgs(2,args);Verilated::threadContextp(&foreign);
 auto context=[&]{if(Verilated::threadContextp()!=&foreign)throw std::runtime_error("Live bridge leaked owner context");++checks;};
 for(const auto p:{Profile::Compute128,Profile::Rocket256}){
  const unsigned hart=p==Profile::Compute128?0:2;const bool compute=hart==0;LiveBridgeCapability cap{"explicit guard fixture",{{~0u,0x5e003457u},{~0u,0x02050407u}}};
  rejects([&]{SaturnLiveBridge bad(p,hart,17,{});});context();rejects([&]{SaturnLiveBridge bad(p,hart,17,{"bad mask",{{0,0}}});});context();
  for(unsigned mode=0;mode<7;++mode){
   {SaturnLiveBridge bridge(p,hart,17,cap);context();rejects([&]{bridge.sample();});rejects([&]{bridge.commit(1);});
    DefinedReferenceInputs input;std::map<std::string,unsigned>idx;const auto fields=SaturnTimingCut::input_fields(p);for(unsigned n=0;n<fields.size();++n){idx.emplace(std::string(fields[n].name),n);input.values.words.push_back(0);input.known_bits.push_back(fields[n].word_width==64?~0ULL:(1ULL<<fields[n].word_width)-1);}auto set=[&](const std::string&n,std::uint64_t v){input.values.words.at(idx.at(n))=v;};set(compute?"io_status_prv":"io_core_status_prv",3);set(compute?"io_resp_ready":"io_core_resp_ready",1);
    auto unknown=input;unknown.known_bits[0]=0;rejects([&]{bridge.evaluate(unknown);});context();
    for(unsigned edge=0;edge<100;++edge){set("reset",edge<2);bridge.evaluate(input);const auto before=bridge.sample();bridge.evaluate(input);if(before.words!=bridge.sample().words||bridge.edges()!=edge)throw std::runtime_error("Repeated live bridge settle advanced source state");bridge.commit(edge+1);context();}
    if(mode==0){bridge.evaluate(input);rejects([&]{bridge.commit(100);});}
    else if(mode==1){set("auto_atl_out_d_valid",1);bridge.evaluate(input);rejects([&]{bridge.commit(101);});}
    else{set(compute?"io_ex_valid":"io_core_ex_valid",1);if(compute)set("io_ex_fire",1);set(compute?"io_ex_uop_inst":"io_core_ex_inst",mode==4?0x0280b457u:mode==5?0x02050407u:0x5e003457u);set(compute?"io_ex_uop_pc":"io_core_ex_pc",0x80001000);set(compute?"io_ex_vconfig_vl":"io_core_ex_vconfig_vl",1);bridge.evaluate(input);if(mode==2)rejects([&]{bridge.commit(101);});else if(mode==3)rejects([&]{bridge.commit(101,CallerCommand{7,0x80001004,0x5e003457u});});else if(mode==4)rejects([&]{bridge.commit(101,CallerCommand{7,0x80001000,0x0280b457u});});else if(mode==5)rejects([&]{bridge.commit(101,CallerCommand{7,0x80001000,0x02050407u});});else rejects([&]{bridge.commit(101,CallerCommand{7,0x80001000,0x5e003453u});});}
    if(bridge.edges()!=100)throw std::runtime_error("Rejected command advanced a source clock");rejects([&]{bridge.evaluate(input);});context();
   }context();
  }
 }
 std::cout<<"{\"refusals\":"<<refused<<",\"context_and_phase_checks\":"<<checks<<",\"post_destructor_checks\":14}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
