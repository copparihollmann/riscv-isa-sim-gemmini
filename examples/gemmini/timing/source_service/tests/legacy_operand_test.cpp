#include "staged.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
struct Observation {Cycle ready,a,d,acc,busy; bool known;};
Observation run(bool bounded,unsigned m,unsigned k,unsigned n,bool accumulating=false,bool same_bank=false,unsigned stride=1,bool late=false,bool descriptor=false,unsigned second=0,bool ownership=false) {
 std::vector<merlin_timing::ResourceSpec> resources;
 for(unsigned i=0;i<17;++i)resources.push_back({i,1,4096});
 Engine e(18000,resources);
 StagedConfig c{};c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};
 c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;
 if(late)c.late_accumulator_write_pipeline=2;
 c.bounded_ws_descriptor_consumption=descriptor;c.ws_preload_operand_ownership=ownership;
 c.require_fenced_phases=true;c.conservative_local_store_holds=true;c.serialized_execute_epochs=true;
 c.serialized_output_stationary_epochs=true;c.split_ws_feed_lifetimes=true;c.split_ws_accumulate_operands=true;
 c.ws_feed_queue_release=true;c.bounded_ws_operand_release=bounded;c.scratchpad_bank_rows=4096;
 c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;
 StagedObserver staged(e,c,16384+1024+4,{},0,16384,16,1024);
 Parameters p;
 for(const auto *kind:{"config","preload","compute_ws","fence"})
  for(const auto *field:{"latency_cycles","occupancy_cycles","latency_per_byte_cycles","occupancy_per_byte_cycles","latency_per_mac_cycles","occupancy_per_mac_cycles"})p[std::string(kind)+"."+field]=0;
 p["config.latency_cycles"]=1;p["config.occupancy_cycles"]=1;
 p["preload.latency_cycles"]=12;p["preload.occupancy_cycles"]=16;
 p["compute_ws.latency_cycles"]=40;p["compute_ws.latency_per_mac_cycles"]=1./256;
 p["compute_ws.occupancy_cycles"]=1;p["compute_ws.occupancy_per_mac_cycles"]=1./256;
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};
 TargetObserver t(e,h,p,{},0,{},[&](const auto&kind,const auto&event,auto busy,auto f,auto r1,auto r2,const auto&phase){return staged.submit(kind,event,busy,f,r1,r2,phase);});
 t.observe_command(4,0,4|(std::uint64_t(stride)<<16),std::uint64_t(1)<<48);
 const auto packet=[](std::uint64_t addr,unsigned rows,unsigned cols){return addr|(std::uint64_t(rows)<<48)|(std::uint64_t(cols)<<32);};
 const unsigned d=same_bank?32:8192;
 t.observe_command(8,6,packet(d,k,n),packet(accumulating?0xc0000000u:0x80000000u,m,n));
 auto done=t.observe_command(12,4,packet(0,m,k),packet(0xffffffffu,m,n));
 if(second) {
  const unsigned out=second==1?0:16;
  t.observe_command(16,6,packet(d,k,n),packet(0xc0000000u+out,m,n));
  done=t.observe_command(20,4,packet(0,m,k),packet(0xffffffffu,m,n));
 }

 return {done.ready.value_or(0),e.last_use(0).value_or(0),e.last_use(d).value_or(0),e.last_use(16384).value_or(0),e.report().resources[16].busy_unit_cycles.value_or(0),bool(done.ready)};
}
int main(){
 for(bool accumulating:{false,true}){
  auto old=run(true,9,16,8,accumulating,false,1,true,true,0,false);
  auto now=run(true,9,16,8,accumulating,false,1,true,true,0,true);
  assert(old.known&&now.known&&old.ready==now.ready&&old.acc==now.acc&&old.a==now.a);
  assert(now.d<old.d); //only PRELOAD-consumed D lifetime, not A/output/result
 }
 for(auto shape:{std::array<unsigned,3>{16,16,16},std::array<unsigned,3>{3,16,16}}){
  auto old=run(true,shape[0],shape[1],shape[2],false,false,1,true,true,0,false);
  auto now=run(true,shape[0],shape[1],shape[2],false,false,1,true,true,0,true);
  assert(old.ready==now.ready&&old.acc==now.acc&&old.a==now.a);
  if(shape[0]==16)assert(old.d==now.d); //existing full-tile pairing unaffected
 }
 for(auto same_bank:{false,true})for(unsigned stride:{1u,2u}){
  if(!same_bank&&stride==1)continue;
  auto old=run(true,9,16,8,false,same_bank,stride,true,true,0,false);
  auto now=run(true,9,16,8,false,same_bank,stride,true,true,0,true);
  assert(old.d==now.d&&old.a==now.a&&old.acc==now.acc&&old.ready==now.ready);
 }
 auto same=run(true,9,16,8,true,false,1,true,true,1,true);
 auto first=run(true,9,16,8,true,false,1,true,true,0,true);
 assert(same.ready>=first.ready+56); //same-row RMW result still required
 std::cout<<"Actual PRELOAD D ownership changes only bounded previous-D read hold; A/result/ACC/RMW, same-bank/stride/full-tile fallbacks preserved\n";
}
