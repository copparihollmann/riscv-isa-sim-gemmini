#include "fast_source_frontend.hpp"
#include <array>
#include <chrono>
#include <iostream>
#include <optional>
#include <stdexcept>

using Peer=iris::frontend::FastSourceFrontend;
struct Refill{uint64_t address,due;unsigned beat=0;};
int main(int argc,char**argv){
  if(argc!=2)throw std::invalid_argument("explicit edges required");
  const uint64_t edges=std::stoull(argv[1]);
  Peer peer(1,16);std::optional<Refill>refill;
  uint64_t accepted=0,requests=0,checksum=0;
  constexpr std::array<uint8_t,16>code={0x13,0x05,0x15,0x00,0x01,0x00,0x13,0x05,
                                     0x15,0x00,0x0d,0x05,0x1b,0x85,0x17,0x00};
  const auto start=std::chrono::steady_clock::now();
  for(uint64_t edge=0;edge<edges;++edge){
    Peer::Inputs in;in.memory_request_ready=true;in.ready0=in.ready1=true;
    if(edge==32){in.redirect_flush=in.redirect_valid=true;in.redirect_pc=0x80000000;in.redirect_ras_head=5;}
    if(refill&&edge>=refill->due){
      uint64_t data=0;for(unsigned b=0;b<8;++b)data|=uint64_t(code[(refill->address+8*refill->beat+b)&15])<<(8*b);
      in.memory_data=Peer::DataBeat{data};
    }
    const auto out=peer.evaluate(in);
    for(const auto&u:out.queue)if(u.valid){++accepted;checksum^=u.pc+uint64_t(u.raw)*accepted;if(u.exception)throw std::logic_error("activebenchmarkleftqualifiedPMA");}
    const bool request=out.memory_request_valid&&in.memory_request_ready;
    peer.commit();
    if(in.memory_data&&++refill->beat==8)refill.reset();
    if(request){if(refill)throw std::logic_error("overlappingrefill");refill=Refill{out.memory_request_address,edge+3};++requests;}
  }
  const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  std::cout<<"{\"edges\":"<<edges<<",\"seconds\":"<<seconds<<",\"edges_per_second\":"<<edges/seconds
    <<",\"accepted_parcels\":"<<accepted<<",\"refills\":"<<requests<<",\"checksum\":"<<checksum
    <<",\"production_RTL_evaluation\":false,\"SoC_MIPS_claim\":false}\n";
}
