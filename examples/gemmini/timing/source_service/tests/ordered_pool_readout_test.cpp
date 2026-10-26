#include "posted.hpp"
#include <cassert>
#include <map>
#include <iostream>
using namespace gemmini_annotated_spike;
std::optional<Cycle>full_writer_baseline;
bool check(unsigned channels,unsigned pitch,bool enabled=true,bool pressure=false,bool packets=false,bool shared=false,bool dirty_put=false,bool ordered_put=false,bool release=false,bool local_completion=false,unsigned higher_priority_latency=0){
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
 facts["target.scheduling.source_masked_i8_readout"]=1;
 facts["target.hardware.source_d_client_beat_bytes"]=16;facts["target.hardware.source_d_write_chunk_bytes"]=8;facts["target.hardware.source_d_sram_read_stages"]=2;facts["target.assumptions.source_d_no_external_banked_store_stalls"]=1;

 if(enabled)facts["target.scheduling.source_ordered_pool_readout"]=1;
 facts["target.hardware.pool_writer_single_reduction_register"]=1;facts["target.hardware.pool_writer_store_only_last_request"]=1;facts["target.hardware.pool_garbage_metadata_bypass"]=1;
 if(packets){
   facts["target.scheduling.source_masked_packet_readout"]=1;facts["target.scheduling.source_full_raw_packet_readout"]=1;
   facts["target.hardware.source_sink_a_put_lists"]=40;facts["target.hardware.source_sink_a_put_beats"]=40;facts["target.hardware.source_full_raw_scale_pipeline"]=8;
   facts["target.scheduling.source_masked_probe_sinkc"]=1;facts["target.hardware.source_d_banked_store_banks"]=8;
   facts["target.hardware.sinkc_data_queue_stages"]=1;facts["target.hardware.mshr_probe_response_register_stages"]=1;
 }
 if(shared){
   facts["target.scheduling.source_d_shared_pipeline"]=1;
   facts["target.scheduling.source_d_read_input_retirement"]=1;
   facts["memory.source_read_allocations.enabled"]=1;
   facts["target.hardware.source_d_s2_entries"]=1;facts["target.hardware.source_d_s3_entries"]=1;
   facts["target.hardware.source_d_s4_entries"]=1;facts["target.hardware.source_d_read_sram_stages"]=2;
   facts["target.hardware.source_d_s1_last_input_retires_busy"]=1;
 }
 if(release){facts["target.scheduling.source_store_request_release"]=1;facts["target.hardware.store_controller_last_request_releases_command"]=1;facts["target.hardware.store_dma_tracker_entries"]=2;}
 if(local_completion){facts["target.hardware.source_completion_priority_execute_load_store"]=1;facts["target.scheduling.source_store_local_request_completion"]=1;facts["target.hardware.store_dma_response_at_local_read_acceptance"]=1;facts["target.hardware.store_dma_completion_register_stages"]=1;facts["target.hardware.store_dma_credit_reuse_register_stages"]=1;}
 if(ordered_put)facts["target.scheduling.source_ordered_resident_dirty_put"]=1;
 if(dirty_put){
   facts["target.scheduling.source_resident_dirty_put_request_retirement"]=1;
   facts["target.hardware.mshr_resident_dirty_put_no_wait_at_source_d_request"]=1;
   facts["target.scheduling.source_cold_write_misses"]=1;
   facts["memory.device_write_miss_pipeline.enabled"]=1;facts["memory.device_write_miss_pipeline.line_bytes"]=64;
   facts["memory.device_write_miss_pipeline.outer_beat_bytes"]=8;facts["memory.device_write_miss_pipeline.demand_mshrs"]=10;
   facts["memory.caches.l2.sets"]=1024;facts["memory.caches.l2.ways"]=8;
 }
 std::vector<std::string>unknown;std::vector<Cycle>puts;unsigned captures=0,read_count=0,garbage=0,early_releases=0,handoffs=0,local_responses=0,local_completions=0,output_completions=0,arbitration_waits=0;
 spike_timing::Services s{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&k){if(k.find("memory.l2.data.bank.")==0)return 17+std::stoi(k.substr(k.find_last_of('.')+1));return 0;},[](auto){return 0;},[](const auto&){return spike_timing::SharedEffects{{},{},{},Cycle{1}};},
 [&](const auto&k,auto n){if(k=="target.posted.store_completion_arbitration_wait_cycles")arbitration_waits+=n;if(k=="target.posted.store_local_request_responses")local_responses+=n;if(k=="target.posted.store_local_tracker_completions")local_completions+=n;if(k=="target.posted.store_output_completions")output_completions+=n;if(k=="target.posted.ordered_dirty_put_value_handoffs")handoffs+=n;if(k=="target.posted.resident_dirty_put_mshr_request_releases")early_releases+=n;if(k=="target.posted.pool_writer_captures")captures+=n;if(k=="target.posted.pool_acc_reads")read_count+=n;if(k=="target.posted.pool_garbage_requests")garbage+=n;},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;h.source_masked_i8_readout=true;h.source_ordered_pool_readout=enabled;h.source_masked_packet_readout=packets;
 if(packets){h.accumulator_readout_packet_geometry=true;h.accumulator_streamed_readout=true;h.accumulator_readout_arrival=8;h.writer_beat_bytes=16;h.writer_max_request_bytes=64;h.accumulator_readout_full_packets=true;}
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;c.readout_stream=ReadoutStreamConfig{2,6,2,6,5,8,16,16};
 PostedSourceObserver target(s,q,h,c,0);
 spike_timing::WriteTransactionServiceV1 svc;svc.opaque=&puts;svc.admit=[](void*opaque,const spike_timing::WriteTransactionV1*r,spike_timing::WriteTransactionEffectsV1*out){
   assert(spike_timing::one_beat_write_useful(*r));static_cast<std::vector<Cycle>*>(opaque)->push_back(r->accepted);
   out->source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+(r->address-0x81000000)/64)},{},Cycle{2}};out->sram_read_required=r->mask!=0xffff;return true;
 };target.write_transactions(svc);
 if(packets){spike_timing::MaskedWriteServiceV8 service;service.opaque=&puts;
   service.packet=[](void*opaque,const spike_timing::MaskedWritePacketV8*r,spike_timing::WriteTransactionEffectsV6*out){
     assert(spike_timing::masked_write_packet_useful(*r));static_cast<std::vector<Cycle>*>(opaque)->push_back(r->accepted);
     out->resident.base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+(r->address-0x81000000)/64)},{},Cycle{2}};return true;
   };target.masked_writes(service);
 }
 std::set<std::uint64_t>dirty;struct Native{std::set<std::uint64_t>*dirty;std::vector<Cycle>*puts;};Native native{&dirty,&puts};
 if(dirty_put){spike_timing::MaskedWriteServiceV9 svc;svc.opaque=&native;
   svc.packet=[](void*opaque,const spike_timing::MaskedWritePacketV8*r,spike_timing::MaskedWriteEffectsV9*out){
     auto&native=*static_cast<Native*>(opaque);native.puts->push_back(r->accepted);auto&dirty=*native.dirty;out->resident_dirty_no_probe=dirty.count(r->address/64);dirty.insert(r->address/64);
     out->original.resident.base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+(r->address-0x81000000)/64)},{},Cycle{2}};return true;
   };target.masked_writes(svc);
 }
 if(pressure){Demand hold{16,1,Cycle{100}};assert(engine.submit_detached(Event{0,{},{},{&hold,1},Cycle{1}}).start==0);}
 std::optional<Cycle>second_read,third_read,last_first_publication,first_last_read,last_publication,higher_done;
 std::vector<ValueId>actual_reads;engine.trace_sink([&](const merlin_timing::Trace&r){
 if(r.event.origin&&std::string(r.action)=="submit_detached"){
   const auto&a=r.event.origin->actor;
   if(a=="stress.higher")higher_done=r.result.ready;
   if(a=="stress.first.acc_read")first_last_read=r.result.start;
   if(a.find("masked_write_publication")!=std::string::npos)last_publication=r.result.ready;
   if(a=="stress.second.acc_read"&&!second_read)second_read=r.result.start;
   if(a=="stress.third.acc_read"&&!third_read)third_read=r.result.start;
   if(a=="stress.first.masked_write_publication"&&r.event.writes.size)last_first_publication=r.result.ready;
 }
 if(r.event.origin&&r.event.origin->actor=="target.pool_store.pool_acc_read"&&std::string(r.action)=="submit_detached"){
   assert(r.event.reads.size==1);actual_reads.push_back(r.event.reads[0]);
 }});
 Parameters p;for(auto k:{"config","pool_store"}){p[std::string(k)+".latency_cycles"]=1;p[std::string(k)+".occupancy_cycles"]=1;}
 std::vector<Transfer>transfers;
 TargetObserver decoder(engine,h,p,{},0,[&](View<Transfer>v){transfers.assign(v.data,v.data+v.size);return TransferEffects{{},{},{},Cycle{0}};},[&](const auto&k,const auto&e,auto o,auto f,auto r1,auto r2,const auto&phase){return target.submit(k,e,o,f,r1,r2,phase,transfers,merlin_timing::StageOrigin{4,0xabcdef,{},"target."+k});});
 // 3x3 windows/stride2/pad1 over5x5 ->3x3 outputs. Every pad request
 // remains present, repeated rows are NOT deduplicated as a performance law.
 const auto rs1=2ull|(2ull<<4)|(3ull<<6)|(1ull<<8)|(1ull<<10)|(3ull<<24)|(3ull<<32)|(3ull<<40)|(5ull<<48)|(5ull<<56);
 decoder.observe_command(0,0,rs1,(0x3f800000ull<<32)|pitch);
 decoder.observe_command(4,3,0x81000000,(1ull<<48)|(std::uint64_t(channels)<<32)|0x80000000u);target.drain(0);
 if(!enabled||(!packets&&channels==16&&pitch==17)){assert(!target.complete()&&!unknown.empty()&&puts.empty());return false;}
 auto expected=pool_readout_requests(16384,5,5,3,3,3,2,1,1,3,0x81000000,pitch,channels);assert(expected);
 std::vector<ValueId>reads;for(const auto&r:*expected)if(r.local_row)reads.push_back(*r.local_row);
 std::size_t original_packets=0;for(const auto&r:*expected)if(r.store)original_packets+=writer_packets(r.output_address,r.bytes,16,64)->size();
 assert(unknown.empty()&&target.complete()&&captures==81&&puts.size()==original_packets&&read_count==reads.size()&&garbage==81-reads.size());assert(actual_reads==reads);
 for(unsigned i=1;i<puts.size();++i)assert(puts[i]>puts[i-1]);
 if(pressure)assert(puts.front()>100);
 if(packets){
   // Same StreamWriter/SourceD accepts raw partial multibeat after pooled i8,
   // then i8 after raw, with no artificial full-fence mode switch.
   decoder.observe_command(8,0,2,(0x3f800000ull<<32)|64);
   decoder.observe_command(12,3,0x81001003,(2ull<<48)|(16ull<<32)|0xa0000000u);target.drain(q.now());
   decoder.observe_command(16,3,0x8100200f,(2ull<<48)|(16ull<<32)|0x80000000u);target.drain(q.now());
   if(!unknown.empty())for(const auto&x:unknown)std::cerr<<x<<"\n";
   assert(target.complete()&&unknown.empty()&&puts.size()==original_packets+6);
 }
 if(dirty_put&&channels==16&&pitch==16){
   const auto start=q.now();const auto before=puts.size();
   std::vector<ValueId>local;for(unsigned i=0;i<16;++i)local.push_back(16384+i);
   TransferPhase phase{};phase.arrival=8;
   for(unsigned n=0;n<3;++n){const std::uint64_t address=0x81003000+n*256;
     target.submit("store",Event{q.now(),{local.data(),local.size()},{},{},Cycle{1}},Cycle{1},3,address,(16ull<<48)|(16ull<<32)|0x80000000u,phase,{{address,16,16,16,true}},merlin_timing::StageOrigin{24+n*4,0xabcdef,{},n==0?"stress.first":n==1?"stress.second":"stress.third"});
   }
   if(higher_priority_latency)target.submit("config",Event{start,{},{},{},Cycle{higher_priority_latency}},Cycle{1},0,1,0,{}, {},merlin_timing::StageOrigin{36,0xabcdef,{},"stress.higher"});
   target.drain(q.now());
   if(!unknown.empty())for(const auto&reason:unknown)std::cerr<<reason<<"\n";
   assert(target.complete()&&unknown.empty()&&puts.size()==before+48);
   if(ordered_put){assert(handoffs>0&&full_writer_baseline&&q.now()-start<*full_writer_baseline);}else full_writer_baseline=q.now()-start;
   assert(second_read&&third_read&&last_first_publication);
   if(local_completion){assert(first_last_read&&*third_read>=*first_last_read+2&&*third_read<*last_first_publication);assert(last_publication&&q.now()>=*last_publication);assert(local_completions==output_completions&&local_responses>=48);}
   else if(release){assert(*second_read<*last_first_publication&&*third_read>=*last_first_publication);}else assert(*second_read>=*last_first_publication);
   if(higher_priority_latency){
     if(higher_done==std::optional<Cycle>{*first_last_read+1}){assert(arbitration_waits>0&&*third_read>=*first_last_read+3);return true;}
     return false;
   }
   std::cout<<"ordered full16B output writer handoffs "<<handoffs<<"\n";
 }else assert(handoffs==0);
 if(dirty_put)assert(early_releases>0);else assert(early_releases==0);
 std::cout<<"ordered pooled ACC reads, padding bypass, finite reduction writer and original packet outputs PASS\n";
 return false;
}
int main(){check(16,16,true,false,true,true,true,false);bool collision=false;for(unsigned delay=1;delay<=128&&!collision;++delay)collision=check(16,16,true,false,true,true,true,true,true,true,delay);assert(collision);std::cout<<"Higher-priority source completion defers original store tracker credit PASS\n";check(16,16,true,false,true,true,true,false);check(16,16,true,false,true,true,true,true,true,true);check(16,16,true,false,true,true,true,true,true);check(16,16,true,false,true,true,true,true);check(16,64);check(1,17);check(16,17);check(16,64,false);check(16,64,true,true);check(16,17,true,false,true);check(16,17,true,false,true,true);check(16,17,true,false,true,true,true);}
