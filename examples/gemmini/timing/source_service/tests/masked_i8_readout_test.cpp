#include "posted.hpp"
#include <cassert>
#include <map>
using namespace gemmini_annotated_spike;
void check(bool enabled,unsigned columns=1,bool missing=false,bool probe=false,bool full=false){
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
 if(missing)facts.erase("target.hardware.relu_same_accumulator_scale_pipeline");
 std::vector<std::string>unknown;std::vector<Cycle>puts;std::uint64_t counted=0;
 spike_timing::Services s{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&k){return 17+std::stoul(k.substr(k.find_last_of('.')+1));},[](auto){return 0;},
 [&](const auto&effects){assert(effects.size()==1&&effects[0].write&&effects[0].bytes==16);puts.push_back(q.now());return spike_timing::SharedEffects{{},{},{},Cycle{1}};},
 [&](const auto&k,auto n){if(k=="target.posted.masked_i8_rows")counted+=n;},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;h.source_masked_i8_readout=enabled;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;c.readout_stream=ReadoutStreamConfig{2,6,2,6,5,8,16,16};
 PostedSourceObserver target(s,q,h,c,0);
 spike_timing::WriteTransactionServiceV1 service;service.opaque=&puts;service.admit=[](void*opaque,const spike_timing::WriteTransactionV1*r,spike_timing::WriteTransactionEffectsV1*out){
   auto useful=spike_timing::one_beat_write_useful(*r);assert(useful);
   assert((useful->bytes==1&&useful->address%16==3)||(useful->bytes==16&&useful->address%16==0));
   static_cast<std::vector<Cycle>*>(opaque)->push_back(r->accepted);
   out->source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+(r->address-0x81000000)/64)},{},Cycle{2}};out->sram_read_required=r->mask!=0xffff;return true;
 };
 target.write_transactions(service);std::vector<ValueId>reads;for(unsigned i=0;i<16;++i)reads.push_back(16384+i);
 std::vector<Cycle>probe_starts,read_starts;
 engine.trace_sink([&](const merlin_timing::Trace&r){if(!r.event.origin||!r.result.start||std::string(r.action)!="submit_detached")return;
   if(r.event.origin->actor=="target.store.masked_private_probe")probe_starts.push_back(*r.result.start);
   if(r.event.origin->actor=="target.store.masked_source_d_read")read_starts.push_back(*r.result.start);
 });
 if(probe){spike_timing::WriteTransactionServiceV2 extended;extended.opaque=&puts;
   extended.admit=[](void*opaque,const spike_timing::WriteTransactionV1*r,spike_timing::WriteTransactionEffectsV2*out){
     static_cast<std::vector<Cycle>*>(opaque)->push_back(r->accepted);auto useful=spike_timing::one_beat_write_useful(*r);assert(useful&&(useful->bytes==1||useful->bytes==16));
     out->base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+(r->address-0x81000000)/64)},{},Cycle{2}};
     out->base.sram_read_required=r->mask!=0xffff;out->probe=spike_timing::WriteProbeV2{25,2,1,2,1,64,16,true};return true;
   };target.write_transactions(extended);
 }
 TransferPhase phase{};phase.arrival=8;phase.row_bytes=columns;
 const std::uint64_t address=0x81000000+(full?0:3);
 target.submit("store_act1",Event{0,{reads.data(),reads.size()},{},{},Cycle{1}},Cycle{1},3,address,(16ull<<48)|(std::uint64_t(columns)<<32)|0x80000000u,phase,{{address,16,columns,64,true}},merlin_timing::StageOrigin{0x80004000,0xabcdef,{},"target.store"});
 target.drain(0);
 if(!enabled||(columns!=1&&!full)){assert(!unknown.empty()&&!target.complete()&&puts.empty());return;}
 assert(unknown.empty()&&target.complete()&&counted==16&&puts.size()==16);
 if(probe){assert(probe_starts.size()==16);if(full)assert(read_starts.empty());else{assert(read_starts.size()==16);assert(read_starts[0]==probe_starts[0]+7);}}
 for(std::size_t i=1;i<puts.size();++i)assert(puts[i]>=puts[i-1]+1);
}
int main(){check(true);check(false);check(true,1,false,true);check(true,16,false,false,true);check(true,16,false,true,true);bool refused=false;try{check(true,1,true);}catch(const std::invalid_argument&){refused=true;}assert(refused);}
