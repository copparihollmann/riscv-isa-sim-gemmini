#include "empirical_cache_v2.hpp"
#include <algorithm>
#include <array>
#include <deque>
#include <iostream>
#include <stdexcept>
using namespace iris::empirical;
static unsigned checks=0,refusals=0;
static void test(bool ok,const char*s){++checks;if(!ok)throw std::runtime_error(s);}
template<class F>static void reject(F f){try{f();}catch(const std::exception&){++checks;++refusals;return;}throw std::runtime_error("missing refusal");}
struct Run{CacheHistoryV2 cache{iris_geometry_v2()};uint64_t id=1,t=0;Delta access(unsigned h,uint64_t a,bool instruction,bool write=false){auto d=instruction?cache.begin_instruction({id,h,a,4,write,t++}):cache.begin({id,h,a,8,write,t++});cache.complete(id++,t++);return d;}};
int main(){try{
 constexpr uint64_t b=0x80000000;
 {Run r;auto d=r.access(0,b,true);test(d.l1_misses==1&&d.l2_misses==1,"cold instruction refill");d=r.access(0,b,true);test(d.l1_hits==1,"instruction reuse");d=r.access(0,b,false);test(d.l1_misses==1&&d.l2_hits==1,"data Icache separation shared L2");r.access(1,b,true);r.access(0,b,false,true);test(r.access(1,b,true).l1_hits==1,"Get-only Icache not Dstore invalidated");r.cache.fence_i(0,r.t);test(r.access(0,b,true).l1_misses==1,"local FENCEI clears Icache");test(r.access(1,b,true).l1_hits==1,"local FENCEI preserves peer Icache");test(r.access(0,b,false).l1_hits==1,"FENCEI preserves data cache");}
 {Run r;r.access(0,b,true);for(unsigned i=1;i<6;++i)r.access(0,b+i*131072,false);test(r.access(0,b,true).l1_hits==1,"L2 eviction cannot probe Get-only Icache");r.cache.fence_i(0,r.t);test(r.access(0,b,true).l2_misses==1,"FENCEI then actual outer miss");}
 {Run r;r.access(0,b,false,true);auto d=r.access(0,b,true);test(d.dirty_owner_forwards==1&&d.l2_hits==1,"own dirty Dcache supplies Icache refill");}
 {Run r;r.cache.begin({1,0,b,8,true,0});auto d=r.cache.begin_instruction({2,0,b,4,false,0});test(d.wait_for==std::vector<uint64_t>{1},"same-hart pending data ownership protects instruction refill");reject([&]{r.cache.complete(2,1);});reject([&]{r.cache.fence_i(0,1);});r.cache.complete(1,2);r.cache.complete(2,2);r.cache.fence_i(0,2);}
 {Run r;r.cache.begin_instruction({1,0,b,4,false,0});auto d=r.cache.begin({2,1,b,8,true,0});test(d.wait_for==std::vector<uint64_t>{1},"data cannot bypass pending instruction transaction");reject([&]{r.cache.complete(2,1);});r.cache.complete(1,2);r.cache.complete(2,2);}
 {Run r;r.access(2,b,true);r.access(2,b+8192,true);test(r.access(2,b,true).l1_hits==1,"Rocket Icache two ways128sets");r.access(2,b+16384,true);test(r.access(2,b+8192,true).l1_misses==1,"Rocket Icache LRU evicts third same-set tag");}
 {Run r;auto n=r.cache.pending();reject([&]{r.cache.begin_instruction({1,0,b,4,true,0});});test(r.cache.pending()==n,"instruction write refusal no mutation");reject([&]{r.cache.fence_i(3,0);});r.access(0,b,true);reject([&]{r.cache.fence_i(0,0);});}
 {Run r;auto d=r.access(0,0x10000,true);test(d.path==Path::Uncached&&d.l1_misses==0,"no invented ROM cache policy");d=r.access(1,0x70020000,true);test(d.path==Path::LocalTCM&&d.l1_misses==0,"no invented TCM instruction cache policy");}
 // Independent two-private-cache oracle with shared dirty data ownership.
 // Footprint fits L2; never reads or injects implementation state/readiness.
 {Run r;struct E{uint64_t line;bool dirty;};std::array<std::array<std::deque<E>,128>,3> data,inst;uint64_t rng=19;
  for(unsigned n=0;n<30000;++n){rng=rng*6364136223846793005ull+1442695040888963407ull;unsigned h=(rng>>7)%3;bool instruction=(rng&4)!=0;bool wr=!instruction&&(rng&7)==1;uint64_t line=(rng>>32)%1024;unsigned sets=instruction&&h==2?128:64,ways=!instruction&&h==2?4:2;auto&set=instruction?inst[h][line%sets]:data[h][line%sets];auto found=std::find_if(set.begin(),set.end(),[&](E e){return e.line==line;});bool hit=found!=set.end(),dirty=hit&&found->dirty;unsigned forward=0,invalidate=0;
   if(!hit)for(unsigned p=0;p<3;++p)if(instruction||p!=h){auto&ps=data[p][line%64];auto i=std::find_if(ps.begin(),ps.end(),[&](E e){return e.line==line;});if(i!=ps.end()&&i->dirty){++forward;i->dirty=false;}}
   if(wr)for(unsigned p=0;p<3;++p)if(p!=h){auto&ps=data[p][line%64];auto i=std::find_if(ps.begin(),ps.end(),[&](E e){return e.line==line;});if(i!=ps.end()){ps.erase(i);++invalidate;}}
   if(hit)set.erase(found);else if(set.size()==ways)set.pop_back();set.push_front({line,dirty||wr});auto d=r.access(h,b+line*64,instruction,wr);test(d.l1_hits==unsigned(hit),"independent mixed I/D LRU");test(d.dirty_owner_forwards==forward,"independent mixed dirty forwarding");test(d.coherence_invalidations==invalidate,"independent Get-only Icache coherence");
   if(n%307==0){r.cache.fence_i(h,r.t);for(auto&is:inst[h])is.clear();}
  }
 }
 std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"refusals\":"<<refusals<<",\"mixed_instruction_data_accesses\":30000,\"replacement_policy\":\"LRU_approximation\",\"source_image_association_verified\":false}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
