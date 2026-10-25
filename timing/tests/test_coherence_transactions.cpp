#include "memory.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace spike_timing;
int main(int argc, char **argv) {
  assert(argc == 3);
  Model model(argv[1]);
  const bool separate = std::string(argv[2]) == "separate";
  merlin_timing::Engine engine(model.max_values, model.resources);
  merlin_timing::ValueId next = 0;
  std::map<std::string,std::uint64_t> counts;
  unsigned unknown = 0;
  MemorySystem memory(model,engine,[&](std::size_t n){auto base=next;next+=n;return base;},
    [&](const std::string &key,std::uint64_t n){counts[key]+=n;},
    [&](const std::string &){++unknown;});
  // First fill L2 and dirty the private CPU line. Do not reset cache state.
  assert(memory.access({{0x1000,16,true}},"cpu_data").latency);
  counts.clear();
  const auto first = memory.access({{0x1000,16,true}},"device");
  assert(first.latency && unknown == 0);
  assert(counts["modeled.coherence_writeback_bytes"] == 16);
  assert(counts["modeled.cache.l2.hits"] == (separate ? 2 : 1));
  assert(counts["modeled.cache.l2.boundary_bytes"] == (separate ? 32 : 16));
  // The dirty CPU copy is now invalid. A later device command has one transfer.
  counts.clear();
  const auto second = memory.access({{0x1000,16,true},{0x1004,8,true}},"device");
  assert(second.latency && unknown == 0);
  assert(counts["modeled.coherence_writeback_bytes"] == 0);
  assert(counts["modeled.cache.l2.hits"] == 1);
  assert(counts["modeled.cache.l2.boundary_bytes"] == 16);
  std::cout << "distinct coherence/request traffic " << argv[2] << " passed\n";
}
