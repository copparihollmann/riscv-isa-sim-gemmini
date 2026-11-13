#include "empirical_cache_v5.hpp"
#include "empirical_cache_v6.hpp"
#include <iostream>
#include <stdexcept>
#include <tuple>

using namespace iris::empirical;
static uint64_t checks=0,refusals=0,owned=0;
static void require(bool value){++checks;if(!value)throw std::runtime_error("owned-store cache check failed");}
template<class F>static void reject(F action){++refusals;try{action();}catch(const std::exception&){return;}throw std::runtime_error("guard did not reject");}
static auto fields(const Delta&d){return std::tie(d.path,d.canonical_address,d.bytes,d.lines,d.l1_hits,d.l1_misses,d.l2_hits,d.l2_misses,d.l1_dirty_victims,d.l2_dirty_victims,d.coherence_invalidations,d.dirty_owner_forwards,d.same_bank_contenders,d.other_bank_contenders,d.shared_line_contenders,d.wait_for);}
int main(){
 constexpr uint64_t base=0x80000000ull;
 for(unsigned h=0;h<3;++h){
  CacheHistoryV6 c(iris_geometry_v6());uint64_t id=0,t=0;
  require(!c.owned_store_hit(h,base,8));
  reject([&]{c.begin_owned_store({1,h,base,8,true,0});});
  // Failed admission does not consume the owner identifier.
  c.begin({++id,h,base,8,false,++t});require(!c.owned_store_hit(h,base,8));c.complete(id,++t);
  require(c.data_hit(h,base,8));require(!c.owned_store_hit(h,base,8));
  c.begin({++id,h,base,8,true,++t});require(!c.owned_store_hit(h,base,8));c.complete(id,++t);
  for(unsigned n: {1u,2u,4u,8u})require(c.owned_store_hit(h,base,n));
  for(unsigned n: {3u,16u,64u,128u})require(!c.owned_store_hit(h,base,n));
  require(!c.owned_store_hit(h,base+1,8));
  for(uint64_t address:{0x70000000ull,0x70080000ull,0x580000000ull,0x10020000ull,0x180000000ull})require(!c.owned_store_hit(h,address,8));
  reject([&]{c.owned_store_hit(3,base,8);});reject([&]{c.owned_store_hit(h,base,0);});
  reject([&]{c.begin_owned_store({id+1,h,base,8,false,t});});
  require(c.owned_store_hit(h,base,8));
  auto d=c.begin_owned_store({++id,h,base,8,true,++t});require(d.l1_hits==1&&d.l2_misses==0&&d.coherence_invalidations==0&&d.wait_for.empty());
  require(!c.owned_store_hit(h,base,8));c.complete(id,++t);require(c.owned_store_hit(h,base,8));
  // Foreign unrelated work cannot block an already-private Dcache line.
  const auto peer=(h+1)%3;auto pending=++id;c.begin({pending,peer,base+0x4000,8,false,++t});
  require(c.owned_store_hit(h,base,8));c.complete(pending,++t);
  // A foreign Get and a vector bypass Get both revoke dirty exclusivity.
  d=c.begin({++id,peer,base,8,false,++t});require(d.dirty_owner_forwards==1);require(!c.owned_store_hit(h,base,8));c.complete(id,++t);
  require(!c.owned_store_hit(h,base,8)&&!c.owned_store_hit(peer,base,8));
  c.begin({++id,h,base,8,true,++t});c.complete(id,++t);require(c.owned_store_hit(h,base,8));
  d=c.begin_vector({++id,peer,base,8,false,++t});require(d.dirty_owner_forwards==1);require(!c.owned_store_hit(h,base,8));c.complete(id,++t);
  c.begin({++id,h,base,8,true,++t});c.complete(id,++t);require(c.owned_store_hit(h,base,8));
  c.fence_i(h,++t);require(c.owned_store_hit(h,base,8));c.reset_timing_tags(++t);require(!c.owned_store_hit(h,base,8));
 }
 {
  auto cfg=iris_geometry_v6();cfg.l2={1,1,1,64};for(auto&g:cfg.l1d)g={1,1,1,64};
  CacheHistoryV6 c(cfg);c.begin({1,0,base,8,true,0});c.complete(1,1);require(c.owned_store_hit(0,base,8));
  c.begin({2,1,base+64,8,false,2});c.complete(2,3);require(!c.owned_store_hit(0,base,8));
 }
 // Legacy behavior is byte-for-byte equivalent under deterministic mixed
 // scalar/Icache/vector traffic. Predicate calls cannot mutate the history.
 CacheHistoryV5 before(iris_geometry_v5());CacheHistoryV6 after(iris_geometry_v6());uint64_t rng=0x1585434a3ull,t=0;
 for(uint64_t id=1;id<=50000;++id){
  rng=rng*6364136223846793005ull+1442695040888963407ull;
  unsigned h=(rng>>32)%3,mode=(rng>>8)%5;uint64_t address=base+((rng>>16)%4096)*64,bytes=1ull<<((rng>>7)%4);bool write=mode<2;
  const bool admitted=after.owned_store_hit(h,address,bytes);
  const bool hit_before=before.data_hit(h,address,bytes);require(after.data_hit(h,address,bytes)==hit_before);
  Access access{id,h,address,bytes,write,++t};Delta a,b;
  if(mode==3){access.write=false;a=before.begin_instruction(access);b=after.begin_instruction(access);}
  else if(mode==4){access.write=(rng>>5)&1;a=before.begin_vector(access);b=after.begin_vector(access);}
  else{a=before.begin(access);if(write&&admitted){b=after.begin_owned_store(access);++owned;}else b=after.begin(access);}
  require(fields(a)==fields(b));before.complete(id,++t);after.complete(id,t);require(before.pending()==after.pending());
 }
 require(owned>50);
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"guard_refusals\":"<<refusals<<",\"legacy_parity_requests\":50000,\"owned_store_requests\":"<<owned<<"}\n";
}
