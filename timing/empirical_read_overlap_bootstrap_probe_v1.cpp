#include "empirical_cache_v7.hpp"
#include <iostream>
#include <stdexcept>
#include <deque>

int main(){
  using namespace iris::empirical;
  CacheHistoryV7 cache(iris_geometry_v7(),true);
  constexpr uint64_t address=0x84000000;
  unsigned checks=0;uint64_t owner=0,tick=0;
  auto check=[&](bool value){++checks;if(!value)throw std::runtime_error("read overlap bootstrap witness failed");};
  // Two response-ready private copies, one ordinary cold requester.
  for(unsigned h=1;h<3;++h){auto d=cache.begin_read({++owner,h,address,8,false,tick});check(d.l1_misses==1);cache.complete(owner,++tick);}
  auto first=cache.begin_read({++owner,0,address,8,false,tick});check(first.l1_misses==1);
  std::deque<uint64_t> pending{owner};
  auto second=cache.begin_read({++owner,1,address,8,false,tick});check(second.l1_hits==1&&second.wait_for.size()==1);pending.push_back(owner);
  auto third=cache.begin_read({++owner,2,address,8,false,tick});check(third.l1_hits==1&&third.wait_for.size()==2);pending.push_back(owner);
  const auto prior=cache.warm_read_accepts();
  // Let each real older response complete, then submit its next ordinary read.
  // No synthetic tag/state mutation or fake ready override is used.
  for(unsigned i=0;i<1000;++i){
    cache.complete(pending.front(),++tick);pending.pop_front();
    const unsigned hart=i%3;check(!cache.data_hit(hart,address,8));
    auto d=cache.begin_read({++owner,hart,address,8,false,tick});
    check(d.l1_hits==1&&d.l1_misses==0&&d.l2_misses==0&&d.wait_for.size()==2);pending.push_back(owner);
  }
  check(cache.warm_read_accepts()==prior);check(cache.compatible_read_dependencies_omitted()==0);
  while(!pending.empty()){cache.complete(pending.front(),++tick);pending.pop_front();}
  // The flag works after draining the false-owner chain.
  auto a=cache.begin_read({++owner,0,address,8,false,tick});auto aid=owner;
  auto b=cache.begin_read({++owner,1,address,8,false,tick});auto bid=owner;
  check(a.l1_hits==1&&a.wait_for.empty());check(b.l1_hits==1&&b.wait_for.empty());
  check(cache.warm_read_accepts()==prior+2);check(cache.compatible_read_dependencies_omitted()==1);
  cache.complete(bid,++tick);cache.complete(aid,++tick);check(cache.pending()==0);
  std::cout<<"{\"schema\":\"iris.empirical_read_overlap_bootstrap_behavior.v1\",\"pass\":true,\"checks\":"<<checks
    <<",\"all_hit_successors_kept_nonwarm\":1000,\"compatible_owners_accepted_after_drain\":2,\"physical_hardware_policy_proved\":false}"<<std::endl;
}
