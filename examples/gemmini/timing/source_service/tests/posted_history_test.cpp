#include "posted.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
int main(){
 std::vector<merlin_timing::ResourceSpec> resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({4096,500000,1000000});
 std::vector<std::string> unknown;std::uint64_t accepted=0;
 spike_timing::Services s{engine,[](const auto&)->std::optional<double>{return {};},[](const auto&){return 0;},[](auto){return 0;},
   [](const auto&){return spike_timing::SharedEffects{{},{},{},Cycle{0}};},
   [&](const auto&name,auto n){if(name=="target.posted.accepted")accepted+=n;},[&](auto r){unknown.push_back(r);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(s,q,h,c,0);
 // More than the old TOTAL history guard, but only one live command at a time.
 // No token/cycle is reset or completed by pruning the completed drain history.
 for(unsigned i=0;i<66000;++i){Event event;event.earliest=q.now();event.latency=1;target.submit("config",event,Cycle{1},0,1,0,{},{});target.drain(q.now());assert(target.complete());}
 assert(accepted==66000&&unknown.empty());assert(q.now()>=66000);
 std::cout<<"completed command history is reclaimed without changing live queues, token identity or time PASS\n";
}
