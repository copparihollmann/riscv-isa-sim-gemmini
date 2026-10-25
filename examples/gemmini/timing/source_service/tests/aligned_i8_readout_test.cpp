#include "posted.hpp"
#include <cassert>
#include <map>
using namespace gemmini_annotated_spike;
void check(bool enabled,unsigned columns=16,bool missing=false){
 std::vector<merlin_timing::ResourceSpec>resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
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
 if(enabled)facts["target.scheduling.source_aligned_i8_readout"]=1;
 if(missing)facts.erase("target.hardware.relu_same_accumulator_scale_pipeline");
 std::vector<std::string>unknown;std::vector<Cycle>puts;std::uint64_t counted=0;
 spike_timing::Services s{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&){return 0;},[](auto){return 0;},
 [&](const auto&effects){assert(effects.size()==1&&effects[0].write&&effects[0].bytes==16);puts.push_back(q.now());return spike_timing::SharedEffects{{},{},{},Cycle{1}};},
 [&](const auto&k,auto n){if(k=="target.posted.i8_full_readout_rows")counted+=n;},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;c.readout_stream=ReadoutStreamConfig{2,6,2,6,5,8,16,16};
 PostedSourceObserver target(s,q,h,c,0);std::vector<ValueId>reads;for(unsigned i=0;i<16;++i)reads.push_back(16384+i);
 TransferPhase phase{};phase.arrival=8;phase.row_bytes=columns;
 target.submit("store_act1",Event{0,{reads.data(),reads.size()},{},{},Cycle{1}},Cycle{1},3,0x81000000,(16ull<<48)|(std::uint64_t(columns)<<32)|0x80000000u,phase,{{0x81000000,16,columns,64,true}});
 target.drain(0);
 if(!enabled||columns!=16){assert(!unknown.empty()&&!target.complete()&&puts.empty());return;}
 assert(unknown.empty()&&target.complete()&&counted==16&&puts.size()==16&&puts.front()==20);
 for(std::size_t i=1;i<puts.size();++i)assert(puts[i]>=puts[i-1]+1);
}
int main(){check(true);check(false);check(true,15);bool refused=false;try{check(true,16,true);}catch(const std::invalid_argument&){refused=true;}assert(refused);}
