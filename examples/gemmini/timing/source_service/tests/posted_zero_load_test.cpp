#include "posted.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
int main(){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({4096,8192,100000});std::vector<std::string>unknown;
 spike_timing::Services services{engine,[](const std::string&key)->std::optional<double>{if(key=="target.hardware.zero_writer_request_register_entries"||key=="target.hardware.zero_writer_pixel_register_entries")return 1;if(key=="target.hardware.zero_writer_max_columns")return 64;return {};},[](const auto&){return 0;},[](auto){return 0;},
   [](const auto&){assert(false);return spike_timing::SharedEffects{{},{},{},Cycle{100}};},[](const auto&,auto){},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;h.source_zero_writer=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;
 c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(services,q,h,c,0);std::optional<Cycle>preload_start,last_weight;
 engine.trace_sink([&](const merlin_timing::Trace&t){
   if(std::string(t.action)!="submit_detached"||!t.event.origin)return;
   if(t.event.origin->actor=="weight_preload.feed")preload_start=t.result.start;
   if(t.event.origin->actor=="weight_load.zero_write"&&t.event.writes.size&&t.event.writes[0]==8207)last_weight=t.result.ready;
 });
 std::vector<ValueId>weights;for(unsigned i=0;i<16;++i)weights.push_back(8192+i);
 TransferPhase phase{};phase.zero_fill=ZeroFillGeometry{16,3,16};phase.reader_destinations=weights;
 target.submit("load",Event{0,{},{weights.data(),weights.size()},{},Cycle{1}},Cycle{1},2,0,0,phase,{},merlin_timing::StageOrigin{4,0,{},"weight_load"});
 target.submit("config",Event{0,{},{},{},Cycle{1}},Cycle{1},0,4|(std::uint64_t(1)<<16),std::uint64_t(1)<<48,{},{});
 const auto pack=[](std::uint64_t address){return address|(std::uint64_t(16)<<48)|(std::uint64_t(16)<<32);};
 // As in the semantic observer, PRELOAD only writes descriptor state here.
 ValueId descriptor=17413;
 target.submit("preload",Event{0,{},{&descriptor,1},{},Cycle{12}},Cycle{16},6,pack(8192),pack(0x80000000),{},{},merlin_timing::StageOrigin{8,0,{},"weight_preload"});
 std::vector<ValueId>inputs,outputs;for(unsigned i=0;i<16;++i){inputs.push_back(i);outputs.push_back(16384+i);}
 target.submit("compute_ws",Event{0,{inputs.data(),inputs.size()},{outputs.data(),outputs.size()},{},Cycle{56}},Cycle{17},4,pack(0),pack(0xffffffff),{},{},merlin_timing::StageOrigin{12,0,{},"compute"});
 target.drain(0);assert(unknown.empty()&&target.complete()&&preload_start&&last_weight);
 assert(*last_weight>=18&&*preload_start>=*last_weight);
 std::cout<<"Zero fill preserves 16 original row requests, no memory request, pending PRELOAD row generations PASS\n";
}
