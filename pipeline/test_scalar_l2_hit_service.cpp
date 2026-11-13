#include "scalar_l2_hit_service.hpp"
#include <iostream>
#include <stdexcept>
using namespace iris::empirical;
static uint64_t checks=0;
static void need(bool value){++checks;if(!value)throw std::runtime_error("scalar L2-hit service check");}
template<class F>static void refuses(F f){bool bad=false;try{f();}catch(const std::runtime_error&){bad=true;}need(bad);}
int main(){try{
  Delta hit{};hit.path=Path::DRAM;hit.l1_misses=1;hit.l2_hits=1;
  ScalarL2HitService off;need(off.charge(hit,L2ServiceActor::ScalarLoad)==0);
  ScalarL2HitService cost;cost.configure(.25,100000);
  for(unsigned i=0;i<10000;++i){
    for(auto actor:{L2ServiceActor::ScalarStore,L2ServiceActor::VectorMemory,L2ServiceActor::Atomic,L2ServiceActor::Instruction,L2ServiceActor::Other})need(cost.charge(hit,actor)==0);
    need(cost.charge(hit,L2ServiceActor::ScalarLoad)==(i%4==3));
  }
  need(cost.stats().accepted_loads==10000&&cost.stats().l2_hits==10000&&cost.stats().charged_cycles==2500);
  for(auto path:{Path::LocalTCM,Path::RemoteTCM,Path::Scratchpad,Path::Uncached}){auto d=hit;d.path=path;need(cost.charge(d,L2ServiceActor::ScalarLoad)==0);}
  auto outer=hit;outer.l2_hits=0;outer.l2_misses=1;need(cost.charge(outer,L2ServiceActor::ScalarLoad)==0);
  auto warm=hit;warm.l1_hits=1;warm.l1_misses=0;warm.l2_hits=0;need(cost.charge(warm,L2ServiceActor::ScalarLoad)==0);
  auto multi=hit;multi.l1_misses=8;multi.l2_hits=7;multi.l2_misses=1;need(cost.charge(multi,L2ServiceActor::ScalarLoad)==1);
  auto wrong=hit;wrong.l2_hits=2;refuses([&]{cost.charge(wrong,L2ServiceActor::ScalarLoad);});
  // Excluded actors never inspect or advance the scalar cost state.
  need(cost.charge(wrong,L2ServiceActor::VectorMemory)==0);
  refuses([&]{cost.configure(1,100);});
  for(double c:{-1.,double(INFINITY),double(NAN)}){ScalarL2HitService s;refuses([&]{s.configure(c,100);});}
  ScalarL2HitService small;small.configure(50,100);auto d=hit;d.l1_misses=3;d.l2_hits=3;refuses([&]{small.charge(d,L2ServiceActor::ScalarLoad);});
  std::cout<<"{\"pass\":true,\"checks\":"<<checks<<"}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
