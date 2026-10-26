#include "memory.hpp"
#include <cassert>
#include <map>
#include <iostream>
using namespace spike_timing;
void parent_phase_checks(const Model&base){
 auto model=base;
 // Synthetic set count, same selected8-way source replacement law. Every
 // address maps to one set; this needs only115 original scalar stores.
 model.document.put("memory.caches.l1d.ways",8);model.document.put("memory.caches.l2.ways",8);
 model.document.put("memory.caches.l2.replacement.schema","merlin.read_stepped_lfsr_replacement.v1");
 model.document.put("memory.caches.l2.replacement.width",16);model.document.put("memory.caches.l2.replacement.feedback_mask",46080);
 model.document.put("memory.caches.l2.replacement.seed",1);model.document.put("memory.caches.l2.replacement.selection_bits",10);
 model.document.put("memory.caches.l2.replacement.source_receipt_sha256",std::string(64,'0'));
 merlin_timing::Engine engine(model.max_values,model.resources);std::uint64_t next=0;unsigned prefixes=0,reused=0;
 MemorySystem memory(model,engine,[&](std::size_t n){auto v=next;next+=n;return v;},[](auto,auto){},[](auto why){std::cerr<<why<<"\n";assert(false);});
 for(unsigned i=0;i<115;++i){
  const auto address=0x89000000ULL+i*65536ULL;assert(memory.access({{address,8,true}},"cpu_data").latency);
  ReadAllocationEffectsV7 batch;if(memory.take_read_allocations(batch)){
   assert(batch.snapshot_revision==5&&batch.unavailable.empty());
   for(const auto&phase:batch.parent_writebacks){++prefixes;assert(phase.bytes==64&&phase.address%64==0&&phase.before_child==0&&!phase.writes.empty());
    for(auto value:phase.writes){assert(std::find(batch.source_request.writes.begin(),batch.source_request.writes.end(),value)==batch.source_request.writes.end());
     for(const auto&child:batch.allocations)if(std::find(child.source_request.writes.begin(),child.source_request.writes.end(),value)!=child.source_request.writes.end())++reused;
    }
   }
   for(const auto&child:batch.allocations){
    for(auto value:child.source_request.writes)assert(std::find(batch.source_request.writes.begin(),batch.source_request.writes.end(),value)==batch.source_request.writes.end());
    if(child.victim)assert(memory.victim_client_released(*child.victim,(i+1)*1000));
   }
  }
  memory.cpu_data_completed((i+1)*1000,false);memory.source_full_fence((i+1)*1000);
 }
 assert(prefixes&&reused==1);
 std::cout<<"original dirty private writeback/child LLC-slot reuse retains separate prefix and late publications PASS\n";
}
void source_read_checks(const Model&model){
 merlin_timing::Engine engine(model.max_values,model.resources);std::uint64_t next=0;
 std::map<std::string,std::uint64_t>f;
 MemorySystem m(model,engine,[&](std::size_t n){auto v=next;next+=n;return v;},[&](const auto&k,auto n){f[k]+=n;},[](auto why){std::cerr<<why<<"\n";assert(false);});
 const std::uint64_t a=0x89000000;ReadAllocationEffectsV7 r;
 const auto before_preview=f;const auto preview_values=next;
 assert(m.cpu_read_admission_lines({{a,8,true}},"cpu_data")==std::vector<std::uint64_t>{a});
 assert(m.cpu_read_admission_lines({{a+60,8,false}},"cpu_fetch")==std::vector<std::uint64_t>({a,a+64}));
 assert(m.cpu_read_admission_lines({{a,4,false},{a+2,2,false}},"cpu_fetch")==std::vector<std::uint64_t>{a});
 assert(!m.cpu_read_admission_lines({{a,32,false}},"cpu_data"));
 assert(!m.cpu_read_admission_lines({{a,4,false},{a+128,4,false}},"cpu_data"));
 assert(f==before_preview&&next==preview_values); // no tags, replacement RNG, traffic or value IDs are consumed
 const auto first=m.access({{a,64,true}},"cpu_data");
 assert(first.latency==2&&m.take_read_allocations(r)&&r.allocations.size()==1);
 assert(!r.allocations[0].device_resident_no_probe&&r.allocations[0].inner_acquire&&r.allocations[0].inner_address==a&&r.allocations[0].inner_bytes==64);
 assert(!r.allocations[0].victim&&r.allocations[0].miss.acquire_block&&r.response_stages==2);
 assert(!m.take_read_allocations(r));m.cpu_data_completed(30,false);
 assert(m.cpu_read_admission_lines({{a,8,false}},"cpu_data")->empty());
 assert(m.access({{a+1024,16,false}},"device").latency==0&&m.take_read_allocations(r));
 assert(!r.allocations[0].inner_acquire&&r.allocations[0].inner_address==a+1024&&r.allocations[0].inner_bytes==16);
 const auto misses=f["modeled.cache.l2.misses"],bytes=f["modeled.dram_request_bytes"];
 const auto effects=m.access({{a+2048,32,false}},"device");
 assert(effects.latency==0&&m.take_read_allocations(r)&&r.allocations.size()==1);
 const auto&v=r.allocations[0];assert(v.victim&&v.victim->line==a/64&&v.victim->private_dirty&&!v.victim->llc_dirty);
 assert(v.victim->client_ready==38&&v.miss.dirty_eviction&&!v.miss.release_writes.empty());
 assert(v.miss.release_latency>0&&v.miss.fill_latency>0&&r.source_request.demands.empty());
 assert(f["modeled.cache.l2.misses"]==misses+1&&f["modeled.dram_request_bytes"]==bytes+128);
 for(auto id:v.miss.release_writes)assert(std::find(r.source_request.writes.begin(),r.source_request.writes.end(),id)==r.source_request.writes.end());
 assert(m.private_client_busy()&&m.victim_client_released(*v.victim,60)&&!m.private_client_busy());
 const auto private_misses=f["modeled.cache.l1d.misses"];
 assert(m.access({{a,1,false}},"cpu_data").latency);
 assert(f["modeled.cache.l1d.misses"]==private_misses+1); // original victim was genuinely invalidated
 // An instruction miss whose actual lower LLC line is resident must keep
 // the native L1 miss and source-owned lower lookup exactly once. The old
 // optional fetch-refill approximation must not suppress the latter price.
 assert(m.access({{a+2048,2,false}},"cpu_fetch").latency==2&&m.take_read_allocations(r));
 assert(r.allocations.size()==1&&r.allocations[0].resident&&!r.allocations[0].inner_acquire&&!r.allocations[0].device_resident_no_probe);
 assert(r.allocations[0].inner_address==a+2048&&r.allocations[0].inner_bytes==64);
 assert(f["modeled.fetch_refill.applied"]==0);
 // Two distinct lower allocations from one architectural request retain
 // independent lookup/dependency custody; the parent is not cloned twice.
 const auto multi=m.access({{a+4096,128,false}},"device");
 assert(multi.latency==0&&m.take_read_allocations(r)&&r.snapshot_revision==5&&r.allocations.size()==2);
 assert(r.source_request.latency==0&&r.source_request.writes.empty());
 for(unsigned i=0;i<2;++i){const auto&child=r.allocations[i];
   assert(child.inner_address==a+4096+i*64&&child.inner_bytes==64);
   assert(child.source_request.latency==2&&child.source_request.writes.size()==1);
   assert(std::find(child.source_request.reads.begin(),child.source_request.reads.end(),r.allocations[1-i].source_request.writes[0])==child.source_request.reads.end());
 }
 assert(r.allocations[0].source_request.writes!=r.allocations[1].source_request.writes);
 // A resident no-probe read inside a typed write epoch now has a real source
 // actor. A later target-coherence probe still fails that exact old guard.
 merlin_timing::Engine e(model.max_values,model.resources);std::uint64_t n=0;std::vector<std::string>unknown;
 MemorySystem resident(model,e,[&](std::size_t count){auto v=n;n+=count;return v;},[](auto,auto){},[&](auto why){unknown.push_back(why);});
 assert(resident.access({{a,64,false}},"device").latency&&resident.take_read_allocations(r));
 FullWritePacketV3 p;p.address=a;p.transaction_bytes=64;p.beat_bytes=16;WriteTransactionEffectsV6 output;
 assert(resident.write_packet(p,output));
 assert(resident.access({{a+16,16,false}},"device").latency&&resident.take_read_allocations(r));
 assert(r.allocations.size()==1&&r.allocations[0].resident&&r.allocations[0].device_resident_no_probe&&!r.allocations[0].victim&&r.allocations[0].miss.fill_latency==0&&unknown.empty());
 assert(resident.access({{a,1,false}},"cpu_data").latency&&resident.take_read_allocations(r));
 resident.access({{a,16,false}},"device");
 assert(std::find(unknown.begin(),unknown.end(),"typed masked-write source epoch intersects unsupported external shared-cache service before full fence")!=unknown.end());
}
void masked_packet_checks(const Model&model){
 merlin_timing::Engine engine(model.max_values,model.resources);std::uint64_t next=0;std::map<std::string,std::uint64_t>f;
 MemorySystem memory(model,engine,[&](std::size_t n){auto v=next;next+=n;return v;},[&](const auto&k,auto n){f[k]+=n;},[](auto x){std::cerr<<x<<"\n";assert(false);});
 MaskedWritePacketV8 p;p.address=0x89000000;p.transaction_bytes=64;p.masks={0,0xff00,0xffff,0x1f};
 MaskedWriteEffectsV9 observed;assert(memory.write_packet(p,observed)&&!observed.resident_dirty_no_probe);
 WriteTransactionEffectsV6 out=std::move(observed.original);assert(out.miss&&out.miss->acquire_block&&out.resident.base.sram_read_required);
 assert(f["device.requested_write_bytes"]==29&&f["modeled.dram_request_bytes"]==64&&f["modeled.typed_write.client_transaction_bytes"]==64);
 // Same packet owner interface can follow with full and partial requests.
 p.masks={0xffff,0xffff,0xffff,0xffff};assert(memory.write_packet(p,observed)&&observed.resident_dirty_no_probe);
 out=std::move(observed.original);assert(!out.miss&&!out.resident.base.sram_read_required);
 assert(f["device.requested_write_bytes"]==93&&f["modeled.dram_request_bytes"]==64);
 p.address+=64;p.transaction_bytes=32;p.masks={0x8000,0x7fff};
 assert(memory.write_packet(p,out)&&out.miss&&out.miss->acquire_block);
 assert(f["device.requested_write_bytes"]==109&&f["modeled.dram_request_bytes"]==128&&f["modeled.typed_write.client_transaction_bytes"]==160);
 const auto before=f;p.masks={0xff00,0x7fff};p.masks[0]|=1;
 assert(!memory.write_packet(p,out)&&f==before); // reject before any tag/traffic mutation
 // A clean resident hit still needs a Directory dirty-bit update. It must
 // not inherit the early-retirement premise from mere absence of a miss.
 merlin_timing::Engine clean_engine(model.max_values,model.resources);std::uint64_t clean_next=0;
 MemorySystem clean(model,clean_engine,[&](std::size_t n){auto v=clean_next;clean_next+=n;return v;},[](const auto&,auto){},[](auto){assert(false);});
 p.address=0x8a000000;p.transaction_bytes=64;p.masks={0xffff,0xffff,0xffff,0xffff};
 assert(clean.access({{p.address,64,false}},"device").latency);
 assert(clean.write_packet(p,observed)&&!observed.original.miss&&!observed.resident_dirty_no_probe);
 assert(clean.write_packet(p,observed)&&observed.resident_dirty_no_probe);

}
int main(int argc,char**argv){
 assert(argc==2);Model model(argv[1]);
 if(model.number("target.scheduling.source_masked_packet_readout")==std::optional<double>{1}){masked_packet_checks(model);return 0;}
 if(model.document.get_child_optional("memory.source_read_allocations")){source_read_checks(model);parent_phase_checks(model);return 0;}merlin_timing::Engine engine(model.max_values,model.resources);
 std::uint64_t next=0;std::map<std::string,std::uint64_t>features;unsigned unknown=0;
 MemorySystem memory(model,engine,[&](std::size_t n){auto v=next;next+=n;return v;},[&](const auto&name,auto n){features[name]+=n;},[&](const auto&){++unknown;});
 WriteTransactionV1 request;request.address=0x81000000;request.beat_bytes=16;request.transaction_bytes=16;request.mask=8;
 WriteTransactionEffectsV1 effects;
 assert(!memory.write_transaction(request,effects)&&effects.unavailable=="typed write requires resident source-ready cache line");
 assert(memory.access({{request.address,64,false}},"device").latency);
 assert(memory.write_transaction(request,effects)&&effects.source_request.latency==2&&effects.sram_read_required);
 assert(features["device.requested_write_bytes"]==1&&features["modeled.typed_write.client_transaction_bytes"]==16&&features["modeled.typed_write.useful_bytes"]==1);
 memory.source_full_fence(0);
 // A private-cache hit needs a different coherent admission law. Refuse it
 // before invalidating the CPU cache or producing an ordinary write effect.
 assert(memory.access({{request.address,1,false}},"cpu_data").latency);
 assert(!memory.write_transaction(request,effects)&&effects.unavailable=="typed write private-cache probe service not source closed");
 assert(features["device.requested_write_bytes"]==1&&!unknown);
 if(model.document.get_child_optional("memory.device_write_request_pipeline.single_private_probe")){
   WriteTransactionEffectsV2 extended;
   assert(memory.write_transaction(request,extended)&&extended.probe&&!extended.probe->dirty&&extended.base.source_request.latency==2);
   assert(extended.probe->lookup==2&&extended.probe->beat_bytes==16);
   memory.source_full_fence(0);
   assert(memory.access({{request.address,1,true}},"cpu_data").latency);
   assert(memory.write_transaction(request,extended)&&extended.probe&&extended.probe->dirty);
   memory.source_full_fence(0,false);memory.source_report();assert(unknown==1);
   memory.source_full_fence(0);
   memory.source_report();assert(unknown==1);
 }
 request.mask=5;assert(!memory.write_transaction(request,effects));
 memory.source_full_fence(0);
 FullWritePacketV3 packet;packet.address=0x81000100;packet.transaction_bytes=64;packet.beat_bytes=16;
 assert(full_write_packet_valid(packet));
 assert(memory.access({{packet.address,64,false}},"device").latency);
 const auto before=features["device.requested_write_bytes"];
 WriteTransactionEffectsV2 whole;
 assert(memory.write_packet(packet,whole)&&whole.base.source_request.latency==2&&!whole.base.sram_read_required&&!whole.probe);
 assert(features["device.requested_write_bytes"]==before+64); // one original packet classification
 const auto owned_writes=whole.base.source_request.writes;
 for(auto value:owned_writes)engine.publish(value,std::nullopt);
 // Earlier admitted packet ownership is retained as a real dependency; this
 // does not manufacture a ready cache line or complete its publication.
 assert(memory.write_packet(packet,whole)&&whole.base.source_request.latency==2);
 for(auto value:owned_writes)assert(!engine.ready(value));
 request.mask=0xffff;assert(!memory.write_transaction(request,whole)&&whole.base.unavailable=="mixed typed SourceD routes require actual full fence");
 memory.source_full_fence(0);
 packet.address+=16;assert(!full_write_packet_valid(packet)&&!memory.write_packet(packet,whole));
 packet.address=0x81000200;
 auto unrelated=memory.access({{packet.address,64,true}},"device");
 for(auto value:unrelated.writes)engine.publish(value,std::nullopt);
 assert(!memory.write_packet(packet,whole)&&whole.base.unavailable=="typed write cache line publication is pending");
 if(model.document.get_child_optional("memory.device_write_miss_pipeline")){
   memory.source_full_fence(0);
   packet.address=0x82000000;packet.transaction_bytes=64;
   const auto reads=features["modeled.dram_request_bytes"];
   const auto misses=features["modeled.cache.l2.misses"];
   assert(!memory.write_packet(packet,whole)); // old ABI cannot grant cold law
   assert(features["modeled.cache.l2.misses"]==misses);
   WriteTransactionEffectsV4 cold;
   assert(memory.write_packet(packet,cold)&&cold.miss&&!cold.miss->acquire_block);
   assert(cold.resident.base.source_request.latency==2&&cold.miss->fill_latency==0&&cold.miss->fill_bus==0);
   assert(features["modeled.dram_request_bytes"]==reads); // no invented data Get
   memory.source_full_fence(0);
   request.address=0x82000040;request.mask=1;request.accepted=0;
   assert(memory.write_transaction(request,cold)&&cold.miss&&cold.miss->acquire_block);
   assert(cold.resident.base.source_request.latency==2&&cold.miss->fill_latency>0);
   assert(features["modeled.dram_request_bytes"]==reads+64);
   memory.source_full_fence(0);
   // A Get/Hint-only instruction cache can retain the evicted line without
   // being an inclusive coherent client. The same D$ hit still needs rprobe.
   // Both experiments have identical tags/geometry; only the source-declared
   // topology role changes admission. No extra Directory step on refusal.
   for(const auto*cpu:{"cpu_fetch","cpu_data"}){
     merlin_timing::Engine e(model.max_values,model.resources);std::uint64_t n=0;
     MemorySystem other(model,e,[&](std::size_t count){auto v=n;n+=count;return v;},[](auto,auto){},[](auto){assert(false);});
     const std::uint64_t base=0x86000000;
     assert(other.access({{base,64,false}},cpu).latency);
     assert(other.access({{base+1024,64,false}},"device").latency);
     FullWritePacketV3 p;p.address=base+2048;p.transaction_bytes=64;p.beat_bytes=16;
     WriteTransactionEffectsV4 result;
     const bool admitted=other.write_packet(p,result);
     const bool noncoherent=std::string(cpu)=="cpu_fetch"&&model.document.get_child_optional("memory.caches.l1i.coherence_role");
     assert(admitted==noncoherent);
     if(admitted)assert(result.miss&&result.miss->evicted_line==base/64&&!result.resident.probe);
     else assert(result.resident.base.unavailable=="cold write allocation requires unsupported private-client victim shoot-down");
   }
   if(model.document.get_child_optional("memory.device_write_miss_pipeline.private_victim"))for(bool atomic:{false,true})for(bool dirty:{false,true}){
     merlin_timing::Engine e(model.max_values,model.resources);std::uint64_t n=0;
     MemorySystem other(model,e,[&](std::size_t count){auto v=n;n+=count;return v;},[](auto,auto){},[](auto){assert(false);});
     const std::uint64_t base=0x87000000;
     assert(other.access({{base,64,dirty}},"cpu_data").latency);other.cpu_data_completed(123,atomic);
     assert(other.access({{base+1024,64,false}},"device").latency);
     FullWritePacketV3 p;p.address=base+2048;p.transaction_bytes=64;p.beat_bytes=16;
     WriteTransactionEffectsV6 result;
     if(atomic){assert(!other.write_packet(p,result)&&!result.victim&&!other.private_client_busy());continue;}
     assert(other.write_packet(p,result)&&result.victim&&result.miss);
     assert(result.victim->line==base/64&&result.victim->client_ready==131&&result.victim->private_dirty==dirty);
     assert(!result.victim->llc_dirty&&result.miss->dirty_eviction==dirty);
     assert(result.miss->release_writes.empty()!=dirty);
     assert(other.private_client_busy());assert(!other.victim_client_released(*result.victim,130));
     assert(other.victim_client_released(*result.victim,150)&&!other.private_client_busy());
     assert(!other.victim_client_released(*result.victim,150));
   }
   // A clean replacement is explicitly recorded, not treated as invalid.
   for(auto address:{0x83000080ull,0x83000480ull})assert(memory.access({{address,64,false}},"device").latency);
   packet.address=0x83000880;
   assert(memory.write_packet(packet,cold)&&cold.miss&&cold.miss->evicted_line&&!cold.miss->dirty_eviction);
   memory.source_full_fence(0);
   // Dirty-victim support is not yet granted. Admission must refuse before
   // stepping allocation, mutating tags or charging the lower memory path.
   packet.address=0x840000c0;assert(memory.write_packet(packet,cold));memory.source_full_fence(0);
   packet.address+=1024;assert(memory.write_packet(packet,cold));memory.source_full_fence(0);
   packet.address+=1024;const auto writes=features["device.requested_write_bytes"];
   const auto dirty_misses=features["modeled.cache.l2.misses"];
   assert(!memory.write_packet(packet,cold)&&cold.resident.base.unavailable=="cold write dirty victim outer-A/ReleaseAck timeline unsupported");
   assert(features["device.requested_write_bytes"]==writes&&features["modeled.cache.l2.misses"]==dirty_misses);
   if(model.document.get_child_optional("memory.device_write_miss_pipeline.dirty_victim")){
     WriteTransactionEffectsV5 dirty;const auto lower=features["modeled.dram_request_bytes"];
     assert(memory.write_packet(packet,dirty)&&dirty.miss&&dirty.miss->dirty_eviction&&dirty.miss->evicted_line);
     assert(dirty.resident.base.source_request.latency==2&&!dirty.miss->acquire_block);
     assert(dirty.miss->release_latency>0&&dirty.miss->release_bus>0&&!dirty.miss->release_writes.empty());
     assert(dirty.miss->fill_latency==0&&features["modeled.dram_request_bytes"]==lower+64);
     for(auto v:dirty.miss->release_writes)assert(std::find(dirty.resident.base.source_request.writes.begin(),dirty.resident.base.source_request.writes.end(),v)==dirty.resident.base.source_request.writes.end());
   }
 }
}
