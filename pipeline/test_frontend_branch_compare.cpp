#include "frontend_branch.hpp"
#include "VIrisBranchCompare.h"
#include <array>
#include <iostream>
#include <stdexcept>
int main() {
  VIrisBranchCompare rtl;uint64_t checks=0;
  const std::array<uint64_t,8> corners={0,1,~uint64_t(0),uint64_t(1)<<63,(uint64_t(1)<<63)-1,0xffffffff,0xffffffff80000000,0x100000000};
  auto check=[&](uint64_t a,uint64_t b) {
    for(unsigned funct3:{0,1,4,5,6,7})for(unsigned dw:{0,1}) {
      const auto want=iris::frontend::ShuttleBranch::compare(0x63|(funct3<<12),a,b);
      const unsigned fn=funct3<2?funct3+2:funct3+8;
      rtl.io_in1=a;rtl.io_in2=b;rtl.io_fn=fn;rtl.io_dw=dw;rtl.eval();
      if(bool(rtl.shuttle_cmp)!=want || bool(rtl.rocket_cmp)!=want)throw std::runtime_error("actual ALU compare differs f3="+std::to_string(funct3));
      checks+=2;
    }
  };
  for(auto a:corners)for(auto b:corners)check(a,b);
  uint64_t seed=0x9e3779b97f4a7c15;
  auto next=[&] {seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;};
  for(unsigned i=0;i<16384;++i) {auto a=next(),b=next();check(a,b);check(a,a);}
  unsigned refuses=0;
  for(uint32_t bad:{0x13u,0x2063u,0x3063u})try {
    iris::frontend::ShuttleBranch::compare(bad,0,0);
  }catch(const std::invalid_argument&){++refuses;}
  if(refuses!=3)throw std::runtime_error("branch compare boundary silently broadened");
  std::cout<<"PASS source Shuttle+Rocket ALU branch comparisons="<<checks<<" explicit-boundary-refusals="<<refuses<<"\n";
}
