#include "posted.hpp"
#include <cassert>
#include <map>
#include <iostream>
using namespace gemmini_annotated_spike;
std::uint64_t pack(std::uint64_t a,unsigned r,unsigned c){return a|(std::uint64_t(r)<<48)|(std::uint64_t(c)<<32);}
Parameters prices(){Parameters p;for(auto k:{"load","config"}){p[std::string(k)+".latency_cycles"]=1;p[std::string(k)+".occupancy_cycles"]=1;}return p;}
void decode(unsigned cols,unsigned offset,bool enabled=true,bool accum=false,bool identity=true,bool shrunk=true,unsigned pixels=1){
 std::vector<merlin_timing::ResourceSpec>rs;for(unsigned i=0;i<17;++i)rs.push_back({i,1,128});Engine e(18000,rs);
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_i8_accumulator_load=enabled;
 std::optional<TransferPhase>phase;TargetObserver d(e,h,prices(),{},0,[](View<Transfer>){return TransferEffects{{},{},{},Cycle{0}};},[&](const auto&k,const Event&,auto,auto,auto,auto,const auto&p){if(k=="load")phase=p;return Result{0,0,0};});
 d.observe_command(0,0,((identity?0x3f800000ull:0x3f000000ull)<<32)|(16ull<<16)|(std::uint64_t(pixels)<<8)|(std::uint64_t(shrunk)<<2)|1,cols+7);
 d.observe_command(4,2,0x81000000+offset,pack(0x80000000u|(std::uint32_t(accum)<<30),3,cols));
 if(!enabled||!identity||!shrunk||pixels!=1){assert(!phase||!phase->identity_i8_accumulator_load);return;}
 assert(phase&&phase->identity_i8_accumulator_load&&!phase->scratchpad_load&&!phase->full_accumulator_load);
 assert(phase->reader_destinations.size()==3&&d.counters().requested_read_bytes==cols*3&&d.counters().local_write_bytes==cols*3*4);
 assert(d.counters().local_read_bytes==(accum?cols*3*4:0));std::map<unsigned,std::uint64_t>mask;
 for(const auto&p:phase->reader_packets)for(const auto&f:p.outputs){assert(f.destination<3&&!(mask[f.destination]&f.mask));mask[f.destination]|=f.mask;assert(f.required_beat<p.bytes/16);}
 for(unsigned row=0;row<3;++row)assert(mask[row]==((1ull<<cols)-1));
}
void composed(bool pressure,bool ports=false){
 std::vector<merlin_timing::ResourceSpec>rs;for(unsigned i=0;i<19;++i)rs.push_back({i,1,128});Engine e(18000,rs);merlin_timing::PostedTimeline q({65536,65536,1000000});
 std::map<std::string,double>facts={{"target.scheduling.source_identity_i8_accumulator_load",1},{"target.hardware.i8_acc_load_identity_scale",1},{"target.hardware.i8_acc_load_signed_extension",1},{"target.hardware.i8_acc_load_mask_byte_expansion",4},{"target.hardware.accumulator_two_port_storage",1}};
 if(ports){facts["target.scheduling.source_accumulator_row_ports"]=1;facts["target.scheduling.source_banked_accumulator_bounds"]=1;facts["target.hardware.accumulator_bank_count"]=2;facts["target.hardware.accumulator_bank_rows"]=512;facts["target.hardware.accumulator_localaddr_contiguous_banks"]=1;}
 std::vector<std::string>unknown;unsigned fragments=0;
 spike_timing::Services s{e,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&k){return k=="accelerator.storage.accumulator.bank.0"?17:k=="accelerator.storage.accumulator.bank.1"?18:0;},[](auto){return 0;},[](const auto&){return spike_timing::SharedEffects{{},{},{},Cycle{4}};},[&](const auto&k,auto n){if(k=="target.posted.identity_i8_accumulator_load_fragments")fragments+=n;},[&](auto x){unknown.push_back(x);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=h.source_identity_i8_accumulator_load=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(s,q,h,c,0);TargetObserver d(e,h,prices(),{},0,[](View<Transfer>){return TransferEffects{{},{},{},Cycle{0}};},[&](const auto&k,const auto&v,auto o,auto f,auto r1,auto r2,const auto&p){return target.submit(k,v,o,f,r1,r2,p,{},merlin_timing::StageOrigin{4,0xabcdef,{},"target."+k});});
 if(pressure){Demand hold{16,1,Cycle{80}};assert(e.submit_detached(Event{0,{},{},{&hold,1},Cycle{1}}).start==0);}
 unsigned writes=0;std::vector<Cycle>published;
 e.trace_sink([&](const merlin_timing::Trace&r){if(r.event.origin&&r.event.origin->actor=="target.load.acc_load_write"&&std::string(r.action)=="submit_detached"){assert(r.result.ready&&r.result.start&&*r.result.ready==*r.result.start+2);++writes;published.push_back(*r.result.ready);}});
 d.observe_command(0,0,(0x3f800000ull<<32)|(16ull<<16)|(1ull<<8)|5,23);
 d.observe_command(4,2,0x81000003,pack(0x80000000u,16,16));target.drain(0);assert(target.complete()&&unknown.empty());auto old=e.ready(16384);assert(old);
 d.observe_command(8,2,0x82000007,pack(0xc0000000u,16,16));target.drain(q.now());assert(target.complete()&&unknown.empty());assert(e.ready(16384)>old);
 // Unaligned packets may split one source row; every original row remains a
 // dependency and publishes only after all its real fragments arrive.
 assert(fragments>=32&&writes==fragments);if(pressure)assert(published.front()>=82);
 assert(target.coverage().peak_q<=2&&target.coverage().peak_ring<=3);
 std::cout<<"identity i8 ACC overwrite/RMW finite shared ingress/write2 PASS\n";
}
int main(){for(unsigned c:{1u,9u,16u})for(unsigned a=0;a<64;++a){decode(c,a);decode(c,a,true,true);}decode(16,0,false);decode(16,0,true,false,false);decode(16,0,true,false,true,false);decode(8,0,true,false,true,true,2);composed(false);composed(true);composed(false,true);}
