#include "memory.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace spike_timing;
using namespace merlin_timing;
template<class T> View<T> v(const std::vector<T>& x) {return {x.data(),x.size()};}
int main(int argc, char**argv) {
  assert(argc==2);
  Model model(argv[1]); Engine engine(model.max_values,model.resources);
  ValueId next=0; std::map<std::string,std::uint64_t> counts; unsigned unknown=0;
  MemorySystem memory(model,engine,[&](std::size_t n){auto id=next;next+=n;assert(next<=model.max_values);return id;},
    [&](const std::string&k,std::uint64_t n){counts[k]+=n;},[&](const std::string&){++unknown;});
  auto schedule=[&](const std::vector<MemoryEffect>&effects){
    auto x=memory.access(effects,"cpu_data");
    return engine.submit({0,v(x.reads),v(x.writes),v(x.demands),x.latency,true});
  };
  auto first=schedule({{0x1000,64,false}});
  assert(counts["modeled.cache.l1.misses"]==4);
  auto second=schedule({{0x1000,64,false}});
  assert(first.ready && second.ready && *second.ready>=*first.ready);
  assert(counts["modeled.cache.l1.hits"]==4);
  // AMO-like effects must dirty a line even when a read already visited it.
  schedule({{0x1000,8,false},{0x1000,8,true}});
  schedule({{0x1100,8,false}});
  assert(counts["modeled.writeback_bytes"]==16);
  const auto before_conflicts=counts["modeled.cache.l1.misses"];
  schedule({{0x2000,8,false},{0x2100,8,false},{0x2000,8,false}});
  assert(counts["modeled.cache.l1.misses"]==before_conflicts+3);
  // Overlapping rows may not create duplicate hazard vectors.
  std::vector<MemoryEffect> repeated(1000,{0x1200,16,false});
  auto effects=memory.access(repeated,"cpu_data");
  assert(effects.reads.size()+effects.writes.size()<10);
  assert(unknown==0 && engine.report().complete);
  std::cout<<"memory regressions passed\n";
}
