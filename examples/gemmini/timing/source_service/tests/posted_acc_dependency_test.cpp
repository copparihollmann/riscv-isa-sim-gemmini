#include "posted.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
void check(bool banked,bool different_bank,bool row_ports=false,bool first_row=false){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<19;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({1024,1024,20000});std::vector<std::string>unknown;
 std::map<std::string,double>facts;bool alias=false;
 if(banked)facts={{"target.scheduling.source_banked_accumulator_bounds",1},
   {"target.hardware.accumulator_bank_count",2},{"target.hardware.accumulator_bank_rows",512},
   {"target.hardware.accumulator_localaddr_contiguous_banks",1}};
 if(row_ports){facts["target.scheduling.source_accumulator_row_ports"]=1;facts["target.hardware.accumulator_two_port_storage"]=1;}
 if(first_row){facts["target.scheduling.source_ws_first_row_bypass"]=1;
   facts["target.hardware.execute_waiting_state_can_fire_first_row"]=1;facts["target.hardware.execute_last_row_pops_in_compute"]=1;}
 spike_timing::Services services{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},
   [&](const auto&name){if(name=="accelerator.storage.accumulator.bank.0")return 17;if(name=="accelerator.storage.accumulator.bank.1")return alias?17:18;return 0;},[](auto){return 0;},
   [](const auto&){return spike_timing::SharedEffects{{},{},{},Cycle{0}};},[](const auto&,auto){},[&](auto r){unknown.push_back(r);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;
 c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 if(banked&&!row_ports){
   facts["target.hardware.accumulator_bank_rows"]=256;bool refused=false;
   try{PostedSourceObserver invalid(services,q,h,c,0);}catch(const std::invalid_argument&){refused=true;}assert(refused);
   facts["target.hardware.accumulator_bank_rows"]=512;alias=true;refused=false;
   try{PostedSourceObserver invalid(services,q,h,c,0);}catch(const std::invalid_argument&){refused=true;}assert(refused);alias=false;
 }
 PostedSourceObserver posted(services,q,h,c,0);Parameters p;
 for(const auto*k:{"config","preload","compute_ws","fence"})for(const auto*f:{"latency_cycles","occupancy_cycles","latency_per_byte_cycles","occupancy_per_byte_cycles","latency_per_mac_cycles","occupancy_per_mac_cycles"})p[std::string(k)+"."+f]=0;
 p["config.latency_cycles"]=p["config.occupancy_cycles"]=1;p["preload.latency_cycles"]=12;p["preload.occupancy_cycles"]=16;
 p["compute_ws.latency_cycles"]=40;p["compute_ws.latency_per_mac_cycles"]=1./256;p["compute_ws.occupancy_cycles"]=1;p["compute_ws.occupancy_per_mac_cycles"]=1./256;
 TargetObserver observer(engine,h,p,{},0,{},[&](const auto&k,const auto&e,auto o,auto f,auto r1,auto r2,const auto&phase){return posted.submit(k,e,o,f,r1,r2,phase,{});});
 auto pack=[](std::uint64_t a,unsigned r,unsigned n){return a|(std::uint64_t(r)<<48)|(std::uint64_t(n)<<32);};
 std::vector<Cycle>feed,output_start,output_ready;
 engine.trace_sink([&](const merlin_timing::Trace&t){
   if(!t.result.start||!t.result.ready)return;
   bool exec=false,acc=false;for(std::size_t i=0;i<t.event.demands.size;++i){exec|=t.event.demands[i].resource==10;acc|=t.event.demands[i].resource==(banked?17u:16u)||t.event.demands[i].resource==18;}
   if(exec&&t.event.reads.size&&t.event.reads[0]<8192)feed.push_back(*t.result.start);
   if((acc||(row_ports&&t.event.writes.size&&t.event.writes[0]%16==0))&&t.event.writes.size&&t.event.writes[0]>=16384&&t.event.writes[0]<17408){output_start.push_back(*t.result.start);output_ready.push_back(*t.result.ready);}
 });
 observer.observe_command(4,0,4|(std::uint64_t(1)<<16),std::uint64_t(1)<<48,0);
 observer.observe_command(8,6,pack(8192,16,16),pack(0x80000000u,16,16),0);
 observer.observe_command(12,4,pack(0,16,16),pack(0xffffffffu,16,16),0);
 observer.observe_command(16,6,pack(8208,16,16),pack(different_bank?0x80000200u:0xc0000000u,16,16),0);
 observer.observe_command(20,4,pack(16,16,16),pack(0xffffffffu,16,16),0);
 posted.drain(0);assert(unknown.empty()&&posted.complete());assert(feed.size()==2&&output_start.size()==2);
 assert(feed[1]-feed[0]==(first_row?16:17));
 assert(feed[1]<output_ready[0]); // real source overlap: input feed before old ACC completion
 if(!row_ports&&banked&&different_bank)assert(output_start[1]<output_ready[0]); // independent selected memories
 else if(!row_ports||!different_bank)assert(output_start[1]>=output_ready[0]); // same-bank bound AND exact WAW preserved
 assert(engine.ready(different_bank?16896:16384)==output_ready[1]);
}
int main(){check(false,false);check(true,false);check(false,true);check(true,true);check(true,false,true);check(true,true,true);check(true,false,true,true);check(true,true,true,true);
 std::cout<<"ACC bank selection preserves same-row WAW, same-bank occupancy and independent-bank overlap PASS\n";
}
