#include "posted.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
void check(bool pressure,unsigned columns){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({4096,4096,100000});
 std::vector<std::string>unknown;bool host_updated=false;unsigned post_host_requests=0;
 spike_timing::Services s{engine,[](const auto&)->std::optional<double>{return {};},[](const auto&){return 0;},[](auto){return 0;},
   [&](const auto&){if(host_updated)++post_host_requests;return spike_timing::SharedEffects{{},{},{},Cycle{20}};},
   [](const auto&,auto){},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};
 h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;
 c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(s,q,h,c,0);
 // An existing operand consumer owns this port from zero, not a speculative
 // future booking. Returned rows must backpressure REAL Queue2/ring3/pixel1.
 Demand busy{14,1,Cycle{80}};Event hold{0,{},{},{&busy,1},Cycle{1}};if(pressure)assert(engine.submit_detached(hold).start==0);
 std::set<std::string>actor_roles;
 engine.trace_sink([&](const merlin_timing::Trace&r){if(std::string(r.action)=="submit_detached"){assert(r.event.origin&&r.event.origin->pc==0x80004000&&r.event.origin->bits==0xabcdef);actor_roles.insert(r.event.origin->actor);}});
 assert(q.post(10,{},[&](auto&,auto){host_updated=true;},merlin_timing::PostedTimeline::Kind::source_arrival));
 std::vector<ValueId>writes;for(unsigned band=0;band<(columns+15)/16;++band)for(unsigned row=0;row<16;++row)writes.push_back(8192+band*16+row);
 TransferPhase phase{};phase.scratchpad_load=true;phase.reader_packets=reader_packets(0x81000000,16,columns,columns,16,64,127);phase.reader_destinations=writes;
 Event load{0,{},{writes.data(),writes.size()},{},Cycle{40}};
 target.submit("load",load,Cycle{1},2,0,0,phase,{{0x81000000,16,columns,columns,false}},merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"target.load"});
 target.drain(0);assert(unknown.empty()&&target.complete());assert(post_host_requests>0);
 assert(actor_roles.count("target.load.rs_issue")&&actor_roles.count("target.load.memory_get")&&actor_roles.count("target.load.sp_write"));
 const auto coverage=target.coverage();assert(coverage.peak_q<=2&&coverage.peak_ring<=3&&coverage.peak_reader<=16);
 if(pressure)assert(coverage.port_blocked>0&&coverage.merger_blocked>0);
 if(!pressure&&columns==16)assert(*engine.ready(writes[1])==*engine.ready(writes[0])+1); // no invented inter-packet bubble
 assert(engine.ready(writes.front())<engine.ready(writes.back())); // real row publication survives final completion
 auto before=engine.ready(writes.front());target.drain(q.now());assert(engine.ready(writes.front())==before);
 // Unsupported semantic families do not silently inherit raw WS scheduling.
 target.submit("compute_os",Event{},Cycle{1},4,0,0,{},{});assert(!target.complete()&&!unknown.empty());
}
int main(){check(true,32);check(false,16);check(false,17);check(false,80);
 std::cout<<"posted native source: delayed host arrival, finite ingress under SP pressure, width32 rows and explicit unsupported refusal PASS\n";
}
