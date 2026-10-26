#include "posted.hpp"
#include <cassert>
#include <map>
#include <iostream>
using namespace gemmini_annotated_spike;
void check(bool selected,std::uint64_t stride=64,bool cold=false,bool dirty=false,bool victim=false,bool source_read=false,bool input_retirement=false,bool resident_retirement=false,bool beat_forward=false,bool deferred=false,bool aggregate_probe=false,unsigned parent_phase=0){
 const bool enabled=true,missing=false,probe=true;const unsigned columns=16;
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<26;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);merlin_timing::PostedTimeline q({65536,65536,1000000});
 std::map<std::string,double>facts={
 {"target.scheduling.source_controller_visibility",1},{"target.hardware.source_rs_valid_registered_stages",1},{"target.hardware.source_controller_visibility_stages.load",1},{"target.hardware.source_controller_visibility_stages.execute",2},{"target.hardware.source_controller_visibility_stages.store",1},
 {"target.scheduling.source_reader_registered_path",1},{"parameters.memory.l2.hit_cycles",1},
 {"target.hardware.reader_tracker_entries",16},{"target.hardware.reader_tracker_first_free",1},
 {"target.hardware.reader_translation_queue_stages",2},{"target.hardware.reader_translation_queue_entries",1},{"target.hardware.reader_translation_queue_pipe",1},{"target.hardware.reader_translation_queue_flow",0},
 {"target.hardware.reader_tl_buffer_stages",3},{"target.hardware.reader_tl_buffer_entries",2},{"target.hardware.reader_tl_buffer_pipe",0},{"target.hardware.reader_tl_buffer_flow",0},
 {"target.hardware.inclusive_hit_directory_stages",1},{"target.hardware.inclusive_hit_plan_stages",1},{"target.hardware.inclusive_hit_source_d_stages",2},
 {"target.scheduling.source_reader_memory_owned_cache_pipeline",1},{"memory.device_read_pipeline.enabled",1},{"memory.device_read_pipeline.directory_stages",1},{"memory.device_read_pipeline.mshr_plan_stages",1},{"memory.device_read_pipeline.source_d_stages",2},{"memory.device_read_pipeline.scalar_lookup_cycles",1},
 {"target.hardware.normalizations",0},{"target.hardware.relu_same_accumulator_scale_pipeline",1},{"target.assumptions.accumulator_readout_translation_hits",1}};
 facts["target.scheduling.source_aligned_i8_readout"]=1;
 if(enabled)facts["target.scheduling.source_masked_i8_readout"]=1;
 facts["target.hardware.source_d_client_beat_bytes"]=16;facts["target.hardware.source_d_write_chunk_bytes"]=8;facts["target.hardware.source_d_sram_read_stages"]=2;facts["target.assumptions.source_d_no_external_banked_store_stalls"]=1;
 if(probe){facts["target.scheduling.source_masked_probe_sinkc"]=1;facts["target.hardware.source_d_banked_store_banks"]=8;facts["target.hardware.sinkc_data_queue_stages"]=1;facts["target.hardware.mshr_probe_response_register_stages"]=1;}
 if(selected){facts["target.scheduling.source_full_raw_packet_readout"]=1;facts["target.hardware.source_sink_a_put_lists"]=40;facts["target.hardware.source_sink_a_put_beats"]=40;facts["target.hardware.source_full_raw_scale_pipeline"]=8;}
 if(cold){facts["target.scheduling.source_cold_write_misses"]=1;
   facts["memory.device_write_miss_pipeline.enabled"]=1;facts["memory.device_write_miss_pipeline.line_bytes"]=64;
   facts["memory.device_write_miss_pipeline.outer_beat_bytes"]=8;facts["memory.device_write_miss_pipeline.demand_mshrs"]=10;
   facts["memory.caches.l2.sets"]=1024;facts["memory.caches.l2.ways"]=8;}
 if(victim)facts["memory.device_write_miss_pipeline.private_victim.clients"]=1;
 if(source_read)facts["memory.source_read_allocations.enabled"]=1;
 if(input_retirement){facts["target.scheduling.source_d_read_input_retirement"]=1;
   facts["target.hardware.source_d_s2_entries"]=1;facts["target.hardware.source_d_s3_entries"]=1;
   facts["target.hardware.source_d_read_sram_stages"]=2;facts["target.hardware.source_d_s1_last_input_retires_busy"]=1;}

 if(deferred){facts["target.scheduling.source_deferred_read_lookup"]=1;facts["target.hardware.scheduler_directory_read_at_mshr_allocation"]=1;}
 if(beat_forward){facts["target.scheduling.source_memory_beat_forwarding"]=1;facts["target.hardware.mshr_zero_offset_grant_wormhole"]=1;facts["target.hardware.sinkd_first_last_response"]=1;}
 if(resident_retirement){facts["target.scheduling.source_resident_get_request_retirement"]=1;
   facts["target.hardware.mshr_resident_get_no_wait_at_source_d_request"]=1;}
 if(missing)facts.erase("target.hardware.relu_same_accumulator_scale_pipeline");
 std::vector<std::string>unknown;std::vector<Cycle>puts;std::uint64_t counted=0;unsigned native_gets=0,deferred_lookups=0;std::vector<Cycle>lookup_times;
 std::optional<spike_timing::ReadAllocationEffectsV7>native_read;
 std::optional<Cycle>parent_prefix_at;std::vector<Cycle>resident_releases;std::optional<Cycle>first_get,last_get;
 struct ReadState{unsigned*released;std::optional<spike_timing::ReadAllocationEffectsV7>*pending;};
 spike_timing::Services s{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&k){if(k=="memory.shared")return 25ul;return 17+std::stoul(k.substr(k.find_last_of('.')+1));},[](auto){return 0;},
 [&](const auto&effects){
   assert(effects.size()==1);
   if(input_retirement&&!effects[0].write){
     assert(!native_read&&effects[0].bytes>=16&&effects[0].bytes<=64&&effects[0].bytes%16==0);++native_gets;lookup_times.push_back(q.now());
     if(aggregate_probe&&native_gets==1)return spike_timing::SharedEffects{{9600},{},{},Cycle{5}};
     spike_timing::ReadAllocationEffectsV7 batch;batch.source_request.latency=0;
     spike_timing::ReadAllocationV7 a;a.resident=true;a.device_resident_no_probe=true;a.inner_address=effects[0].address;a.inner_bytes=effects[0].bytes;
     a.miss.line=a.inner_address/64;a.miss.set=a.miss.line%1024;a.miss.slot=a.miss.set*8;a.miss.generation=1;
     a.source_request=spike_timing::SharedEffects{{9600+a.miss.line%64},{},{},Cycle{2}};batch.allocations.push_back(a);native_read=std::move(batch);
     return spike_timing::SharedEffects{{},{},{},Cycle{0}};
   }
   assert(effects[0].write&&effects[0].bytes==64);puts.push_back(q.now());return spike_timing::SharedEffects{{},{},{},Cycle{1}};
 },
 [&](const auto&k,auto n){if(k=="target.posted.parent_writeback_prefix_publications"){parent_prefix_at=q.now();assert(engine.ready(9000)==parent_prefix_at&&engine.ready(9200)!=parent_prefix_at);}if(k=="target.posted.read_lookup_after_mshr_admission")deferred_lookups+=n;if(k=="target.posted.full_raw_write_beats")counted+=n;if(k=="target.posted.resident_get_mshr_request_releases"&&n)resident_releases.push_back(q.now());},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;h.source_masked_i8_readout=enabled;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;c.readout_stream=ReadoutStreamConfig{2,6,2,6,5,8,16,16};
 PostedSourceObserver target(s,q,h,c,0);
 spike_timing::FullWritePacketServiceV3 service;service.opaque=&puts;
 service.admit=[](void*opaque,const spike_timing::FullWritePacketV3*r,spike_timing::WriteTransactionEffectsV2*out){
   assert(spike_timing::full_write_packet_valid(*r)&&(r->transaction_bytes==32||r->transaction_bytes==64));
   static_cast<std::vector<Cycle>*>(opaque)->push_back(r->accepted);
   out->base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+(r->address-0x81000000)/64)},{},Cycle{2}};return true;
 };
 target.full_write_packets(service);
 if(cold&&!dirty){spike_timing::ColdWriteServiceV4 cold_service;cold_service.opaque=&puts;
   cold_service.beat=[](void*,const auto*,auto*){return false;};
   cold_service.packet=[](void*opaque,const spike_timing::FullWritePacketV3*r,spike_timing::WriteTransactionEffectsV4*out){
     static_cast<std::vector<Cycle>*>(opaque)->push_back(r->accepted);
     out->resident.base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+(r->address-0x81000000)/64)},{},Cycle{2}};
     spike_timing::WriteMissV4 m;m.line=r->address/64;m.set=m.line%1024;m.slot=m.set;m.generation=1;m.acquire_block=r->transaction_bytes<64;
     if(m.acquire_block){m.fill_latency=16;m.fill_bus=4;}out->miss=m;return true;
   };target.cold_writes(cold_service);
 }
 if(dirty&&!victim){assert(cold);spike_timing::ColdWriteServiceV5 cold_service;cold_service.opaque=&puts;
   cold_service.beat=[](void*,const auto*,auto*){return false;};
   cold_service.packet=[](void*opaque,const spike_timing::FullWritePacketV3*r,spike_timing::WriteTransactionEffectsV5*out){
     static_cast<std::vector<Cycle>*>(opaque)->push_back(r->accepted);
     const auto row=(r->address-0x81000000)/64;
     out->resident.base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+row)},{},Cycle{2}};
     spike_timing::WriteMissV5 m;m.line=r->address/64;m.set=m.line%1024;m.slot=m.set;m.generation=1;
     m.evicted_line=m.line+1024;m.dirty_eviction=true;m.release_writes={merlin_timing::ValueId(7000+row)};
     m.release_latency=24;m.release_bus=8;m.acquire_block=r->transaction_bytes<64;
     if(m.acquire_block){m.fill_latency=16;m.fill_bus=4;}out->miss=m;return true;
   };target.cold_writes(cold_service);
 }
 unsigned released=0;ReadState read_state{&released,&native_read};
 if(victim){assert(cold&&dirty);spike_timing::ColdWriteServiceV6 cold_service;cold_service.opaque=&released;
   cold_service.beat=[](void*,const auto*,auto*){return false;};
   cold_service.packet=[](void*,const spike_timing::FullWritePacketV3*r,spike_timing::WriteTransactionEffectsV6*out){
     const auto row=(r->address-0x81000000)/64;
     out->resident.base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+row)},{},Cycle{2}};
     spike_timing::WriteMissV5 m;m.line=r->address/64;m.set=m.line%1024;m.slot=m.set*8;m.generation=2;
     m.evicted_line=m.line+1024;m.dirty_eviction=true;m.release_writes={merlin_timing::ValueId(7000+row)};
     m.release_latency=24;m.release_bus=8;m.acquire_block=r->transaction_bytes<64;
     if(m.acquire_block){m.fill_latency=16;m.fill_bus=4;}out->miss=m;
     out->victim=spike_timing::VictimProbeV6{*m.evicted_line,m.set,0,1,8000+row,false,true,0,"source-fixture"};return true;
   };
   cold_service.client_released=[](void*opaque,const auto*,Cycle){++*static_cast<unsigned*>(opaque);return true;};
   target.cold_writes(cold_service);
 }
 std::optional<Cycle>read_done,resident_done,batch_done;unsigned batch_callbacks=0;
 std::pair<std::optional<Cycle>*,unsigned*>callback{&batch_done,&batch_callbacks};
 if(source_read){
   spike_timing::ReadAllocationServiceV7 svc;svc.opaque=&read_state;svc.take=[](void*opaque,auto*out){
     auto&pending=*static_cast<ReadState*>(opaque)->pending;if(!pending)return false;*out=std::move(*pending);pending.reset();return true;
   };
   svc.client_released=[](void*opaque,const auto*,Cycle){++*static_cast<ReadState*>(opaque)->released;return true;};
   auto old=svc;old.snapshot_revision=3;bool rejected=false;
   try{target.read_allocations(old);}catch(const std::invalid_argument&){rejected=true;}assert(rejected);
   old=svc;old.snapshot_revision=4;rejected=false;
   try{target.read_allocations(old);}catch(const std::invalid_argument&){rejected=true;}assert(rejected);
   target.read_allocations(svc);
   spike_timing::ReadAllocationEffectsV7 batch;batch.source_request=spike_timing::SharedEffects{{},{9200},{},Cycle{3}};
   spike_timing::ReadAllocationV7 a;a.miss.line=0x85000000/64;a.miss.set=a.miss.line%1024;a.miss.slot=a.miss.set*8;a.miss.generation=2;
   a.miss.evicted_line=a.miss.line+1024;a.miss.dirty_eviction=true;a.miss.acquire_block=true;a.miss.fill_latency=16;a.miss.fill_bus=4;
   a.source_request=spike_timing::SharedEffects{{9200},{9000},{},Cycle{2}};a.miss.release_latency=24;a.miss.release_bus=8;a.miss.release_writes={9100};a.inner_address=a.miss.line*64;a.inner_bytes=64;a.inner_acquire=true;
   a.victim=spike_timing::VictimProbeV6{*a.miss.evicted_line,a.miss.set,0,1,8100,false,true,0,"source-fixture"};batch.allocations.push_back(a);
   if(parent_phase){
     batch.parent_writebacks.push_back({*a.miss.evicted_line*64,64,0,{9000}});
     if(parent_phase==2)batch.source_request.writes.push_back(9000);
     if(parent_phase==3){batch.parent_writebacks.clear();batch.source_request.writes.push_back(9000);}
     if(parent_phase==4)batch.parent_writebacks[0].before_child=1;
     if(parent_phase>=2){assert(!target.submit_read_allocations(batch,merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"cpu_data"},0,&read_done,[](void*,Cycle){}));assert(q.progress().failed&&!unknown.empty());return;}
   }
   assert(target.submit_read_allocations(batch,merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"cpu_data"},0,&read_done,[](void*cookie,Cycle t){*static_cast<std::optional<Cycle>*>(cookie)=t;}));
   batch.parent_writebacks.clear();
   batch.source_request=spike_timing::SharedEffects{{9000},{},{},Cycle{0}};batch.allocations[0].source_request=spike_timing::SharedEffects{{9000},{},{},Cycle{2}};batch.allocations[0].resident=true;
   batch.allocations[0].victim.reset();batch.allocations[0].miss.evicted_line.reset();batch.allocations[0].miss.dirty_eviction=false;
   batch.allocations[0].miss.fill_latency=0;batch.allocations[0].miss.fill_bus=0;batch.allocations[0].miss.release_latency=0;batch.allocations[0].miss.release_bus=0;batch.allocations[0].miss.release_writes.clear();
   assert(target.submit_read_allocations(batch,merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"cpu_data"},0,&resident_done,[](void*cookie,Cycle t){*static_cast<std::optional<Cycle>*>(cookie)=t;}));
   batch.source_request=spike_timing::SharedEffects{{9000},{9400},{},Cycle{3}};
   auto second=batch.allocations.front();second.miss.line+=1;second.miss.set+=1;second.miss.slot+=8;second.inner_address+=64;
   batch.allocations[0].source_request=spike_timing::SharedEffects{{9400},{9300},{},Cycle{2}};
   second.source_request=spike_timing::SharedEffects{{9400},{9301},{},Cycle{2}};batch.allocations.push_back(second);
   assert(target.submit_read_allocations(batch,merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"cpu_data"},0,&callback,[](void*cookie,Cycle t){
     auto&state=*static_cast<std::pair<std::optional<Cycle>*,unsigned*>*>(cookie);*state.first=t;++*state.second;
   }));

 }
 if(resident_retirement){
   // Two distinct ready resident lines in the SAME set. The first D sink
   // stalls: MSHR request retirement must not publish its data/cache owner.
   for(unsigned i=0;i<2;++i){
     spike_timing::ReadAllocationEffectsV7 b;b.source_request.latency=0;
     spike_timing::ReadAllocationV7 a;a.resident=true;a.device_resident_no_probe=true;
     a.miss.line=0x30000+i*1024;a.miss.set=a.miss.line%1024;a.miss.slot=i;a.miss.generation=1;
     a.inner_address=a.miss.line*64;a.inner_bytes=16;a.source_request.latency=0;a.source_request.writes={9500+i};b.allocations.push_back(a);
     auto output=i?&last_get:&first_get;
     assert(target.submit_read_allocations(b,merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"device_get"},0,output,
       [](void*opaque,Cycle t){*static_cast<std::optional<Cycle>*>(opaque)=t;},
       [&,i](std::size_t beat,Cycle t,auto accepted){assert(beat==0);
         q.post(t+(i?0:20),{},[accepted](auto&q,auto){q.complete(accepted);});}));
   }
 }
 std::vector<ValueId>loaded;
 if(input_retirement){
   for(unsigned row=0;row<16;++row)loaded.push_back(8192+row);
   TransferPhase phase{};phase.scratchpad_load=true;phase.reader_packets=reader_packets(0x81004000,16,16,16,16,64,64);phase.reader_destinations=loaded;
   target.submit("load",Event{0,{},{loaded.data(),loaded.size()},{},Cycle{1}},Cycle{1},2,0,0,phase,{{0x81004000,16,16,16,false}},merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"target.load"});
 }
 std::vector<ValueId>reads;for(unsigned i=0;i<16;++i)reads.push_back(16384+i);
 TransferPhase phase{};phase.arrival=8;phase.row_bytes=64;
 const std::uint64_t address=0x81000000;
 target.submit("store",Event{0,{reads.data(),reads.size()},{},{},Cycle{1}},Cycle{1},3,address,(16ull<<48)|(std::uint64_t(columns)<<32)|0xa0000000u,phase,{{address,16,64,stride,true}},merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"target.store"});
 target.drain(0);
 if(resident_retirement){
   assert(first_get&&last_get&&*last_get>*first_get&&resident_releases.size()>=2);
   assert(resident_releases[0]<*first_get&&resident_releases[1]<*first_get);
   assert(engine.ready(9500)==first_get&&engine.ready(9501)==last_get);
 }
 if(input_retirement){assert(native_gets==16&&!native_read);for(auto row:loaded)assert(engine.ready(row)&&*engine.ready(row)>0);}
 if(source_read){
   while(!batch_done&&!q.progress().failed)if(!q.step(true))break;
   assert(batch_done&&batch_callbacks==1&&engine.ready(9400)==batch_done);
   assert(engine.ready(9300)&&engine.ready(9301)&&*engine.ready(9300)<*engine.ready(9301));
 }
 if(source_read){if(!read_done||!resident_done||q.progress().failed){std::cerr<<"r="<<read_done.value_or(9999)<<" hit="<<resident_done.value_or(9999)<<" why="<<q.reason()<<"\n";}
 if(!read_done||!resident_done||!(*resident_done>*read_done)||engine.ready(9000)!=read_done)std::cerr<<"cold="<<read_done.value_or(9999)<<" resident="<<resident_done.value_or(9999)<<" value="<<engine.ready(9000).value_or(9999)<<" now="<<q.now()<<"\n";
 assert(read_done&&resident_done&&*resident_done>*read_done&&engine.ready(9000)==read_done);}
 if(beat_forward){
   std::optional<Cycle>zero,offset;
   for(unsigned i=0;i<2;++i){
     spike_timing::ReadAllocationEffectsV7 b;b.source_request.latency=0;
     spike_timing::ReadAllocationV7 a;a.miss.line=0x60000+i;a.miss.set=a.miss.line%1024;a.miss.slot=a.miss.set*8;a.miss.generation=1;
     a.miss.acquire_block=true;a.miss.fill_latency=40;a.miss.fill_bus=8;
     a.inner_address=a.miss.line*64+i*16;a.inner_bytes=16;a.source_request.latency=2;a.source_request.writes={9700+i};b.allocations.push_back(a);
     auto result=i?&offset:&zero;
     assert(target.submit_read_allocations(b,merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"beat_read"},q.now(),result,
       [](void*opaque,Cycle t){*static_cast<std::optional<Cycle>*>(opaque)=t;}));
   }
   while(q.step(true)){}assert(!q.progress().failed&&zero&&offset&&*zero<*engine.ready(9700)&&*offset==*engine.ready(9701));
 }
 if(deferred){assert(deferred_lookups==16&&lookup_times.size()==16);for(unsigned i=1;i<16;++i)assert(lookup_times[i]>lookup_times[i-1]);}
 if(deferred&&!aggregate_probe){
   // An older device request owns this set and writes the same cache slot.
   // The CPU must not bind a speculative later writer while waiting for it.
   const auto begin=q.now();std::optional<Cycle>old_done;
   spike_timing::ReadAllocationEffectsV7 old;old.source_request.latency=0;
   spike_timing::ReadAllocationV7 prior;prior.resident=true;prior.inner_address=0x86000000;prior.inner_bytes=64;
   prior.miss.line=prior.inner_address/64;prior.miss.set=prior.miss.line%1024;prior.source_request={{},{9900},{},Cycle{2}};
   old.allocations.push_back(prior);
   assert(target.submit_read_allocations(old,merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"older_device"},begin,&old_done,
     [](void*opaque,Cycle t){*static_cast<std::optional<Cycle>*>(opaque)=t;},
     [&](std::size_t,Cycle t,auto accepted){q.post(t+8,{},[accepted](auto&q,auto){q.complete(accepted);});}));
   struct CpuState{std::optional<Cycle>done;unsigned calls=0,completions=0;Cycle first=0,classified=0;};
   CpuState cpu;spike_timing::CpuReadAdmissionV10 request;request.line_addresses={prior.inner_address,prior.inner_address+64};
   assert(target.submit_cpu_read(request,merlin_timing::StageOrigin{0x80005000,0x1234,{},"cpu_fetch"},begin,&cpu,
     [](void*opaque,Cycle at,spike_timing::ReadAllocationEffectsV7*out){
       auto&state=*static_cast<CpuState*>(opaque);if(!state.calls)state.first=at;
       if(++state.calls<3)return spike_timing::CpuReadLookupStatusV10::retry;
       state.classified=at;out->source_request={{},{9908},{},Cycle{1}};
       for(unsigned i=0;i<2;++i){spike_timing::ReadAllocationV7 a;a.resident=true;a.inner_address=0x86000000+i*64;a.inner_bytes=64;
         a.miss.line=a.inner_address/64;a.miss.set=a.miss.line%1024;a.source_request={{},{9900+i},{},Cycle{2}};out->allocations.push_back(a);}
       return spike_timing::CpuReadLookupStatusV10::accepted;
     },[](void*opaque,Cycle at){auto&state=*static_cast<CpuState*>(opaque);state.done=at;++state.completions;}));
   assert(cpu.calls==0);while(q.step(true)){}
   assert(!q.progress().failed&&old_done&&cpu.done&&cpu.first>*old_done&&cpu.classified==cpu.first+2&&cpu.completions==1);
   assert(engine.ready(9908)==cpu.done&&engine.ready(9900)&&*engine.ready(9900)>*old_done);
 }
 if(parent_phase==1)assert(parent_prefix_at==std::optional<Cycle>{3}&&read_done&&*read_done>*parent_prefix_at);
 if(!selected){assert(unknown.empty()&&target.complete()&&counted==0&&puts.size()==16);return;}
 if(!unknown.empty()||!target.complete()){for(const auto&reason:unknown)std::cerr<<reason<<"\n";std::cerr<<"complete="<<target.complete()<<" counted="<<counted<<" released="<<released<<" stride="<<stride<<"\n";}
 assert(unknown.empty()&&target.complete()&&counted==64&&(victim?released>0:puts.size()==(stride==64?16:24)));
 for(std::size_t i=1;i<puts.size();++i)assert(puts[i]>puts[i-1]);
}
int main(){for(unsigned phase=1;phase<=4;++phase)check(true,64,true,true,true,true,false,false,false,false,false,phase);check(true);check(true,96);check(false);check(true,64,true);check(true,96,true);check(true,64,true,true);check(true,96,true,true);check(true,64,true,true,true);check(true,96,true,true,true);check(true,64,true,true,true,true);check(true,64,true,true,true,true,true);check(true,64,true,true,true,true,true,true);check(true,64,true,true,true,true,true,true,true);check(true,64,true,true,true,true,true,true,true,true);check(true,64,true,true,true,true,true,true,true,true,true);}
