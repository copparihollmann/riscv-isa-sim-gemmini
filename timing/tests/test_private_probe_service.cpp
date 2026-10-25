#include "memory.hpp"
#include <cassert>
#include <map>
#include <string>
using namespace spike_timing;
int main(int argc, char **argv) {
  assert(argc==3);
  if (std::string(argv[2])=="invalid-response") {
    try {
      Model m(argv[1]); merlin_timing::Engine e(m.max_values,m.resources);
      MemorySystem bad(m,e,[](std::size_t){return 0;},[](const auto &,auto){},[](const auto &){});
    } catch (const std::exception &) {return 0;}
    assert(false && "invalid response geometry/policy must refuse");
  }
  Model model(argv[1]);
  const std::string mode=argv[2];
  merlin_timing::Engine engine(model.max_values,model.resources);
  merlin_timing::ValueId next=0;
  std::map<std::string,std::uint64_t> counts;
  unsigned unknown=0;
  MemorySystem memory(model,engine,[&](std::size_t n){auto base=next;next+=n;return base;},
      [&](const std::string &k,std::uint64_t n){counts[k]+=n;},[&](const std::string &){++unknown;});
  assert(memory.access({{0x1000,128,true}},"cpu_data").latency);
  counts.clear();
  const auto dirty=memory.access({{0x1000,128,true},{0x1004,8,true}},"device");
  assert(counts["modeled.coherence_probes"]==2);
  assert(counts["modeled.coherence_writeback_bytes"]==128);
  const auto counter="modeled.cache.l1d.coherence_protocol_cycles";
  if (mode=="legacy") assert(counts[counter]==0);
  else {
    assert(counts[counter]==20); // 2*(lookup2 + enter1 + data2 + beats4 + metadata1)
    assert(!dirty.demands.empty() && dirty.demands.back().occupancy==20);
    if(mode=="unknown") assert(!dirty.latency && unknown);
    else assert(dirty.latency && *dirty.latency>=20 && !unknown);
  }
  if(mode=="response") {
    assert(dirty.latency==24); // second line starts10, first C5 + shared pipeline9
    assert(counts["modeled.cache.l1d.response_first_cycles"]==10);
    assert(counts["modeled.cache.l1d.response_last_cycles"]==16);
    assert(counts["modeled.cache.l1d.response_completion_cycles"]==28);
    assert(counts["modeled.cache.l1d.response_wormhole"]==2);
  }
  // Invalidated lines are not charged twice, and no cache state is reset.
  counts.clear();
  const auto absent=memory.access({{0x1000,128,true}},"device");
  assert(counts[counter]==0 && counts["modeled.coherence_probes"]==0);
  // A clean hit has a one-beat acknowledgement, no data-release pipeline.
  assert(memory.access({{0x1000,64,false}},"cpu_data").latency);
  counts.clear();
  const auto clean=memory.access({{0x1000,64,true}},"device");
  assert(counts["modeled.coherence_writeback_bytes"]==0);
  assert(counts[counter]==(mode=="legacy"?0:4));
  if(mode=="selected")assert(clean.latency && *clean.latency>=4);
  if(mode=="response") {
    assert(clean.latency==11); // clean first C2 + SAME pipeline9
    assert(clean.demands.back().occupancy==4);
    assert(memory.access({{0x2000,64,true}},"cpu_data").latency);
    counts.clear();
    const auto partial=memory.access({{0x2010,16,true}},"device");
    assert(partial.latency==17); // offset16 waits last C8, not first C5
    assert(partial.demands.back().occupancy==10);
    assert(counts["modeled.cache.l1d.response_wormhole"]==0);
    assert(counts["modeled.cache.l1d.response_completion_cycles"]==17);
    // Reads retain the existing policy; do not claim qualified read response.
    assert(memory.access({{0x3000,64,true}},"cpu_data").latency);
    counts.clear();
    const auto read=memory.access({{0x3000,64,false}},"device");
    assert(read.latency==10 && !counts["modeled.cache.l1d.response_completion_cycles"]);
  }
}
