#include "empirical_cache_v8.hpp"
#include "empirical_cache_v9.hpp"
#include <array>
#include <iostream>
#include <stdexcept>
#include <tuple>
using namespace iris::empirical;
static uint64_t checks=0,refusals=0;void need(bool x){++checks;if(!x)throw std::runtime_error("V9 source random guard");}
template<class F>void reject(F f){++refusals;try{f();}catch(const std::exception&){return;}throw std::runtime_error("V9 guard admitted");}
auto fields(const Delta&d){return std::tie(d.path,d.canonical_address,d.bytes,d.lines,d.l1_hits,d.l1_misses,d.l2_hits,d.l2_misses,d.l1_dirty_victims,d.l2_dirty_victims,d.coherence_invalidations,d.dirty_owner_forwards,d.same_bank_contenders,d.other_bank_contenders,d.shared_line_contenders,d.wait_for);}
int main(){try{
 constexpr uint64_t a=0x84000000;uint64_t rng=17,t=0;
 CacheHistoryV8 old(iris_geometry_v8(),true);CacheHistoryV9 off(iris_geometry_v9(),true,false);
 for(uint64_t id=1;id<=40000;++id){rng=rng*6364136223846793005ull+1;unsigned h=(rng>>12)%3;Access x{id,h,a+((rng>>24)%512)*64,8,bool(rng&1),t++};auto b=x.write?old.begin(x):old.begin_read(x),c=x.write?off.begin(x):off.begin_read(x);need(fields(b)==fields(c));need(old.data_hit(h,x.address,8)==off.data_hit(h,x.address,8));old.complete(id,t);off.complete(id,t++);}
 CacheHistoryV9 on(iris_geometry_v9(),true,true);
 struct Tag{bool valid=false;uint64_t line=0;};std::array<std::array<std::array<Tag,2>,64>,2> tag{};std::array<uint16_t,2> state{1,1};std::array<uint64_t,3> allocations{};t=0;
 for(uint64_t id=1;id<=30000;++id){rng=rng*6364136223846793005ull+1;unsigned h=(rng>>12)%2;const uint64_t line=(a/64)+h*1024+(rng>>24)%256;auto&set=tag[h][line%64];bool hit=false;for(auto&q:set)hit|=q.valid&&q.line==line;
  auto d=on.begin_read({id,h,line*64,8,false,t++});need(d.l1_hits==uint64_t(hit)&&d.l1_misses==uint64_t(!hit));
  if(!hit){unsigned way=state[h]&1;set[way]={true,line};uint16_t s=state[h];state[h]=uint16_t((s<<1)|(((s>>10)^(s>>12)^(s>>13)^(s>>15))&1));++allocations[h];}
  on.complete(id,t++);need(on.data_hit(h,line*64,8));need(on.source_random_allocations()==allocations);
 }
 // Accepted old response cannot validate a replacement generation.
 CacheHistoryV9 e(iris_geometry_v9(),true,true);const auto b=a+4096,c=a+8192;
 e.begin_read({1,0,a,8,false,0});e.begin_read({2,0,b,8,false,1});e.begin_read({3,0,c,8,false,2});need(!e.data_hit(0,b,8)&&!e.data_hit(0,c,8));e.complete(2,3);need(!e.data_hit(0,c,8));e.complete(1,4);e.complete(3,5);need(e.data_hit(0,c,8));
 auto n=e.source_random_allocations();e.begin_read({4,0,c,8,false,6});need(e.source_random_allocations()==n);e.complete(4,7);e.fence_i(0,8);need(e.source_random_allocations()==n);
 e.begin({5,1,c,8,true,9});need(!e.data_hit(0,c,8));e.complete(5,10,false);need(!e.data_hit(1,c,8));
 e.begin_read({6,0,c,8,false,11});e.complete(6,12,false);need(!e.data_hit(0,c,8));
 n=e.source_random_allocations();e.reset_timing_tags(13);need(e.source_random_allocations()==n);e.begin_read({7,0,c,8,false,14});e.complete(7,15);need(e.source_random_allocations()[0]==n[0]+1);
 // Rocket, Icache and vector bypass do not advance Shuttle replacement state.
 n=e.source_random_allocations();e.begin_read({8,2,a,8,false,16});e.complete(8,17);e.begin_instruction({9,0,a+64,8,false,18});e.complete(9,19);e.begin_vector({10,0,a+128,8,false,20});e.complete(10,21);need(e.source_random_allocations()==n);
 auto cfg=iris_geometry_v9();cfg.l1d[0].ways=4;reject([&]{CacheHistoryV9 bad(cfg,true,true);});
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"guard_refusals\":"<<refusals<<",\"OFF_V8_requests\":40000,\"source_selector_oracle_requests\":30000,\"harts\":[0,1],\"Rocket_policy_changed\":false,\"matching_generation_fault_writer_guards\":true,\"full_RTL_cache_phase_certified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
