#include "empirical_cache_v8.hpp"
#include <deque>
#include <iostream>
#include <stdexcept>
int main(){
 using namespace iris::empirical;CacheHistoryV8 cache(iris_geometry_v8(),true);
 uint64_t id=0,t=0;unsigned checks=0,refusals=0;constexpr uint64_t a=0x84000000;
 auto check=[&](bool x){++checks;if(!x)throw std::runtime_error("response-owned read sharing witness failed");};
 auto reject=[&](auto f){++refusals;try{f();}catch(const std::exception&){return;}throw std::runtime_error("expected response guard refusal");};
 for(unsigned h=1;h<3;++h){auto d=cache.begin_read({++id,h,a,8,false,t});check(d.l1_misses==1);cache.complete(id,++t);}
 const auto coldid=++id;auto d=cache.begin_read({coldid,0,a,8,false,t});check(d.l1_misses==1);check(!cache.data_hit(0,a,8));
 check(cache.data_hit(1,a,8));check(cache.data_hit(2,a,8));
 const auto r1=++id;d=cache.begin_read({r1,1,a,8,false,t});check(d.l1_hits==1&&d.wait_for.empty());
 const auto r2=++id;d=cache.begin_read({r2,2,a,8,false,t});check(d.l1_hits==1&&d.wait_for.empty());
 cache.complete(r2,++t);cache.complete(r1,++t);check(!cache.data_hit(0,a,8));
 const auto writer=++id;d=cache.begin({writer,2,a,8,true,t});check(d.wait_for==std::vector<uint64_t>{coldid});
 check(!cache.data_hit(0,a,8)&&!cache.data_hit(1,a,8)&&!cache.data_hit(2,a,8));reject([&]{cache.complete(writer,t);});
 cache.complete(coldid,++t);check(!cache.data_hit(0,a,8));cache.complete(writer,++t);check(cache.data_hit(2,a,8));
 const auto failed=++id;d=cache.begin_read({failed,0,a,8,false,t});check(d.l1_misses==1&&d.dirty_owner_forwards==1);cache.complete(failed,++t,false);check(!cache.data_hit(0,a,8));
 d=cache.begin_read({++id,0,a,8,false,t});check(d.l1_misses==1);cache.complete(id,++t);check(cache.data_hit(0,a,8));
 // Unknown read intent (LR/AMO or an unspecified caller) remains ordered.
 const auto unknown=++id;cache.begin({unknown,2,a,8,false,t});check(!cache.data_hit(0,a,8));
 const auto dependent=++id;d=cache.begin_read({dependent,0,a,8,false,t});check(d.wait_for==std::vector<uint64_t>{unknown});
 cache.complete(unknown,++t);cache.complete(dependent,++t);
 // Physical source geometry: three same-index lines evict a two-way L1.
 CacheHistoryV8 generation(iris_geometry_v8(),true);uint64_t owner=0,tick=0;
 const auto old=++owner;generation.begin_read({old,0,a,8,false,tick});
 const auto b=++owner;generation.begin_read({b,0,a+4096,8,false,tick});
 const auto c=++owner;generation.begin_read({c,0,a+8192,8,false,tick});
 const auto fresh=++owner;d=generation.begin_read({fresh,0,a,8,false,tick});check(d.l1_misses==1);check(d.wait_for==std::vector<uint64_t>{old});
 generation.complete(old,++tick);check(!generation.data_hit(0,a,8));generation.complete(fresh,++tick);check(generation.data_hit(0,a,8));
 generation.complete(b,++tick);generation.complete(c,++tick);check(generation.pending()==0);check(cache.pending()==0);
 // Reproduce the old bootstrap stimulus, now with actual independent ready
 // copies and successful responses rather than inherited warm classifications.
 for(unsigned h=0;h<3;++h){cache.begin_read({++id,h,a,8,false,t});cache.complete(id,++t);}
 std::deque<uint64_t> queue;for(unsigned h=0;h<3;++h){cache.begin_read({++id,h,a,8,false,t});queue.push_back(id);}
 const auto omitted=cache.compatible_read_dependencies_omitted();
 for(unsigned i=0;i<1000;++i){cache.complete(queue.front(),++t);queue.pop_front();const unsigned h=i%3;check(cache.data_hit(h,a,8));d=cache.begin_read({++id,h,a,8,false,t});check(d.wait_for.empty()&&d.l1_hits==1);queue.push_back(id);}
 check(cache.compatible_read_dependencies_omitted()>=omitted+2000);
 while(!queue.empty()){cache.complete(queue.front(),++t);queue.pop_front();}check(cache.pending()==0);
 std::cout<<"{\"schema\":\"iris.read_overlap_response_independent_probe.v1\",\"pass\":true,\"checks\":"<<checks<<",\"refusals\":"<<refusals<<",\"compatible_successors\":1000,\"actual_hardware_policy_proved\":false}"<<std::endl;
}
