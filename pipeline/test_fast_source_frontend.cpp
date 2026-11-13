#include "fast_source_frontend.hpp"
#include "frontend_rtl_peer.hpp"
#include <array>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using Ref=iris::frontend::SavedShuttleFrontend;
using Fast=iris::frontend::FastSourceFrontend;
struct Refill {uint64_t address;unsigned due,beat=0;};
int main(int argc,char**argv) {
  if(argc!=2&&argc!=3)throw std::invalid_argument("seed [pma] required");
  const bool pma=argc==3&&std::string(argv[2])=="pma";
  std::vector<uint64_t>targets;
  for(const auto&range:std::array<std::pair<uint64_t,uint64_t>,7>{{{0x3000,0x1000},{0x10000,0x10000},{0x70000000,0x40000},{0x70080000,0x80000},{0x80000000,0x100000000ULL},{0x580000000ULL,0x20000},{0x10020000,0x1000}}})for(int64_t delta:{-2,0,2}){targets.push_back(range.first+delta);targets.push_back(range.first+range.second+delta);}
  for(uint64_t address:{0ULL,0x1000ULL,0x2000ULL,0x70040000ULL,0x7007fffeULL,0x7ffffffffeULL,0x8000000000ULL,0xfffffffffeULL})targets.push_back(address);
  unsigned seed=std::stoul(argv[1]);Ref reference(seed,16);Fast fast(seed,16);
  uint64_t random=0xd1310ba698dfb5acULL^seed;
  auto rng=[&]{random^=random<<13;random^=random>>7;random^=random<<17;return random;};
  std::optional<Refill> refill;uint64_t checks=0,valid_uops=0,requests=0;
  constexpr std::array<uint8_t,16> code={0x13,0x05,0x15,0x00,0x01,0x00,0x13,0x05,
                                      0x15,0x00,0x0d,0x05,0x1b,0x85,0x17,0x00};
  for(unsigned edge=0;edge<20000;++edge) {
    const auto value=rng();Ref::Inputs in;in.memory_request_ready=(value&7)!=0;
    in.ready0=(value&16)!=0;in.ready1=in.ready0&&(value&32);
    if((!pma&&(edge==1024||edge==8096||edge==13011))||(pma&&edge>=1024&&(edge-1024)%311==0&&(edge-1024)/311<targets.size())) {
      in.redirect_flush=in.redirect_valid=true;in.redirect_pc=0x80000400+((value>>8)&63)*2;
      if(pma)in.redirect_pc=targets[(edge-1024)/311];
      in.redirect_ras_head=5;
    }
    if(refill&&edge>=refill->due&&(value&3)!=0) {
      uint64_t data=0;for(unsigned b=0;b<8;++b)data|=uint64_t(code[(refill->address+refill->beat*8+b)&15])<<(8*b);
      in.memory_data=Ref::DataBeat{data};
    }
    auto a=reference.evaluate(in),b=fast.evaluate(in);
    auto equal=[&](auto x,auto y,const char* field){++checks;if(x!=y)throw std::runtime_error(std::string(field)+" edge="+std::to_string(edge)+" ref="+std::to_string(x)+" fast="+std::to_string(y));};
    equal(a.memory_request_valid,b.memory_request_valid,"A.valid");
    if(a.memory_request_valid)equal(a.memory_request_address,b.memory_request_address,"A.address");
    for(unsigned lane=0;lane<2;++lane) {
      const auto& x=a.queue[lane];const auto& y=b.queue[lane];equal(x.valid,y.valid,"Q.valid");
      if(!x.valid)continue;++valid_uops;
      equal(x.pc,y.pc,"Q.pc");equal(x.raw,y.raw,"Q.raw");equal(x.expanded,y.expanded,"Q.expanded");
      equal(x.compressed,y.compressed,"Q.rvc");equal(x.edge_instruction,y.edge_instruction,"Q.edge");
      equal(x.exception,y.exception,"Q.exception");if(x.exception)equal(x.exception_cause,y.exception_cause,"Q.cause");
      equal(x.prediction_valid,y.prediction_valid,"Q.prediction_valid");
      if(x.prediction_valid)equal(x.predicted_pc,y.predicted_pc,"Q.predicted_pc");
      equal(x.btb_valid,y.btb_valid,"Q.btb_valid");if(x.btb_valid)equal(x.btb_entry,y.btb_entry,"Q.btb_entry");
      equal(x.bht_history,y.bht_history,"Q.history");equal(x.bht_value,y.bht_value,"Q.counter");
      equal(x.small_forward_branch,y.small_forward_branch,"Q.sfb");equal(x.ras_head,y.ras_head,"Q.ras_head");
    }
    const bool accepted=a.memory_request_valid&&in.memory_request_ready;
    reference.commit();fast.commit();
    if(in.memory_data&&++refill->beat==8)refill.reset();
    if(accepted) {
      if(refill)throw std::runtime_error("overlapping accepted reference refill");
      refill=Refill{a.memory_request_address,edge+3,0};++requests;
    }
  }
  std::cout<<"{\"pass\":true,\"edges\":20000,\"checks\":"<<checks<<",\"valid_uops\":"<<valid_uops<<",\"refills\":"<<requests<<"}\n";
}
