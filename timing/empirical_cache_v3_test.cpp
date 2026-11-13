#include "empirical_cache_v3.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace iris::empirical;
static unsigned checks=0,refusals=0;
static void test(bool x,const char*s){++checks;if(!x)throw std::runtime_error(s);}
template<class F>static void reject(F f){try{f();}catch(const std::exception&){++checks;++refusals;return;}throw std::runtime_error("missing query refusal");}
int main(){try{
 constexpr uint64_t b=0x80000000;CacheHistoryV3 c(iris_geometry_v3());
 test(!c.data_hit(0,b,8),"cold query false");test(c.pending()==0,"cold query no accepted owner");
 auto d=c.begin({1,0,b,8,false,0});test(d.l2_misses==1,"query did not install cache line");test(!c.data_hit(0,b,8),"inflight line not a completed hit");c.complete(1,1);test(c.data_hit(0,b,8),"completed private hit");
 test(!c.data_hit(1,b,8),"private hit does not invent peer copy");test(!c.data_hit(0,b+60,8),"crossline query requires all lines");c.begin({2,0,b+64,8,false,1});c.complete(2,2);test(c.data_hit(0,b+60,8),"completed crossline hit");
 c.begin_instruction({3,1,b,4,false,2});test(!c.data_hit(0,b,8),"pending instruction owner forbids bypass");c.complete(3,3);test(c.data_hit(0,b,8),"completed peer instruction leaves data tags");
 c.begin({4,1,b,8,true,3});test(!c.data_hit(0,b,8),"pending peer store invalidates private prediction");c.complete(4,4);test(!c.data_hit(0,b,8),"completed peer store leaves private miss");test(c.data_hit(1,b,8),"writer own private hit after completion");
 for(unsigned h=0;h<3;++h){test(!c.data_hit(h,0x10000,4),"ROM query not admitted");test(!c.data_hit(h,0x70080000,8),"TCM alias query not admitted");test(!c.data_hit(h,0x580000000,8),"scratch query not admitted");}
 reject([&]{c.data_hit(3,b,8);});reject([&]{c.data_hit(0,b,0);});reject([&]{c.data_hit(0,b,4097);});reject([&]{c.data_hit(0,std::numeric_limits<uint64_t>::max()-1,8);});test(!c.data_hit(0,0x17fffffff,2),"region-crossing query not admitted");
 // Nonmutation proof: repeated lookups must not change LRU recency.
 CacheHistoryV3 lru(iris_geometry_v3());uint64_t id=1,t=0;
 for(uint64_t line:{b,b+4096}){lru.begin({id,0,line,8,false,t});lru.complete(id++,++t);}
 for(unsigned n=0;n<10000;++n){test(lru.data_hit(0,b,8),"repeated lookup hit");}
 lru.begin({id,0,b+8192,8,false,t});lru.complete(id++,++t);test(!lru.data_hit(0,b,8)&&lru.data_hit(0,b+4096,8),"lookup did not refresh LRU");
 std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"refusals\":"<<refusals<<",\"nonmutating_queries\":10000,\"hardware_state_inputs\":false}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
