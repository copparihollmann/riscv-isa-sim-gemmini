#include "posted_memory.hpp"
#include <cassert>
#include <map>
#include <iostream>
using namespace spike_timing;
int main(int argc,char**argv){
 assert(argc==2);Model model(argv[1]);merlin_timing::Engine engine(model.max_values,model.resources);
 merlin_timing::ValueId next=0;std::map<std::string,std::uint64_t>features;std::vector<std::string>unknown;
 MemorySystem memory(model,engine,[&](std::size_t n){auto out=next;next+=n;return out;},[&](auto k,auto n){features[k]+=n;},[&](auto s){unknown.push_back(s);});
 merlin_timing::PostedTimeline queue({32,16,128});auto device=queue.token(),cpu=queue.token();assert(device&&cpu);
 // Future DMA posted first, but source acceptance happens after actual CPU
 // write completion. Classifying it now would miss that private dirty copy.
 assert(PostedAggregateMemory::post_accepted(queue,memory,engine,{{0x81000000,16,false}},"device",100,{},*device));
 assert(queue.advance(4,true));assert(features["device.requested_read_bytes"]==0&&engine.report().events==0);
 assert(PostedAggregateMemory::post_accepted(queue,memory,engine,{{0x81000000,16,true}},"cpu_data",4,{},*cpu));
 assert(queue.advance(90,true));assert(queue.completed(*cpu)&&features["device.requested_read_bytes"]==0);assert(features["modeled.coherence_probes"]==0);
 assert(queue.advance(1000,true));assert(unknown.empty()&&queue.progress().complete&&queue.completed(*device));
 assert(features["device.requested_read_bytes"]==16&&features["modeled.coherence_writeback_bytes"]==64);
 auto summary=queue.summary();assert(summary.classes[std::size_t(merlin_timing::PostedTimeline::Kind::memory_accept)].dispatched==2&&summary.unresolved_tokens==0);
 std::cout<<"Native actual MemorySystem classification deferred to accepted arrival; intervening dirty CPU line observed; pending completion and compact causal diagnostics PASS\n";
}
