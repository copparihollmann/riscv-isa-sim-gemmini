#include "frontend_rtl_peer.hpp"
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>

using Peer=iris::frontend::SavedShuttleFrontend;
struct Refill {uint64_t line;unsigned accepted_at,beat=0;};
static uint8_t program_byte(uint64_t address) {
  static constexpr uint8_t bytes[]={0x05,0x03,0x93,0x82,0x12,0x00};
  if(address<0x10000 || address>=0x11000)throw std::runtime_error("synthetic ROM lookup outside qualified source PMA");
  return bytes[(address-0x10000)%6];
}
int main() {
  unsigned refusals=0;
  const auto refuses=[&](auto f){try{f();}catch(const std::exception&){++refusals;return;}throw std::runtime_error("invalid peer call accepted");};
  refuses([]{Peer bad(1,0);});
  refuses([]{Peer bad(0,16);});
  refuses([]{Peer bad(uint64_t(1)<<40,16);});
  Peer peer(1,16);Peer::Inputs inputs;
  refuses([&]{peer.commit();});
  inputs.ready1=true;refuses([&]{peer.evaluate(inputs);});inputs.ready1=false;
  inputs.redirect_pc=uint64_t(1)<<40;refuses([&]{peer.evaluate(inputs);});inputs.redirect_pc=0;
  inputs.memory_data=Peer::DataBeat{0};refuses([&]{peer.evaluate(inputs);});inputs.memory_data.reset();
  std::optional<Refill> refill;uint64_t expected_pc=0x10000;unsigned consumed=0,requests=0,beats=0;
  std::map<uint64_t,unsigned> lines;
  bool redirected_during_refill=false,invalidated=false;
  unsigned data_after_redirect=0,accepted_before_redirect=0,stalled_request_edges=0;
  // The sole service source is this explicit synthetic ROM peer: A may be
  // stalled; first D is three local edges after A, subsequent beats have
  // periodic gaps. Redirects cannot withdraw an accepted refill.
  for(unsigned cycle=0;cycle<30000 && consumed<512;++cycle) {
    inputs={};inputs.memory_request_ready=cycle>=7;
    inputs.ready0=inputs.ready1=(cycle%11)<8;
    const bool returning=refill && cycle>=refill->accepted_at+3 && cycle%5!=0;
    if(returning) {
      uint64_t value=0;for(unsigned b=0;b<8;++b)value|=uint64_t(program_byte(refill->line+refill->beat*8+b))<<(b*8);
      inputs.memory_data=Peer::DataBeat{value};
    }
    if(!redirected_during_refill && refill && refill->beat==2) {
      inputs.redirect_flush=inputs.redirect_valid=true;inputs.redirect_pc=0x10804;
      expected_pc=0x10804;redirected_during_refill=true;accepted_before_redirect=requests;
      inputs.ready0=inputs.ready1=false;
    } else if(!invalidated && consumed>=256 && !refill) {
      inputs.redirect_flush=inputs.redirect_valid=inputs.invalidate_icache=true;
      inputs.redirect_pc=0x10804;expected_pc=0x10804;invalidated=true;inputs.ready0=inputs.ready1=false;
    }
    const auto outputs=peer.evaluate(inputs);
    // Fixed-point reevaluation at one edge has no state transition.
    const auto repeated=peer.evaluate(inputs);
    if(outputs.memory_request_valid!=repeated.memory_request_valid || outputs.memory_request_address!=repeated.memory_request_address)
      throw std::runtime_error("source peer changed state during evaluate");
    if(outputs.memory_request_valid && !inputs.memory_request_ready)++stalled_request_edges;
    if(outputs.memory_request_valid && inputs.memory_request_ready) {
      if(refill || outputs.memory_request_address&63)throw std::runtime_error("invalid source request handshake");
      refill=Refill{outputs.memory_request_address,cycle,0};++requests;++lines[refill->line];
    }
    for(unsigned lane=0;lane<2;++lane) {
      const auto& u=outputs.queue[lane];
      if(!u.valid || !(lane?inputs.ready1:inputs.ready0))continue;
      if(u.exception || u.pc!=expected_pc)throw std::runtime_error("source peer queue lost parcel ordering atpc="+std::to_string(u.pc)+",expected="+std::to_string(expected_pc));
      const bool compressed=(expected_pc-0x10000)%6==0;
      if(u.compressed!=compressed || (compressed?uint16_t(u.raw):u.raw)!=(compressed?0x0305u:0x00128293u) || u.expanded!=(compressed?0x00130313u:0x00128293u))
        throw std::runtime_error("source peer queue raw/expanded parcel mismatch");
      expected_pc+=compressed?2:4;++consumed;
    }
    peer.commit();
    if(returning){++beats;if(redirected_during_refill && requests==accepted_before_redirect)++data_after_redirect;if(++refill->beat==8)refill.reset();}
  }
  if(consumed<512 || !invalidated || !redirected_during_refill || data_after_redirect<6 || lines[0x10800]<2 || !stalled_request_edges || requests<20 || beats<150 || refusals!=7)
    throw std::runtime_error("incomplete source frontend redirect/refill/invalidation exercise");
  std::cout<<"{\"status\":\"passed_source_frontend_peer\",\"consumed_uops\":"<<consumed<<",\"requests\":"<<requests<<",\"data_beats\":"<<beats
           <<",\"accepted_refill_beats_after_redirect\":"<<data_after_redirect<<",\"invalidated_line_refills\":"<<lines[0x10800]<<",\"stalled_request_edges\":"<<stalled_request_edges
           <<",\"refusals\":"<<refusals<<",\"reset_only\":true,\"native_integration\":false,\"calibrated\":false}\n";
}
