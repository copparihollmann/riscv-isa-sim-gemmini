#include "empirical_cache_v6.hpp"
#include "empirical_cache_v8.hpp"
#include <iostream>
#include <stdexcept>
#include <tuple>
using namespace iris::empirical;
static unsigned checks=0,rejections=0;
void check(bool x){++checks;if(!x)throw std::runtime_error("read ownership check");}
template<class F>void reject(F f){++rejections;try{f();}catch(const std::exception&){return;}throw std::runtime_error("guard accepted");}
auto fields(const Delta&d){return std::tie(d.path,d.canonical_address,d.bytes,d.lines,d.l1_hits,d.l1_misses,d.l2_hits,d.l2_misses,d.l1_dirty_victims,d.l2_dirty_victims,d.coherence_invalidations,d.dirty_owner_forwards,d.same_bank_contenders,d.other_bank_contenders,d.shared_line_contenders,d.wait_for);}
int main(){
 constexpr uint64_t a=0x84000000ull;uint64_t id=0,t=0;
 CacheHistoryV8 c(iris_geometry_v8(),true);
 auto cold=c.begin_read({++id,0,a,8,false,t++});check(cold.l1_misses==1);check(!c.data_hit(0,a,8));
 auto second=c.begin_read({++id,0,a,8,false,t++});check(second.wait_for==std::vector<uint64_t>{1});reject([&]{c.complete(2,t);});
 c.complete(1,t++);check(c.data_hit(0,a,8));c.complete(2,t++);check(c.data_hit(0,a,8));
 c.begin_read({++id,1,a,8,false,t++});c.complete(id,t++);c.begin_read({++id,2,a,8,false,t++});c.complete(id,t++);
 auto first=id+1;c.begin_read({++id,0,a,8,false,t++});check(c.data_hit(1,a,8));
 auto next=id+1;auto d=c.begin_read({++id,1,a,8,false,t++});check(d.wait_for.empty()&&d.shared_line_contenders==0&&d.same_bank_contenders==0&&d.l1_hits==1);
 // Compatible readers may complete in the opposite order; writes remain behind both.
 auto writer=id+1;d=c.begin({++id,2,a,8,true,t++});check(d.wait_for==std::vector<uint64_t>({first,next}));check(!c.data_hit(0,a,8));reject([&]{c.complete(writer,t);});
 auto later=id+1;d=c.begin_read({++id,0,a,8,false,t++});check(d.wait_for==std::vector<uint64_t>({first,next,writer}));reject([&]{c.complete(later,t);});
 c.complete(next,t++);c.complete(first,t++);c.complete(writer,t++);c.complete(later,t++);check(c.pending()==0);
 // LR/atomics/unspecified callers are deliberately unknown even when write=false.
 first=id+1;c.begin({++id,0,a,8,false,t++});check(!c.data_hit(0,a,8));d=c.begin_read({++id,0,a,8,false,t++});check(d.wait_for==std::vector<uint64_t>{first});c.complete(first,t++);c.complete(id,t++);
 reject([&]{c.begin_read({id+1,0,a,8,true,t});});
 // No read overlap relaxation for TCM/MMIO/vector/instruction or not-ready copies.
 first=id+1;c.begin_read({++id,0,0x70000000,8,false,t++});d=c.begin_read({++id,1,0x70000000,8,false,t++});check(d.wait_for==std::vector<uint64_t>{first});c.complete(first,t++);c.complete(id,t++);
 first=id+1;c.begin_vector({++id,1,a,8,false,t++});check(!c.data_hit(0,a,8));d=c.begin_read({++id,0,a,8,false,t++});check(d.wait_for==std::vector<uint64_t>{first});c.complete(first,t++);c.complete(id,t++);
 check(c.warm_read_accepts()>=2&&c.compatible_read_dependencies_omitted()>=1);
 {
  CacheHistoryV8 failed(iris_geometry_v8(),true);failed.begin_read({1,0,a,8,false,0});failed.complete(1,1,false);check(!failed.data_hit(0,a,8));
 }
 // OFF remains all-field V6 parity, including typed ordinary reads and pending owners.
 CacheHistoryV6 before(iris_geometry_v6());CacheHistoryV8 after(iris_geometry_v8(),false);uint64_t rng=0x5587,tick=0;
 for(uint64_t owner=1;owner<=40000;++owner){rng=rng*6364136223846793005ull+1;unsigned h=(rng>>24)%3;uint64_t address=a+((rng>>16)%1024)*64;bool wr=(rng>>7)&1;Access x{owner,h,address,8,wr,tick++};Delta x0=before.begin(x),x1=wr?after.begin(x):after.begin_read(x);check(fields(x0)==fields(x1));check(before.data_hit(h,address,8)==after.data_hit(h,address,8));before.complete(owner,tick);after.complete(owner,tick++);}
 // Read-only values have no publication callback here; the test proves only
 // ownership/dependency mechanics. Native tests must prove RAM/knownness separately.
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"guard_refusals\":"<<rejections<<",\"off_legacy_requests\":40000}\n";
}
