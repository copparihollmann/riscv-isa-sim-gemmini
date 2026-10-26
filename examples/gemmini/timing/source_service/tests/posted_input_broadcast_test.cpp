#include "posted.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace gemmini_annotated_spike;
std::uint64_t pack(unsigned rows,unsigned cols){return 8192|(std::uint64_t(rows)<<48)|(std::uint64_t(cols)<<32);}
Parameters prices(){Parameters p;for(auto k:{"config","load"})for(auto f:{"latency_cycles","occupancy_cycles","latency_per_byte_cycles","occupancy_per_byte_cycles","latency_per_mac_cycles","occupancy_per_mac_cycles"})p[std::string(k)+"."+f]=(std::string(f)=="latency_cycles"||std::string(f)=="occupancy_cycles")?1:0;return p;}
void check(unsigned rows,unsigned cols,unsigned align,bool pressure=false){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({65536,65536,1000000});std::vector<std::string>unknown;
 unsigned gets=0,emitted=0,writes=0;std::vector<ValueId>order;std::vector<Cycle>times;
 spike_timing::Services services{engine,[](const auto&)->std::optional<double>{return {};},[](const auto&){return 0;},[](auto){return 0;},
  [&](const auto&effects){assert(effects.size()==1&&!effects[0].write);++gets;return spike_timing::SharedEffects{{},{},{},Cycle{4}};},
  [&](const auto&key,auto n){if(key=="target.posted.input_scaler_repeated_row_emissions")emitted+=n;},[&](auto why){unknown.push_back(why);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;h.scratchpad_packet_loads=true;h.wide_scratchpad_row_publication=true;h.selected_mvin_cols_bits=7;h.selected_mvin_rows_bits=5;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(services,q,h,c,0);std::optional<TransferPhase>phase;
 TargetObserver decoder(engine,h,prices(),{},0,[](View<Transfer>){return TransferEffects{{},{},{},Cycle{0}};},[&](const auto&kind,const auto&e,auto occupancy,auto funct,auto rs1,auto rs2,const auto&p){if(kind=="load")phase=p;return target.submit(kind,e,occupancy,funct,rs1,rs2,p,{},merlin_timing::StageOrigin{4,0xabcdef,{},"target."+kind});});
 if(pressure){Demand hold{14,1,Cycle{100}};assert(engine.submit_detached(Event{0,{},{},{&hold,1},Cycle{1}}).start==0);}
 engine.trace_sink([&](const merlin_timing::Trace&t){if(t.event.origin&&t.event.origin->actor=="target.load.sp_write"&&std::string(t.action)=="submit_detached"){++writes;assert(t.event.writes.size==1);order.push_back(t.event.writes[0]);times.push_back(*t.result.ready);}});
 decoder.observe_command(0,0,(0x3f800000ull<<32)|(16ull<<16)|(1ull<<8)|1,0);
 decoder.observe_command(4,2,0x81000000+align,pack(rows,cols));target.drain(0);
 assert(unknown.empty()&&target.complete()&&phase&&phase->scratchpad_load&&phase->input_row_repeats==rows-1);
 assert(decoder.counters().requested_read_bytes==cols&&decoder.counters().local_write_bytes==rows*cols);
 const auto packets=reader_packets(0x81000000+align,1,cols,0,16,64,127);assert(!packets.empty()&&gets==packets.size());
 unsigned fragments=0;for(const auto&p:packets)fragments+=p.outputs.size();
 assert(writes==fragments*rows&&emitted==(rows>1?fragments*rows:0));
 std::map<ValueId,unsigned>counts;for(auto row:order)++counts[row];
 for(unsigned band=0;band<(cols+15)/16;++band)for(unsigned row=0;row<rows;++row)assert(counts[8192+band*16+row]&&engine.ready(8192+band*16+row));
 if(rows>1){for(unsigned r=0;r<rows;++r)assert(order[r]==8192+rows-1-r);for(unsigned r=1;r<rows;++r)assert(times[r]==times[r-1]+1);}
 const auto coverage=target.coverage();assert(coverage.peak_q<=2&&coverage.peak_ring<=3&&coverage.peak_reader<=16);
 if(pressure){assert(times.front()>=101&&coverage.port_blocked>0);}
}
void refused(bool identity,bool pixels,bool enabled,unsigned rows,unsigned cols,std::uint64_t pitch){
 Engine engine(18000,{{0,1,128}});HardwareConfig h{16,16384,1024,1,4,32,true,true,0};h.source_identity_ingress=enabled;h.scratchpad_packet_loads=true;h.wide_scratchpad_row_publication=true;h.selected_mvin_cols_bits=7;h.selected_mvin_rows_bits=5;
 std::optional<TransferPhase>phase;TargetObserver decoder(engine,h,prices(),{},0,[](View<Transfer>){return TransferEffects{{},{},{},Cycle{0}};},[&](const auto&kind,const auto&,auto,auto,auto,auto,const auto&p){if(kind=="load")phase=p;return Result{0,0,0};});
 decoder.observe_command(0,0,((identity?0x3f800000ull:0x3f000000ull)<<32)|(16ull<<16)|(std::uint64_t(pixels?2:1)<<8)|1,pitch);
 decoder.observe_command(4,2,0x81000000,pack(rows,cols));assert(!phase||!phase->scratchpad_load||phase->reader_packets.empty());
}
int main(){
 assert(reader_packets(0x81000000,2,16,0,16,64).empty());
 for(auto rows:{1u,3u,16u})for(auto cols:{1u,3u,16u,32u,127u})for(auto align:{0u,7u,15u})check(rows,cols,align);
 check(16,16,0,true);check(16,32,7,true);
 refused(false,false,true,16,16,0);refused(true,true,true,16,3,0);refused(true,false,false,16,16,0);refused(true,false,true,17,16,0);refused(true,false,true,16,128,0);refused(true,false,true,16,16,1);
 std::cout<<"stride0 one original Get stream; finite input-register/ring3 descending repeats; masked bands/pressure and unsupported guards PASS\n";
}
