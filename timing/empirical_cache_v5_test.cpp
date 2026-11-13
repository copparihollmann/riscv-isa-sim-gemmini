#include "empirical_cache_v5.hpp"
#include <iostream>
#include <stdexcept>
using namespace iris::empirical;
static unsigned checks=0,refusals=0;static void test(bool x,const char*s){++checks;if(!x)throw std::runtime_error(s);}
template<class F>static void reject(F f){try{f();}catch(const std::exception&){++checks;++refusals;return;}throw std::runtime_error("missing refusal");}
int main(){try{
 constexpr uint64_t b=0x80000000;CacheHistoryV5 c(iris_geometry_v5());test(!c.instruction_hit(0,b+62,4),"cold crossline false");reject([&]{c.touch_instruction(0,b+62,4,0);});c.begin_instruction({1,0,b+62,4,false,0});test(!c.instruction_hit(0,b+62,4),"own uncompleted refill excluded");reject([&]{c.touch_instruction(0,b+62,4,0);});c.complete(1,1);test(c.instruction_hit(0,b+62,4),"both returned lines satisfy crossline");
 c.begin_instruction({2,1,b+62,4,false,1});test(c.instruction_hit(0,b+62,4),"foreign I pending cannot block completed private hit");auto pending=c.pending();auto d=c.touch_instruction(0,b+62,4,1);test(d.l1_hits==2&&d.l1_misses==0&&d.l2_hits==0&&d.l2_misses==0&&d.wait_for.empty(),"local I hit no NoC or owner credit");test(c.pending()==pending,"touch allocates no owner");c.complete(2,2);
 c.begin_vector({3,2,b,32,true,2});test(c.instruction_hit(0,b,4),"pending foreign vector Put cannot block Get-only I hit");c.touch_instruction(0,b,4,2);c.complete(3,3);c.begin({4,0,b,8,true,3});test(c.instruction_hit(0,b,4),"own pending D store does not invalidate private I");c.touch_instruction(0,b,4,3);c.complete(4,4);c.fence_i(0,4);test(!c.instruction_hit(0,b,4),"FENCEI clears actual I tags");reject([&]{c.touch_instruction(0,b,4,4);});
 c.begin_instruction({5,0,b+62,4,false,4});c.complete(5,5);for(unsigned i=0;i<10000;++i){test(c.instruction_hit(0,b+62,4),"crossline repeated private hit");auto x=c.touch_instruction(0,b+62,4,5);test(x.l1_hits==2,"crossline hit counts both lines");}test(c.pending()==0,"no retry-owner convoy");
 reject([&]{c.touch_instruction(0,b,4,4);});reject([&]{c.instruction_hit(3,b,4);});test(!c.instruction_hit(0,0x10000,4),"no invented ROM instruction cache");
 std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"refusals\":"<<refusals<<",\"crossline_hits\":10000,\"foreign_pending_ignored_for_private_I_hits\":true}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
