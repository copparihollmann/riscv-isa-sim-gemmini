#include "posted.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace gemmini_annotated_spike;
void run(unsigned columns,unsigned alignment=0,bool pressure=false,bool enabled=true,unsigned rows=3){
 const unsigned blocks=(columns+15)/16,pitch=96;
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


 facts["target.scheduling.source_masked_packet_readout"]=1;facts["target.scheduling.source_full_raw_packet_readout"]=1;
 facts["target.hardware.source_sink_a_put_lists"]=40;facts["target.hardware.source_sink_a_put_beats"]=40;facts["target.hardware.source_full_raw_scale_pipeline"]=8;
 facts["target.scheduling.source_masked_probe_sinkc"]=1;facts["target.hardware.source_d_banked_store_banks"]=8;facts["target.hardware.sinkc_data_queue_stages"]=1;facts["target.hardware.mshr_probe_response_register_stages"]=1;
 facts["target.scheduling.source_store_request_release"]=1;facts["target.hardware.store_controller_last_request_releases_command"]=1;facts["target.hardware.store_dma_tracker_entries"]=2;
 facts["target.scheduling.source_store_local_request_completion"]=1;facts["target.hardware.source_completion_priority_execute_load_store"]=1;facts["target.hardware.store_dma_response_at_local_read_acceptance"]=1;facts["target.hardware.store_dma_completion_register_stages"]=1;facts["target.hardware.store_dma_credit_reuse_register_stages"]=1;
 if(enabled){facts["target.scheduling.source_multiblock_i8_readout"]=1;facts["target.hardware.stream_writer_block_registers"]=4;facts["target.hardware.store_block_stride_rows"]=16;facts["target.hardware.store_block_last_only"]=1;}
 std::vector<std::string>unknown;std::vector<ValueId>actual_reads;unsigned partial=0,local=0,commands=0;std::vector<spike_timing::WriteUsefulBytes>useful;
 spike_timing::Services s{engine,[&](const auto&k)->std::optional<double>{auto i=facts.find(k);return i==facts.end()?std::nullopt:std::optional<double>{i->second};},[](const auto&k){if(k.find("memory.l2.data.bank.")==0)return 17+std::stoi(k.substr(k.find_last_of('.')+1));return 0;},[](auto){return 0;},[](const auto&){return spike_timing::SharedEffects{{},{},{},Cycle{1}};},
 [&](const auto&k,auto n){if(k=="target.posted.multiblock_i8_register_captures")partial+=n;if(k=="target.posted.store_local_request_responses")local+=n;if(k=="target.posted.store_output_completions")commands+=n;},[&](auto reason){unknown.push_back(reason);}};
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};h.source_identity_ingress=true;h.source_masked_i8_readout=true;h.source_masked_packet_readout=true;h.source_multiblock_i8_readout=enabled;
 h.accumulator_readout_packet_geometry=true;h.accumulator_streamed_readout=true;h.accumulator_readout_arrival=8;h.writer_beat_bytes=16;h.writer_max_request_bytes=64;h.accumulator_readout_full_packets=true;
 StagedConfig c{};c.source_identity_ingress=true;c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.late_accumulator_write_pipeline=2;c.readout_stream=ReadoutStreamConfig{2,6,2,6,5,8,16,16};
 PostedSourceObserver target(s,q,h,c,0);
 spike_timing::MaskedWriteServiceV8 service;service.opaque=&useful;
 service.packet=[](void*opaque,const spike_timing::MaskedWritePacketV8*r,spike_timing::WriteTransactionEffectsV6*out){
   auto interval=spike_timing::masked_write_packet_useful(*r);assert(interval);static_cast<std::vector<spike_timing::WriteUsefulBytes>*>(opaque)->push_back(*interval);
   out->resident.base.source_request=spike_timing::SharedEffects{{},{merlin_timing::ValueId(6000+r->address/64%128)},{},Cycle{2}};return true;
 };target.masked_writes(service);
 if(pressure){Demand hold{16,1,Cycle{100}};assert(engine.submit_detached(Event{0,{},{},{&hold,1},Cycle{1}}).start==0);}
 engine.trace_sink([&](const merlin_timing::Trace&r){if(r.event.origin&&r.event.origin->actor=="target.store.acc_read"&&std::string(r.action)=="submit_detached"){assert(r.event.reads.size==1);actual_reads.push_back(r.event.reads[0]);if(pressure)assert(r.result.start>=100);}});
 Parameters prices;for(auto kind:{"config","store"})for(auto field:{"latency_cycles","occupancy_cycles"})prices[std::string(kind)+"."+field]=1;
 std::optional<TransferPhase>phase;std::vector<Transfer>transfers;
 TargetObserver decoder(engine,h,prices,{},0,[&](View<Transfer>v){transfers.assign(v.data,v.data+v.size);return TransferEffects{{},{},{},Cycle{0}};},[&](const auto&kind,const Event&e,auto occupancy,auto funct,auto r1,auto r2,const auto&p){if(kind=="store"){phase=p;transfers={{0x81000000+alignment,rows,columns,pitch,true}};}return target.submit(kind,e,occupancy,funct,r1,r2,p,transfers,merlin_timing::StageOrigin{0x80000000,0x0000007b,{},"target."+kind});});

 decoder.observe_command(0,0,2,(0x3f800000ull<<32)|pitch);
 decoder.observe_command(4,3,0x81000000+alignment,(std::uint64_t(rows)<<48)|(std::uint64_t(columns)<<32)|0x80000020u);
 target.drain(0);
 if(!enabled){assert(!target.complete()&&!unknown.empty()&&actual_reads.empty()&&useful.empty());return;}
 if(!target.complete()){for(auto&x:unknown)std::cerr<<x<<"\n";}
 assert(target.complete()&&unknown.empty()&&phase&&phase->accumulator_readout_blocks==blocks);
 assert(actual_reads.size()==rows*blocks&&local==rows*blocks&&commands==1&&partial==rows*(blocks-1));
 for(unsigned r=0;r<rows;++r)for(unsigned b=0;b<blocks;++b)assert(actual_reads[r*blocks+b]==16384+32+b*16+r);
 const auto expected=*masked_writer_rows(0x81000000+alignment,rows,columns,pitch);std::size_t packets=0;std::uint64_t bytes=0;
 for(const auto&row:expected)packets+=row.size();
 assert(useful.size()==packets);
 for(const auto&p:useful)bytes+=p.bytes;
 assert(bytes==rows*columns);
 assert(decoder.counters().requested_write_bytes==rows*columns&&decoder.counters().local_read_bytes==rows*columns*4);
}
void unsupported(unsigned columns,bool full){
 std::vector<merlin_timing::ResourceSpec>resources{{0,1,128}};Engine engine(18000,resources);
 HardwareConfig h{16,16384,1024,1,4,32,true,true,std::uint8_t{0},false};
 h.source_multiblock_i8_readout=h.source_masked_packet_readout=h.accumulator_streamed_readout=h.accumulator_readout_packet_geometry=true;
 h.accumulator_readout_full_packets=true;h.accumulator_readout_arrival=8;h.writer_beat_bytes=16;h.writer_max_request_bytes=64;
 Parameters prices;for(auto kind:{"config","store"})for(auto field:{"latency_cycles","occupancy_cycles"})prices[std::string(kind)+"."+field]=1;
 bool mapped=false;
 TargetObserver decoder(engine,h,prices,{},0,[](View<Transfer>){return TransferEffects{{},{},{},Cycle{0}};},
  [&](const auto&kind,const Event&,auto,auto,auto,auto,const auto&phase){if(kind=="store")mapped=bool(phase);return Result{0,0,0};});
 decoder.observe_command(0,0,2,(0x3f800000ull<<32)|256);
 decoder.observe_command(4,3,0x81000000,(3ull<<48)|(std::uint64_t(columns)<<32)|0x80000000u|(std::uint64_t(full)<<29));
 assert(!mapped&&decoder.unknown_timing().count("unsupported_masked_or_multitransaction_accumulator_readout"));
}
int main(){for(unsigned n:{17u,19u,32u,48u,64u}){run(n);run(n,7,true);}run(64,7,true,true,16);run(32,0,false,false);unsupported(65,false);unsupported(32,true);}
