#include "memory.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace spike_timing;
using namespace merlin_timing;
int main(int argc,char**argv){
  assert(argc==3);const std::string mode=argv[2];bool rejected=false;
  try {
    Model m(argv[1]);Engine e(m.max_values,m.resources);ValueId next=0;
    std::map<std::string,std::uint64_t> counts;unsigned unresolved=0;
    MemorySystem memory(m,e,[&](std::size_t n){auto id=next;next+=n;assert(next<=m.max_values);return id;},
        [&](const auto&k,auto n){counts[k]+=n;},[&](const auto&){++unresolved;});
    assert(mode!="reject");
    auto cold=memory.access({{0x80002000,4,false}},"cpu_fetch");
    assert(cold.latency && *cold.latency>2);
    memory.instruction_fence();
    auto refill=memory.access({{0x80002000,4,false}},"cpu_fetch");
    assert(refill.latency==std::optional<Cycle>(mode=="selected"?14:2));
    assert(!refill.reads.empty() && !refill.writes.empty()); // lower slot + filled upper slot
    auto hit=memory.access({{0x80002000,4,false}},"cpu_fetch");assert(hit.latency==1);
    if(mode=="selected"){
      assert(counts["modeled.fetch_refill.applied"]==1);
      assert(counts["modeled.fetch_refill.legacy_lower_miss"]==1);
      assert(counts["modeled.fetch_refill.last_response_cycles"]==11);
      assert(counts["modeled.fetch_refill.lookup_response_cycles"]==14);
    } else assert(!counts.count("modeled.fetch_refill.applied"));
    auto data=memory.access({{0x80002000,4,false}},"cpu_data");assert(data.latency==2);
    assert(unresolved==0);
  }catch(const std::invalid_argument&){rejected=true;}
  assert(rejected==(mode=="reject"));std::cout<<"fetch refill "<<mode<<" passed\n";
}
