#include "staged.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
struct Observation {std::uint64_t pairs;Cycle horizon,sp0,sp2;bool known;};
Observation run(bool enabled,unsigned m=9,bool late=false,bool blocked=false,bool samebank=false,bool sameout=false,bool accinput=false){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,4096});Engine e(18000,resources);
 StagedConfig c{};c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;
 c.late_accumulator_write_pipeline=2;c.bounded_ws_descriptor_consumption=true;c.require_fenced_phases=true;c.conservative_local_store_holds=true;c.serialized_execute_epochs=true;c.serialized_output_stationary_epochs=true;c.split_ws_feed_lifetimes=true;c.split_ws_accumulate_operands=true;c.ws_feed_queue_release=true;c.ws_resident_mul_pre_pairing=true;c.bounded_ws_operand_release=true;c.ws_preload_operand_ownership=true;c.source_bounded_mul_pre_pairing=enabled;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;
 StagedObserver staged(e,c,16384+1024+4,{},0,16384,16,1024);Parameters p;
 for(const auto*k:{"config","preload","compute_ws","fence"})for(const auto*f:{"latency_cycles","occupancy_cycles","latency_per_byte_cycles","occupancy_per_byte_cycles","latency_per_mac_cycles","occupancy_per_mac_cycles"})p[std::string(k)+"."+f]=0;
 p["config.latency_cycles"]=1;p["config.occupancy_cycles"]=1;p["preload.latency_cycles"]=12;p["preload.occupancy_cycles"]=16;p["compute_ws.latency_cycles"]=40;p["compute_ws.latency_per_mac_cycles"]=1./256;p["compute_ws.occupancy_cycles"]=1;p["compute_ws.occupancy_per_mac_cycles"]=1./256;
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};TargetObserver t(e,h,p,{},0,{},[&](const auto&k,const auto&v,auto o,auto f,auto r1,auto r2,const auto&phase){return staged.submit(k,v,o,f,r1,r2,phase);});
 auto pack=[](std::uint64_t a,unsigned r,unsigned n){return a|(std::uint64_t(r)<<48)|(std::uint64_t(n)<<32);};unsigned d=samebank?32:8192;
 if(blocked)for(unsigned r=0;r<16;++r)e.publish(d+16+r,Cycle{120});
 t.observe_command(4,0,4|(std::uint64_t(1)<<16),std::uint64_t(1)<<48,1);
 t.observe_command(8,6,pack(d,16,8),pack(0x80000000u,m,8),2);
 t.observe_command(12,4,pack(0,m,16),pack(0xffffffffu,m,8),3);
 if(late)e.advance_issue(100);
 t.observe_command(16,6,pack(d+16,16,8),pack(0xc0000000u+(sameout?0:16),m,8),late?100:4);
 auto done=t.observe_command(20,4,pack(accinput?0x80000000u:0,m,16),pack(0xffffffffu,m,8),late?101:5);
 t.observe_fence(late?102:6);
 auto r=e.report();return{staged.bounded_pairings(),r.modeled_makespan,e.last_use(0).value_or(0),e.last_use(d+16).value_or(0),r.complete&&bool(done.ready)};
}
int main(){
 for(unsigned m:{3u,9u,16u}){auto old=run(false,m),n=run(true,m);assert(old.known&&n.known);assert(n.pairs==1);assert(n.horizon<old.horizon);assert(n.sp2>0);}
 for(auto n:{run(true,9,true),run(true,9,false,true),run(true,9,false,false,true),run(true,9,false,false,false,true),run(true,9,false,false,false,false,true)})assert(n.pairs==0);
 std::cout<<"actual-arrival bounded 3-command pair: full/tail; late arrival, unready D, same bank/output and ACC-input refusal PASS\n";
}
