#include "posted.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
struct ResultRows{Cycle completion,first;unsigned written,pairings;};
ResultRows run(unsigned rows,bool selected,bool garbage=false,bool pair=false,bool pipeline=false,bool real_pair=false){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<19;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({4096,8192,100000});std::vector<std::string>unknown;
 std::map<std::string,double>facts={{"target.scheduling.source_banked_accumulator_bounds",1},{"target.hardware.accumulator_bank_count",2},{"target.hardware.accumulator_bank_rows",512},{"target.hardware.accumulator_localaddr_contiguous_banks",1},{"target.scheduling.source_accumulator_row_ports",1},{"target.hardware.accumulator_two_port_storage",1},{"target.scheduling.source_ws_first_row_bypass",1},{"target.hardware.execute_waiting_state_can_fire_first_row",1},{"target.hardware.execute_last_row_pops_in_compute",1}};
 if(selected){facts["target.scheduling.source_ws_garbage_preload_total_rows"]=1;facts["target.hardware.execute_ws_garbage_preload_uses_actual_total_rows"]=1;facts["target.scheduling.source_ws_total_rows_completion"]=1;facts["target.hardware.execute_ws_minimum_total_rows"]=4;facts["target.hardware.mesh_last_uses_actual_total_rows"]=1;facts["target.hardware.execute_completion_at_mesh_last_response"]=1;}
 if(pipeline){facts["target.scheduling.source_ws_operand_pipeline"]=1;for(const auto&f:std::vector<std::pair<std::string,double>>{{"execute_control_queue_entries",5},{"execute_sp_response_queue_entries",4},{"execute_sram_response_queue_entries",1},{"execute_mesh_tag_queue_entries",6},{"execute_mesh_matmul_ids",5},{"execute_mesh_tile_latency",0},{"execute_mesh_output_delay",1},{"execute_mesh_shifter_banks",1}})facts["target.hardware."+f.first]=f.second;}
 unsigned pairings=0;
 spike_timing::Services services{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);if(i==facts.end())return {};return i->second;},[](const auto&k){return k=="accelerator.storage.accumulator.bank.0"?17:18;},[](auto){return 0;},[](const auto&){return spike_timing::SharedEffects{{},{},{},Cycle{1}};},[&](const auto&k,auto n){if(k=="target.posted.mul_pre")pairings+=n;},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(services,q,h,c,0);std::optional<Cycle>first;unsigned written=0;
 engine.trace_sink([&](const merlin_timing::Trace&t){if(pipeline&&std::string(t.action)=="submit_detached"){assert(t.event.origin&&t.event.origin->pc>=4&&t.event.origin->pc<=20&&t.event.origin->pc%4==0);}if(std::string(t.action)=="submit_detached"&&t.event.origin&&(t.event.origin->actor=="compute.acc_result_row"||t.event.origin->actor=="nextcompute.acc_result_row")){if(!first)first=t.result.ready;++written;}});
 target.submit("config",Event{0,{},{},{},Cycle{1}},Cycle{1},0,4|(std::uint64_t(1)<<16),std::uint64_t(1)<<48,{},{},merlin_timing::StageOrigin{4,0,{},"config"});
 const auto pack=[](std::uint64_t addr,unsigned n){return addr|(std::uint64_t(n)<<48)|(std::uint64_t(16)<<32);};ValueId descriptor=17413;
 target.submit("preload",Event{0,{},{&descriptor,1},{},Cycle{12}},Cycle{16},6,pack(garbage?0xffffffff:8192,16),pack(0x80000000,rows),{},{},merlin_timing::StageOrigin{8,0,{},"weights"});
 std::vector<ValueId>inputs,outputs;for(unsigned i=0;i<rows;++i){inputs.push_back(i);outputs.push_back(16384+i);}
 target.submit("compute_ws",Event{0,{inputs.data(),inputs.size()},{outputs.data(),outputs.size()},{},Cycle{56}},Cycle{17},4,pack(0,rows),pack(0xffffffff,1),{},{},merlin_timing::StageOrigin{12,0,{},"compute"});
 if(pair){
   target.submit("preload",Event{0,{},{&descriptor,1},{},Cycle{12}},Cycle{16},6,pack(real_pair?16u:0xffffffffu,16),pack(0x80000020,rows),{},{},merlin_timing::StageOrigin{16,0,{},"reuse"});
   std::vector<ValueId>next;for(unsigned i=0;i<rows;++i)next.push_back(16384+32+i);
   target.submit("compute_ws",Event{0,{inputs.data(),inputs.size()},{next.data(),next.size()},{},Cycle{56}},Cycle{17},5,pack(0,rows),pack(0xffffffff,1),{},{},merlin_timing::StageOrigin{20,0,{},"nextcompute"});
 }
 target.drain(0);
 if(!unknown.empty())for(const auto&x:unknown)std::cerr<<x<<"\n";
 assert(unknown.empty()&&target.complete()&&first&&written==rows*(pair?2:1));for(auto row:outputs)assert(engine.ready(row)&&*engine.ready(row)<=q.now());return {q.now(),*first,written,pairings};
}
int main(){for(unsigned rows:{1,2,3,4,5,15,16}){auto old=run(rows,false),actual=run(rows,true);assert(actual.first==old.first&&actual.written==old.written);assert(old.completion-actual.completion==16-std::max(rows,4u));}for(unsigned rows:{1,4,16}){auto old=run(rows,false,true),actual=run(rows,true,true);assert(old.first-actual.first==12&&old.completion-actual.completion==12+16-std::max(rows,4u));}
 for(unsigned rows:{1,4,16}){auto old=run(rows,false,false,true),actual=run(rows,true,false,true);assert(old.pairings==1&&actual.pairings==1&&old.first==actual.first&&old.completion-actual.completion==2*(16-std::max(rows,4u)));}
 std::cout<<"WS last-response completion follows actual total_rows with floor4; row publication unchanged PASS\n";return 0;}
