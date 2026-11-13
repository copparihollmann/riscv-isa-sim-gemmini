#include "empirical_cache_v4.hpp"
#include <iostream>
#include <stdexcept>
using namespace iris::empirical;
static unsigned checks=0,refusals=0;
static void test(bool x,const char*s){++checks;if(!x)throw std::runtime_error(s);}
template<class F>static void reject(F f){try{f();}catch(const std::exception&){++checks;++refusals;return;}throw std::runtime_error("missing refusal");}
struct Run{CacheHistoryV4 c{iris_geometry_v4()};uint64_t id=1,t=0;Delta access(unsigned h,uint64_t a,bool vector=false,bool wr=false,uint64_t bytes=8){auto d=vector?c.begin_vector({id,h,a,bytes,wr,t}):c.begin({id,h,a,bytes,wr,t});c.complete(id++,++t);return d;}};
int main(){try{
 constexpr uint64_t b=0x80000000;
 {Run r;auto d=r.access(2,b,true);test(d.l1_hits==0&&d.l1_misses==0&&d.l2_misses==1,"vector cold bypass miss");test(!r.c.data_hit(2,b,8),"vector does not allocate scalar Dcache");d=r.access(2,b,true);test(d.l2_hits==1&&d.l1_hits==0,"vector warm still L2 not private");d=r.access(2,b);test(d.l1_misses==1&&d.l2_hits==1,"scalar fills own D after vector");}
 {Run r;r.access(0,b,false,true);auto d=r.access(0,b,true);test(d.dirty_owner_forwards==1&&d.l2_hits==1,"own dirty owner probes on vector read");test(r.c.data_hit(0,b,8),"vector Get retains clean own Dcopy");r.access(1,b);d=r.access(0,b,true,true);test(d.coherence_invalidations==2,"vector Put invalidates all private D including own");test(!r.c.data_hit(0,b,8)&&!r.c.data_hit(1,b,8),"no stale own checksum Dhit after vector Put");}
 {Run r;r.c.begin_instruction({1,0,b,4,false,0});r.c.complete(1,1);r.id=2;r.t=1;auto d=r.access(1,b,true,true);test(d.l1_hits==0&&d.l2_hits==1,"vector Put on instruction shared L2");d=r.c.begin_instruction({r.id,0,b,4,false,r.t});test(d.l1_hits==1,"vector Put cannot invalidate Get-only Icache");r.c.complete(r.id++,++r.t);r.c.fence_i(0,r.t);d=r.c.begin_instruction({r.id,0,b,4,false,r.t});test(d.l1_misses==1&&d.l2_hits==1,"fenced instruction refill sees shared L2");}
 {Run r;r.c.begin({1,0,b,8,true,0});auto d=r.c.begin_vector({2,2,b,32,false,0});test(d.wait_for==std::vector<uint64_t>{1},"vector read waits pending scalar write");reject([&]{r.c.complete(2,1);});r.c.complete(1,2);r.c.complete(2,2);d=r.c.begin_vector({3,2,b,32,true,2});auto load=r.c.begin({4,0,b,8,false,2});test(load.wait_for==std::vector<uint64_t>{3},"scalar read waits accepted vector Put");reject([&]{r.c.complete(4,3);});r.c.complete(3,4);r.c.complete(4,4);}
 {Run r;auto d=r.access(0,b+32,true,false,128);test(d.lines==3&&d.l2_misses==3&&d.l1_misses==0,"crossline vector probes actual coverage");d=r.access(0,b+32,true,false,128);test(d.l2_hits==3,"vector coverage reuse in L2");d=r.access(0,0x70000000,true);test(d.path==Path::LocalTCM&&d.l2_hits==0,"uncached vector TCM route unchanged");}
 // Read/write reuse must never turn vector traffic into a private hit.
 {Run r;for(unsigned n=0;n<20000;++n){unsigned h=n%3;uint64_t address=b+64*(n%1024);auto d=r.access(h,address,true,(n&3)==0,32);test(d.l1_hits==0&&d.l1_misses==0,"streaming vector bypass independent of warm state");test(!r.c.data_hit(h,address,8),"streaming vector leaves no private copy");}}
 std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"refusals\":"<<refusals<<",\"vector_accesses\":20000,\"private_l1_allocation\":false,\"source_image_association_verified\":false}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
