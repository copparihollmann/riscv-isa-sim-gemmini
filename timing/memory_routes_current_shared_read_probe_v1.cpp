#include "empirical_cache_v6.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>

int main() {
  using namespace iris::empirical;
  unsigned checks=0;
  auto require=[&](bool result){++checks;if(!result)throw std::runtime_error("shared-read behavior witness failed");};
  CacheHistoryV6 cache(iris_geometry_v6());
  constexpr uint64_t address=0x80010000;
  uint64_t id=0,tick=0;
  for(unsigned hart=0;hart<3;++hart){auto d=cache.begin({++id,hart,address,4,false,tick});require(d.path==Path::DRAM);cache.complete(id,++tick);}
  for(unsigned hart=0;hart<3;++hart)require(cache.data_hit(hart,address,4));
  auto first=cache.begin({++id,0,address,4,false,tick});const auto first_id=id;
  require(first.l1_hits==1&&first.l1_misses==0&&first.wait_for.empty());
  require(!cache.data_hit(1,address,4));require(!cache.data_hit(2,address,4));
  auto second=cache.begin({++id,1,address,4,false,tick});const auto second_id=id;
  require(second.l1_hits==1&&second.l1_misses==0&&second.l2_misses==0);
  require(second.wait_for==std::vector<uint64_t>{first_id});require(second.shared_line_contenders==1);
  auto third=cache.begin({++id,2,address,4,false,tick});const auto third_id=id;
  require(third.l1_hits==1&&third.l1_misses==0&&third.l2_misses==0);
  require(third.wait_for==std::vector<uint64_t>({first_id,second_id}));require(third.shared_line_contenders==2);
  bool rejected=false;try{cache.complete(third_id,tick);}catch(const std::logic_error&){rejected=true;}require(rejected);
  cache.complete(first_id,++tick);cache.complete(second_id,++tick);cache.complete(third_id,++tick);
  for(unsigned hart=0;hart<3;++hart)require(cache.data_hit(hart,address,4));
  auto disjoint=cache.begin({++id,0,address+64,8,false,tick});require(disjoint.wait_for.empty());
  require(cache.data_hit(1,address,4));cache.complete(id,++tick);
  auto writer=cache.begin({++id,0,address,8,true,tick});const auto writer_id=id;
  require(writer.l1_hits==1);require(!cache.data_hit(1,address,4));
  auto reader=cache.begin({++id,1,address,4,false,tick});const auto reader_id=id;
  require(reader.wait_for==std::vector<uint64_t>{writer_id});require(reader.dirty_owner_forwards==1);
  cache.complete(writer_id,++tick);cache.complete(reader_id,++tick);require(cache.pending()==0);
  std::cout<<"{\"schema\":\"iris.empirical_shared_read_behavior.v1\",\"pass\":true,\"checks\":"<<checks
           <<",\"pending_read_blocks_private_L1_read\":true,\"three_L1_read_hits_are_dependency_chained\":true,"
             "\"write_read_dependency_preserved\":true,\"physical_hardware_policy_proved\":false}"<<std::endl;
}
