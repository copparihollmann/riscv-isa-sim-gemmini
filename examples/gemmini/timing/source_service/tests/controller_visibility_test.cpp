#include "posted.hpp"
#include <cassert>
#include <map>
using namespace gemmini_annotated_spike;
Cycle check(bool enabled,bool missing=false){
 std::vector<merlin_timing::ResourceSpec> resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({4096,4096,100000});
 std::map<std::string,double>facts;
 if(enabled)facts={{"target.scheduling.source_controller_visibility",1},{"target.hardware.source_rs_valid_registered_stages",1},{"target.hardware.source_controller_visibility_stages.load",1},{"target.hardware.source_controller_visibility_stages.execute",2},{"target.hardware.source_controller_visibility_stages.store",1}};
 if(missing)facts.erase("target.hardware.source_controller_visibility_stages.load");
 std::vector<std::string>unknown;std::vector<Cycle>gets;
 spike_timing::Services s{engine,[&](const std::string&name)->std::optional<double>{auto i=facts.find(name);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&){return 0;},[](auto){return 0;},
   [&](const auto&){gets.push_back(q.now());return spike_timing::SharedEffects{{},{},{},Cycle{1}};},[](const auto&,auto){},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={2,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(s,q,h,c,0);
 // Three queued commands exceed physical2-entry LD capacity; pending stage
 // ownership must count without becoming a visible head prematurely.
 for(unsigned i=0;i<3;++i){
  const ValueId row=8192+i;TransferPhase phase{};phase.scratchpad_load=true;phase.reader_packets=reader_packets(0x81000000+i*64,1,16,16,16,64,127);phase.reader_destinations={row};
  target.submit("load",Event{0,{},{&row,1},{},Cycle{40}},Cycle{1},2,0,0,phase,{{0x81000000+i*64,1,16,16,false}});
 }
 target.drain(0);assert(unknown.empty()&&target.complete()&&gets.size()==3);
 return gets.front();
}
int main(){assert(check(false)==2);assert(check(true)==4);bool refused=false;try{check(true,true);}catch(const std::invalid_argument&){refused=true;}assert(refused);}
