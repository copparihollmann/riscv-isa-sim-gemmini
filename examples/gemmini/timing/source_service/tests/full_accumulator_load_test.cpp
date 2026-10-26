#include "posted.hpp"
#include <cassert>
#include <map>
using namespace gemmini_annotated_spike;

// The normal ISA decoder must produce byte-based ACC packets, rather than
// reinterpreting sixteen INT32 elements as sixteen scratchpad bytes.
void decoded(unsigned columns,unsigned align,bool enabled=true,bool accumulate=false,bool shrunk=false,bool repeated=false){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<19;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};
 h.source_full_accumulator_load=enabled;
 Parameters prices;for(auto kind:{"config","load"}){prices[std::string(kind)+".latency_cycles"]=1;prices[std::string(kind)+".occupancy_cycles"]=1;}
 std::optional<TransferPhase> observed;
 TargetObserver decoder(engine,h,prices,{},0,[](View<Transfer>){return TransferEffects{{},{},{},Cycle{0}};},
  [&](const auto&kind,const Event&,auto,auto,auto,auto,const auto&phase){if(kind=="load")observed=phase;return Result{0,0,0};});
 const auto config=(0x3f800000ull<<32)|(16ull<<16)|(1ull<<8)|(std::uint64_t(shrunk)<<2)|1;
 decoder.observe_command(0,0,config,repeated?0:columns*4+16);
 const auto local=0x80000000u|(std::uint32_t(accumulate)<<30);
 decoder.observe_command(4,2,0x81000000+align,(3ull<<48)|(std::uint64_t(columns)<<32)|local);
 if(!enabled||accumulate||shrunk){assert(!observed||!observed->full_accumulator_load);return;}
 assert(observed&&observed->full_accumulator_load&&!observed->scratchpad_load&&observed->reader_destinations.size()==3);
 assert(observed->full_accumulator_repeats==(repeated?2u:0u));
 assert(decoder.counters().requested_read_bytes==columns*4*(repeated?1:3));
 std::map<std::size_t,std::uint64_t>masks;std::map<std::size_t,unsigned>finals;
 for(const auto&p:observed->reader_packets)for(const auto&f:p.outputs){
  assert(f.destination==p.row&&f.required_beat<p.bytes/16&&f.bytes<=64);
  assert(!(masks[f.destination]&f.mask));masks[f.destination]|=f.mask;finals[f.destination]+=f.destination_complete;
 }
 const auto expected=columns==16?~std::uint64_t{0}:(1ull<<(columns*4))-1;
 for(unsigned row=0;row<(repeated?1u:3u);++row)assert(masks[row]==expected&&finals[row]==1);
}

