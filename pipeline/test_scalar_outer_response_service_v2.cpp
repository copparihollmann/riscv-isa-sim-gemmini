#include "scalar_outer_response_service_v2.hpp"
#include <iostream>
#include <stdexcept>
using namespace iris::empirical;
static uint64_t checks=0;
static void need(bool v){++checks;if(!v)throw std::runtime_error("scalar outer response check");}
template<class F>void refuses(F f){bool yes=false;try{f();}catch(const std::runtime_error&){yes=true;}need(yes);}
int main(){try{
  Delta outer{};outer.path=Path::DRAM;outer.l1_misses=1;outer.l2_misses=1;
  ScalarOuterResponseService service;service.configure(.25,100000);
  ScalarL2HitService alpha;alpha.configure(7,100000);
  for(unsigned i=0;i<10000;++i){
    for(auto a:{L2ServiceActor::ScalarStore,L2ServiceActor::VectorMemory,L2ServiceActor::Atomic,L2ServiceActor::Instruction,L2ServiceActor::Other})need(service.charge(outer,a)==0);
    need(service.charge(outer,L2ServiceActor::ScalarLoad)==(i%4==3));
    need(alpha.charge(outer,L2ServiceActor::ScalarLoad)==0);
  }
  auto hit=outer;hit.l2_hits=1;hit.l2_misses=0;need(service.charge(hit,L2ServiceActor::ScalarLoad)==0);need(alpha.charge(hit,L2ServiceActor::ScalarLoad)==7);
  for(auto path:{Path::LocalTCM,Path::RemoteTCM,Path::Scratchpad,Path::Uncached}){auto d=outer;d.path=path;need(service.charge(d,L2ServiceActor::ScalarLoad)==0);}
  need(service.stats().charged_cycles==2500&&service.stats().l2_misses==10000);
  auto bad=outer;bad.l2_hits=1;refuses([&]{service.charge(bad,L2ServiceActor::ScalarLoad);});need(service.charge(bad,L2ServiceActor::VectorMemory)==0);
  refuses([&]{service.configure(1,100);});
  for(double c:{-1.,double(INFINITY),double(NAN)}){ScalarOuterResponseService s;refuses([&]{s.configure(c,100);});}
  ScalarOuterResponseService small;small.configure(50,100);auto d=outer;d.l1_misses=d.l2_misses=3;refuses([&]{small.charge(d,L2ServiceActor::ScalarLoad);});
  std::cout<<"{\"pass\":true,\"checks\":"<<checks<<"}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
