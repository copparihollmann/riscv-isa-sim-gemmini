#include "empirical_cache.hpp"
#include <algorithm>
#include <array>
#include <deque>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace iris::empirical;
static unsigned checks=0,refusals=0;
static void require(bool ok,const char*why){++checks;if(!ok)throw std::runtime_error(why);}
template<class F>static void reject(F f){try{f();}catch(const std::exception&){++checks;++refusals;return;}throw std::runtime_error("missing refusal");}
struct Run{
 CacheHistory history{iris_geometry()};uint64_t id=1,t=0;
 Delta access(unsigned h,uint64_t a,bool wr=false,uint64_t bytes=8){auto x=history.begin({id,h,a,bytes,wr,t++});history.complete(id++,t++);return x;}
};
int main(){
 try{
  constexpr uint64_t b=0x80000000;
  {Run r;auto a=r.access(0,b);require(a.l1_misses==1&&a.l2_misses==1,"cold DRAM miss");a=r.access(0,b);require(a.l1_hits==1&&a.l2_misses==0,"warm private hit");a=r.access(1,b);require(a.l1_misses==1&&a.l2_hits==1,"peer clean sharing");a=r.access(0,b,true);require(a.coherence_invalidations==1,"store invalidates sharer");a=r.access(1,b);require(a.dirty_owner_forwards==1&&a.l2_hits==1,"dirty owner read forwarding");}
  {Run r;auto a=r.history.begin({1,0,b,8,false,0});a=r.history.begin({2,1,b,8,false,0});require(a.wait_for==std::vector<uint64_t>{1},"pending owner dependence");require(a.shared_line_contenders==1&&a.same_bank_contenders==1,"shared pending contender");a=r.history.begin({3,2,b,8,false,0});require(a.wait_for.size()==2&&a.shared_line_contenders==2,"all real pending owners");reject([&]{r.history.reset_timing_tags(0);});reject([&]{r.history.complete(2,0);});r.history.complete(1,5);r.history.complete(2,5);r.history.complete(3,5);require(r.history.pending()==0,"owned completion");r.history.reset_timing_tags(5);require(r.history.begin({4,0,b,8,false,5}).l2_misses==1,"explicit timing reset clears tags");}
  {Run r;r.history.begin({1,0,b,8,false,0});auto a=r.history.begin({2,1,b+64,8,false,0});require(a.other_bank_contenders==1&&a.same_bank_contenders==0,"four-bank physical indexing");r.history.complete(2,1);a=r.history.begin({3,1,b+256,8,false,1});require(a.same_bank_contenders==1&&a.shared_line_contenders==0,"same bank independent line");}
  {Run r;r.history.begin({1,0,0x70000000,8,false,0});auto a=r.history.begin({2,1,0x70020000,8,false,0});require(a.same_bank_contenders==0&&a.other_bank_contenders==0,"separate TCM managers");a=r.history.begin({3,1,0x70000000,8,false,0});require(a.path==Path::RemoteTCM&&a.same_bank_contenders==1&&a.wait_for.size()==1,"remote local TCM shared resource");}
  {Run r;auto a=r.history.begin({1,0,0x70080000,8,false,0});require(a.canonical_address==0x70000000&&a.path==Path::LocalTCM,"own TCM alias canonicalized");a=r.history.begin({2,1,0x70000000,8,false,0});require(a.wait_for==std::vector<uint64_t>{1},"canonical peer aliases owner");auto count=r.history.pending();reject([&]{r.history.begin({3,2,0x70080000,8,false,0});});require(r.history.pending()==count,"invalid hart alias no mutation");}
  {Run r;require(r.access(0,0x580000000).path==Path::Scratchpad,"scratchpad route");require(r.access(2,0x70000000).path==Path::RemoteTCM,"hart2 TCM always remote");auto a=r.access(0,0x10020000);require(a.path==Path::Uncached&&a.l1_misses==0,"MMIO not cached RAM");}
  {Run r;auto a=r.access(0,b+63,false,8);require(a.lines==2&&a.l1_misses==2&&a.bytes==8,"unaligned crossline counted without changing functional legality");a=r.access(0,b+64);require(a.l1_hits==1,"crossline installs second line");}
  {Run r;r.access(0,b);r.access(0,b+4096);r.access(0,b);r.access(0,b+8192);require(r.access(0,b).l1_hits==1,"LRU touch preserves hot line");require(r.access(0,b+4096).l1_misses==1,"LRU evicts least recently touched");}
  {Run r;for(unsigned i=0;i<4;++i)r.access(2,b+i*4096);for(unsigned i=0;i<4;++i)require(r.access(2,b+i*4096).l1_hits==1,"Rocket four-way L1");}
  {Run r;r.access(0,b);for(unsigned i=1;i<5;++i)r.access(0,b+i*131072);auto a=r.access(0,b);require(a.l2_misses==1,"L2 four-way replacement");}
  {Run r;r.access(0,b,true);bool dirty=false;for(unsigned i=1;i<8;++i)dirty|=r.access(0,b+i*131072).l2_dirty_victims!=0;require(dirty,"dirty outer eviction work credited");}
  {Run r;reject([&]{r.history.begin({1,3,b,8,false,0});});reject([&]{r.history.begin({1,0,b,0,false,0});});reject([&]{r.history.begin({1,0,b,4097,false,0});});reject([&]{r.history.begin({1,0,std::numeric_limits<uint64_t>::max()-3,8,false,0});});reject([&]{r.history.begin({1,0,0x17fffffff,2,false,0});});reject([&]{r.history.begin({1,0,0x7001ffff,8,false,0});});reject([&]{r.history.begin({1,0,0x7009ffff,8,false,0});});r.history.begin({1,0,b,8,false,5});reject([&]{r.history.begin({1,0,b,8,false,5});});reject([&]{r.history.begin({2,0,b,8,false,4});});reject([&]{r.history.complete(1,4);});reject([&]{r.history.complete(9,6);});r.history.complete(1,6);reject([&]{r.history.complete(1,7);});reject([&]{r.history.begin({1,0,b,8,false,7});});reject([&]{r.history.begin({0,0,b,8,false,7});});}
  {auto c=iris_geometry();c.l1d[0].ways=3;reject([&]{CacheHistory x(c);});c=iris_geometry();c.l1d[0].line_bytes=32;reject([&]{CacheHistory x(c);});}
  // Independent MRU-list oracle, actual accepted address sequence only.
  // No timing/cache state from observations is supplied to the implementation.
  {Run r;std::array<std::deque<uint64_t>,64> oracle;uint64_t rng=0x12345678;
   for(unsigned n=0;n<20000;++n){rng=rng*6364136223846793005ull+1442695040888963407ull;uint64_t line=(rng>>32)%512;auto&set=oracle[line%64];auto i=std::find(set.begin(),set.end(),line);bool hit=i!=set.end();if(hit)set.erase(i);else if(set.size()==2)set.pop_back();set.push_front(line);auto a=r.access(0,b+line*64,(rng&32)!=0);require(a.l1_hits==unsigned(hit)&&a.l1_misses==unsigned(!hit),"independent LRU oracle");}
  }
  // Independent three-hart sharing/dirty-owner/LRU oracle. The footprint fits
  // L2, so its expected private-cache effects need no model-state observation.
  {Run r;struct Entry{uint64_t line;bool dirty;};std::array<std::array<std::deque<Entry>,64>,3> oracle;uint64_t rng=77;
   for(unsigned n=0;n<10000;++n){rng=rng*2862933555777941757ull+3037000493ull;unsigned h=(rng>>9)%3;uint64_t line=(rng>>32)%1024;bool wr=(rng&7)==0;auto&set=oracle[h][line%64];auto it=std::find_if(set.begin(),set.end(),[&](auto e){return e.line==line;});bool hit=it!=set.end();bool dirty=hit&&it->dirty;unsigned forwards=0,invalidations=0,victims=0;
    if(!hit)for(unsigned peer=0;peer<3;++peer)if(peer!=h){auto&ps=oracle[peer][line%64];auto p=std::find_if(ps.begin(),ps.end(),[&](auto e){return e.line==line;});if(p!=ps.end()&&p->dirty){++forwards;p->dirty=false;}}
    if(wr)for(unsigned peer=0;peer<3;++peer)if(peer!=h){auto&ps=oracle[peer][line%64];auto p=std::find_if(ps.begin(),ps.end(),[&](auto e){return e.line==line;});if(p!=ps.end()){ps.erase(p);++invalidations;}}
    if(hit)set.erase(it);else if(set.size()==(h==2?4:2)){victims=set.back().dirty;set.pop_back();}set.push_front({line,dirty||wr});
    auto a=r.access(h,b+line*64,wr);require(a.l1_hits==unsigned(hit),"three-hart independent LRU hit");require(a.dirty_owner_forwards==forwards,"three-hart independent dirty forwarding");require(a.coherence_invalidations==invalidations,"three-hart independent write invalidation");require(a.l1_dirty_victims==victims,"three-hart independent dirty eviction");
   }
  }
  std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"refusals\":"<<refusals<<",\"random_lru_accesses\":30000,\"source_geometry_lru_approximation\":true,\"hardware_or_rtl_certificate\":false}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