void consumed(bool enabled,bool pressure=false,bool missing=false,bool repeated=false,bool ports=false){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<19;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({65536,65536,1000000});
 std::map<std::string,double>facts={
 {"target.scheduling.source_reader_registered_path",1},{"parameters.memory.l2.hit_cycles",1},
 {"target.hardware.reader_tracker_entries",16},{"target.hardware.reader_tracker_first_free",1},
 {"target.hardware.reader_translation_queue_stages",2},{"target.hardware.reader_translation_queue_entries",1},{"target.hardware.reader_translation_queue_pipe",1},{"target.hardware.reader_translation_queue_flow",0},
 {"target.hardware.reader_tl_buffer_stages",3},{"target.hardware.reader_tl_buffer_entries",2},{"target.hardware.reader_tl_buffer_pipe",0},{"target.hardware.reader_tl_buffer_flow",0},
 {"target.hardware.inclusive_hit_directory_stages",1},{"target.hardware.inclusive_hit_plan_stages",1},{"target.hardware.inclusive_hit_source_d_stages",2},
 {"target.scheduling.source_reader_memory_owned_cache_pipeline",1},{"memory.device_read_pipeline.enabled",1},{"memory.device_read_pipeline.directory_stages",1},{"memory.device_read_pipeline.mshr_plan_stages",1},{"memory.device_read_pipeline.source_d_stages",2},{"memory.device_read_pipeline.scalar_lookup_cycles",1},
 {"target.hardware.full_acc_load_separate_scaler",1},{"target.hardware.full_acc_load_scale_args_present",0},
 {"target.hardware.full_acc_load_input_queue_entries",2},{"target.hardware.full_acc_load_input_register_entries",1},
 {"target.hardware.full_acc_load_scale_pipeline_stages",0},{"target.hardware.accumulator_two_port_storage",1}};
 if(ports){facts["target.scheduling.source_accumulator_row_ports"]=1;facts["target.scheduling.source_banked_accumulator_bounds"]=1;facts["target.hardware.accumulator_bank_count"]=2;facts["target.hardware.accumulator_bank_rows"]=512;facts["target.hardware.accumulator_localaddr_contiguous_banks"]=1;}
 if(enabled)facts["target.scheduling.source_full_accumulator_load"]=1;
 if(missing)facts.erase("target.hardware.full_acc_load_separate_scaler");
 std::vector<std::string>unknown;unsigned fragments=0,gets=0;std::vector<Cycle>publications;
 spike_timing::Services s{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&k){return k=="accelerator.storage.accumulator.bank.0"?17:k=="accelerator.storage.accumulator.bank.1"?18:0;},[](auto){return 0;},
 [&](const auto&effects){assert(effects.size()==1&&!effects[0].write&&effects[0].bytes==64);++gets;return spike_timing::SharedEffects{{},{},{},Cycle{4}};},
 [&](const auto&k,auto n){if(k=="target.posted.full_accumulator_load_fragments")fragments+=n;},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;h.source_full_accumulator_load=enabled;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;
 PostedSourceObserver target(s,q,h,c,0);
 Demand busy{16,1,Cycle{100}};if(pressure)assert(engine.submit_detached(Event{0,{},{},{&busy,1},Cycle{1}}).start==0);
 engine.trace_sink([&](const merlin_timing::Trace&r){if(r.event.origin&&r.event.origin->actor=="target.load.acc_load_write"&&std::string(r.action)=="submit_detached")publications.push_back(*r.result.ready);});
 std::vector<ValueId>writes;for(unsigned row=0;row<16;++row)writes.push_back(16384+row);
 TransferPhase phase{};phase.full_accumulator_load=true;phase.full_accumulator_repeats=repeated?15:0;phase.reader_packets=reader_packets(0x81000000,repeated?1:16,64,64,16,64,64,64);phase.reader_destinations=writes;
 target.submit("load",Event{0,{},{writes.data(),writes.size()},{},Cycle{1}},Cycle{1},2,0,0x80000000,phase,{{0x81000000,repeated?1u:16u,64,repeated?0u:64u,false}},merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"target.load"});
 target.drain(0);
 if(!enabled){assert(!target.complete()&&!unknown.empty()&&!fragments);return;}
 assert(target.complete()&&unknown.empty()&&fragments==16&&publications.size()==16);
 assert(publications.front()>=2&&publications.front()<publications.back());
 for(unsigned row=0;row<16;++row)assert(engine.ready(writes[row])==publications[repeated?15-row:row]);
 assert(gets==(repeated?1u:16u));
 if(repeated)for(unsigned row=1;row<16;++row)assert(publications[row]==publications[row-1]+1);
 if(pressure){assert(publications.front()>=102);assert(publications[1]==publications[0]+1);}
 assert(target.coverage().peak_reader<=16);
}
int main(){auto full=reader_packets(0x81000000,1,64,64,16,64,64,64);
 assert(full.size()==1&&full[0].outputs.size()==1&&full[0].outputs[0].required_beat==3&&full[0].outputs[0].mask==~std::uint64_t{0});
 auto sp=reader_packets(0x81000000,1,64,64,16,64,64);
 assert(sp.size()==1&&sp[0].outputs.size()==4&&sp[0].outputs[0].required_beat==0);
 for(auto columns:{1u,9u,16u})for(unsigned align=0;align<64;align+=4){decoded(columns,align);decoded(columns,align,true,false,false,true);}
 decoded(16,0,false);decoded(16,0,true,true);decoded(16,0,true,false,true);
 consumed(true);consumed(true,true);consumed(false);
 consumed(true,false,false,true);consumed(true,true,false,true);consumed(true,false,false,false,true);consumed(true,false,false,true,true);
 bool refused=false;try{consumed(true,false,true);}catch(const std::invalid_argument&){refused=true;}assert(refused);
}
