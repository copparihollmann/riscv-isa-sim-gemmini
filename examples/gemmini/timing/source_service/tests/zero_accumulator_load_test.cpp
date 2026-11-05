#include "posted.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace gemmini_annotated_spike;
static std::uint64_t pack(unsigned a,unsigned r,unsigned c){return a|(std::uint64_t(r)<<48)|(std::uint64_t(c)<<32);}
static Parameters prices(){Parameters p;for(auto k:{"load","config"}){p[std::string(k)+".latency_cycles"]=1;p[std::string(k)+".occupancy_cycles"]=1;}return p;}
void decode(bool enabled,bool accumulate,unsigned pixels,bool shrunk=false){
 std::vector<merlin_timing::ResourceSpec>rs;for(unsigned i=0;i<19;++i)rs.push_back({i,1,128});Engine engine(18000,rs);
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_zero_writer=enabled;
 std::optional<TransferPhase>phase;unsigned memory=0;
 TargetObserver d(engine,h,prices(),{},0,[&](View<Transfer>){++memory;return TransferEffects{{},{},{},Cycle{0}};},[&](const auto&k,const Event&,auto,auto,auto,auto,const auto&p){if(k=="load")phase=p;return Result{0,0,0};});
 d.observe_command(0,0,(0x3f000000ull<<32)|(16ull<<16)|(std::uint64_t(pixels)<<8)|(std::uint64_t(shrunk)<<2)|1,0);
 d.observe_command(4,2,0,pack(0x80000000u|(unsigned(accumulate)<<30),3,19));
 assert(memory==0&&d.counters().requested_read_bytes==0&&d.counters().zero_fill_elements==57);
 assert(bool(phase&&phase->zero_fill)==(enabled&&!accumulate&&!shrunk&&pixels==1));
 if(phase&&phase->zero_fill)assert(phase->reader_destinations.size()==6&&phase->reader_destinations[3]==16400);
}
void composed(unsigned columns,bool ports,bool origin=true){
 std::vector<merlin_timing::ResourceSpec>rs;for(unsigned i=0;i<19;++i)rs.push_back({i,1,128});Engine engine(18000,rs);merlin_timing::PostedTimeline q({65536,65536,1000000});
 std::map<std::string,double>facts={{"target.hardware.zero_writer_request_register_entries",1},{"target.hardware.zero_writer_pixel_register_entries",1},{"target.hardware.zero_writer_max_columns",64}};
 if(ports)for(const auto&kv:std::map<std::string,double>{{"target.scheduling.source_accumulator_row_ports",1},{"target.scheduling.source_banked_accumulator_bounds",1},{"target.hardware.accumulator_bank_count",2},{"target.hardware.accumulator_bank_rows",512},{"target.hardware.accumulator_localaddr_contiguous_banks",1},{"target.hardware.accumulator_two_port_storage",1}})facts.insert(kv);
 std::vector<std::string>unknown;std::map<std::string,double>features;
 spike_timing::Services s{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&k){return k=="accelerator.storage.accumulator.bank.0"?17:18;},[](auto){return 0;},[](const auto&){assert(false);return spike_timing::SharedEffects{{},{},{},Cycle{0}};},[&](const auto&k,auto n){features[k]+=n;},[&](auto r){unknown.push_back(r);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_zero_writer=h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(s,q,h,c,0);
 TargetObserver d(engine,h,prices(),{},0,[](View<Transfer>){assert(false);return TransferEffects{};},[&](const auto&k,const auto&v,auto o,auto f,auto a,auto b,const auto&p){return target.submit(k,v,o,f,a,b,p,{},origin?std::optional<merlin_timing::StageOrigin>{{4,0,{},"target."+k}}:std::nullopt);});
 std::map<ValueId,Cycle>published;engine.trace_sink([&](const merlin_timing::Trace&t){if(std::string(t.action)=="submit_detached"&&t.event.writes.size==1&&t.event.writes[0]>=16384&&t.event.writes[0]<17408){assert(t.result.ready&&t.result.start&&*t.result.ready==*t.result.start+2);assert(published.emplace(t.event.writes[0],*t.result.ready).second);}});
 d.observe_command(0,0,(0x3f800000ull<<32)|(16ull<<16)|(1ull<<8)|1,0);
 d.observe_command(4,2,0,pack(0x80000000u,16,columns));target.drain(0);
 assert(unknown.empty()&&target.complete()&&published.size()==16*((columns+15)/16));
 for(const auto&kv:published)assert(engine.ready(kv.first)==kv.second);
 assert(features["target.posted.zero_row_requests"]==16&&features["target.posted.zero_useful_bytes"]==16*columns*4);
 assert(features["target.posted.zero_accumulator_local_writes"]==published.size());
 assert(features["target.posted.zero_masked_local_writes"]==(columns%16?16:0));
}
int main(){decode(true,false,1);decode(false,false,1);decode(true,true,1);decode(true,false,2);decode(true,false,1,true);for(auto c:{1u,16u,19u,64u})for(bool ports:{false,true})composed(c,ports);composed(19,true,false);std::cout<<"ACC zero overwrite masks/write2/no DMA, finite port ownership and unsupported RMW/shrink/repeats PASS\n";}
