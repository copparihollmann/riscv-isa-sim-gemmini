#include "frontend_rtl_peer.hpp"
#include "rocket_frontend_rtl_peer.hpp"
#include "verilated.h"
#include <array>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <vector>
using iris::frontend::SavedRocketFrontend;
using iris::frontend::SavedShuttleFrontend;
struct Refill {uint64_t line;unsigned accepted,beat=0;};
static uint8_t byte(uint64_t address) {
  static constexpr uint8_t code[]={0x05,0x03,0x93,0x82,0x12,0x00};
  if(address<0x10000 || address>=0x12000)throw std::runtime_error("synthetic ROM outside span");
  return code[(address-0x10000)%6];
}
static uint64_t data(uint64_t address) {uint64_t v=0;for(unsigned i=0;i<8;++i)v|=uint64_t(byte(address+i))<<(i*8);return v;}
static void selected(VerilatedContext& foreign) {if(Verilated::threadContextp()==&foreign)throw std::runtime_error("public phase did not select own Verilator context");}
struct Rocket {
  SavedRocketFrontend peer;std::optional<Refill> refill;std::optional<uint64_t> correction;
  unsigned consumed=0,requests=0,beats=0,replays=0;uint64_t expected=0x10000;
  std::vector<std::string> trace;
  explicit Rocket(unsigned seed):peer(seed,16){}
  void step(unsigned cycle,VerilatedContext& foreign) {
    SavedRocketFrontend::Inputs in;in.memory_request_ready=true;in.might_request=in.progress=true;
    in.id_ready=cycle%11<8;in.redirect_valid=bool(correction);if(correction)in.redirect_pc=*correction;
    in.id_ready=in.id_ready&&!in.redirect_valid;correction.reset();
    const bool returning=refill && cycle>=refill->accepted+3;
    if(returning)in.memory_data=SavedRocketFrontend::DataBeat{data(refill->line+refill->beat*8),false};
    Verilated::threadContextp(&foreign);peer.evaluate(in);selected(foreign);
    Verilated::threadContextp(&foreign);auto out=peer.evaluate(in);selected(foreign);
    std::ostringstream s;s<<cycle<<' '<<out.memory_request_valid<<' ';
    if(out.memory_request_valid){s<<out.memory_request_address;if(refill || (out.memory_request_address&63))throw std::runtime_error("Rocket request ownership");refill=Refill{out.memory_request_address,cycle,0};++requests;}
    s<<' '<<out.id.valid;
    if(out.id.valid){const auto& u=out.id;s<<' '<<u.pc<<' '<<u.raw<<' '<<u.expanded<<' '<<u.compressed<<' '<<u.replay<<' '<<u.btb_entry<<' '<<u.bht_history;
      if(u.first_access_fault||u.first_page_fault||u.first_guest_page_fault||u.second_access_fault||u.second_page_fault||u.second_guest_page_fault)throw std::runtime_error("Rocket unexpected source fault");
      if(in.id_ready){if(u.replay){correction=u.pc;++replays;}else{
        const bool compressed=(expected-0x10000)%6==0;
        if(u.pc!=expected || u.compressed!=compressed || (compressed?uint16_t(u.raw):u.raw)!=(compressed?0x0305u:0x00128293u))throw std::runtime_error("Rocket parcel identity");
        expected+=compressed?2:4;++consumed;
      }}
    }
    trace.push_back(s.str());Verilated::threadContextp(&foreign);peer.commit();selected(foreign);
    if(returning){++beats;if(++refill->beat==8)refill.reset();}
  }
};
struct Shuttle {
  SavedShuttleFrontend peer;std::optional<Refill> refill;
  unsigned consumed=0,requests=0,beats=0;uint64_t expected=0x10000;
  std::vector<std::string> trace;
  explicit Shuttle(unsigned seed):peer(seed,16){}
  void step(unsigned cycle,VerilatedContext& foreign) {
    SavedShuttleFrontend::Inputs in;in.memory_request_ready=true;
    const bool returning=refill && cycle>=refill->accepted+3;
    if(returning)in.memory_data=SavedShuttleFrontend::DataBeat{data(refill->line+refill->beat*8)};
    Verilated::threadContextp(&foreign);auto out=peer.evaluate(in);selected(foreign);
    in.ready0=cycle%11<8 && out.queue[0].valid;in.ready1=in.ready0 && out.queue[1].valid;
    Verilated::threadContextp(&foreign);out=peer.evaluate(in);selected(foreign);
    std::ostringstream s;s<<cycle<<' '<<out.memory_request_valid<<' ';
    if(out.memory_request_valid){s<<out.memory_request_address;if(refill || (out.memory_request_address&63))throw std::runtime_error("Shuttle request ownership");refill=Refill{out.memory_request_address,cycle,0};++requests;}
    for(unsigned lane=0;lane<2;++lane){const auto& u=out.queue[lane];s<<' '<<u.valid;if(!u.valid)continue;
      s<<' '<<u.pc<<' '<<u.raw<<' '<<u.expanded<<' '<<u.compressed<<' '<<u.prediction_valid<<' '<<u.btb_valid<<' '<<u.small_forward_branch;
      if(u.exception)throw std::runtime_error("Shuttle unexpected source fault");
      if(lane?in.ready1:in.ready0){const bool compressed=(expected-0x10000)%6==0;
        if(u.pc!=expected || u.compressed!=compressed || (compressed?uint16_t(u.raw):u.raw)!=(compressed?0x0305u:0x00128293u))throw std::runtime_error("Shuttle parcel identity");
        expected+=compressed?2:4;++consumed;
      }
    }
    trace.push_back(s.str());Verilated::threadContextp(&foreign);peer.commit();selected(foreign);
    if(returning){++beats;if(++refill->beat==8)refill.reset();}
  }
};
int main() {
  VerilatedContext foreign;const char* args[]={"foreign-context","+unrelated_foreign_context=1"};foreign.commandArgs(2,args);
  constexpr unsigned edges=1200;std::array<std::vector<std::string>,3> reference;
  {Rocket one(1);for(unsigned c=0;c<edges;++c)one.step(c,foreign);reference[0]=one.trace;if(one.consumed<512 || one.replays<20)throw std::runtime_error("Rocket standalone coverage");}
  {Rocket one(17);for(unsigned c=0;c<edges;++c)one.step(c,foreign);reference[1]=one.trace;}
  {Shuttle one(7);for(unsigned c=0;c<edges;++c)one.step(c,foreign);reference[2]=one.trace;if(one.consumed<512)throw std::runtime_error("Shuttle standalone coverage");}
  for(unsigned order=0;order<3;++order){
    // Reverse construction plus changing per-edge phase order. Every public
    // evaluate/commit enters with an unrelated active thread-local context.
    Shuttle shuttle(7);Rocket second(17),first(1);
    for(unsigned c=0;c<edges;++c){
      switch((c+order)%3){
        case 0:first.step(c,foreign);second.step(c,foreign);shuttle.step(c,foreign);break;
        case 1:shuttle.step(c,foreign);first.step(c,foreign);second.step(c,foreign);break;
        default:second.step(c,foreign);shuttle.step(c,foreign);first.step(c,foreign);break;
      }
    }
    if(first.trace!=reference[0] || second.trace!=reference[1] || shuttle.trace!=reference[2])throw std::runtime_error("multi-peer context/order changed physical output trace");
  }
  unsigned refused=0;
  {SavedRocketFrontend peer(1,16);SavedRocketFrontend::Inputs in;in.might_request=true;peer.evaluate(in);in.redirect_pc=uint64_t(1)<<40;try{peer.evaluate(in);}catch(const std::invalid_argument&){++refused;}try{peer.commit();}catch(const std::logic_error&){++refused;}}
  {SavedShuttleFrontend peer(1,16);SavedShuttleFrontend::Inputs in;peer.evaluate(in);in.ready1=true;try{peer.evaluate(in);}catch(const std::invalid_argument&){++refused;}try{peer.commit();}catch(const std::logic_error&){++refused;}}
  if(refused!=4)throw std::runtime_error("invalid reevaluation left stale committable inputs");
  std::cout<<"{\"status\":\"passed_frontend_owned_context_interleavings\",\"standalone_peers\":3,\"interleaving_orders\":3,\"physical_edges\":"<<edges*12<<",\"trace_rows_equal\":"<<edges*9<<",\"invalid_phase_refusals\":"<<refused<<",\"synthetic_backend_replay_delay\":1,\"source_state_injected\":false,\"native_integration\":false}\n";
}
