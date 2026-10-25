#include "posted.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
int main(){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({1024,1024,20000});std::vector<std::string>unknown;
 spike_timing::Services services{engine,[](const auto&)->std::optional<double>{return {};},[](const auto&){return 0;},[](auto){return 0;},
   [](const auto&){return spike_timing::SharedEffects{{},{},{},Cycle{0}};},[](const auto&,auto){},[&](auto r){unknown.push_back(r);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;
 c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver posted(services,q,h,c,0);Parameters p;
 for(const auto*k:{"config","preload","compute_ws","fence"})for(const auto*f:{"latency_cycles","occupancy_cycles","latency_per_byte_cycles","occupancy_per_byte_cycles","latency_per_mac_cycles","occupancy_per_mac_cycles"})p[std::string(k)+"."+f]=0;
 p["config.latency_cycles"]=p["config.occupancy_cycles"]=1;p["preload.latency_cycles"]=12;p["preload.occupancy_cycles"]=16;
 p["compute_ws.latency_cycles"]=40;p["compute_ws.latency_per_mac_cycles"]=1./256;p["compute_ws.occupancy_cycles"]=1;p["compute_ws.occupancy_per_mac_cycles"]=1./256;
 TargetObserver observer(engine,h,p,{},0,{},[&](const auto&k,const auto&e,auto o,auto f,auto r1,auto r2,const auto&phase){return posted.submit(k,e,o,f,r1,r2,phase,{});});
 auto pack=[](std::uint64_t a,unsigned r,unsigned n){return a|(std::uint64_t(r)<<48)|(std::uint64_t(n)<<32);};
 std::vector<Cycle>feed,output_start,output_ready;
 engine.trace_sink([&](const merlin_timing::Trace&t){
   if(!t.result.start||!t.result.ready)return;
   bool exec=false,acc=false;for(std::size_t i=0;i<t.event.demands.size;++i){exec|=t.event.demands[i].resource==10;acc|=t.event.demands[i].resource==16;}
   if(exec&&t.event.reads.size&&t.event.reads[0]<8192)feed.push_back(*t.result.start);
   if(acc&&t.event.writes.size&&t.event.writes[0]==16384){output_start.push_back(*t.result.start);output_ready.push_back(*t.result.ready);}
 });
 observer.observe_command(4,0,4|(std::uint64_t(1)<<16),std::uint64_t(1)<<48,0);
 observer.observe_command(8,6,pack(8192,16,16),pack(0x80000000u,16,16),0);
 observer.observe_command(12,4,pack(0,16,16),pack(0xffffffffu,16,16),0);
 observer.observe_command(16,6,pack(8208,16,16),pack(0xc0000000u,16,16),0);
 observer.observe_command(20,4,pack(16,16,16),pack(0xffffffffu,16,16),0);
 posted.drain(0);assert(unknown.empty()&&posted.complete());assert(feed.size()==2&&output_start.size()==2);
 assert(feed[1]<output_ready[0]); // real source overlap: input feed before old ACC completion
 assert(output_start[1]>=output_ready[0]); // exact old generation/WAW preserved at late write
 assert(engine.ready(16384)==output_ready[1]);
 std::cout<<"same-output WS: RS/feed may advance; old ACC RMW/WAW and final row publication remain late PASS\n";
}
