#include "posted_cold_write.hpp"
#include <cassert>
#include <tuple>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
void path(bool block,bool clean){
 Q q({65536,65536,1000000});std::vector<std::tuple<Cycle,std::uint64_t,bool>>ports;unsigned lowers=0;
 PostedColdWrite actor(q,[&](auto address,PostedColdWrite::Port port,Cycle t,auto ready){ports.emplace_back(t,address,port==PostedColdWrite::Port::sinkd_noop);q.complete(ready);},
 [&](Cycle latency,Cycle bus,Cycle t,auto ready){++lowers;assert(latency==16&&bus==4);q.post(t+latency-bus,{},[ready](auto&q,auto){q.complete(ready);});});
 auto pub=*q.token();std::optional<Cycle>admitted,ready;
 spike_timing::WriteMissV4 m;m.line=16;m.set=16;m.acquire_block=block;m.fill_latency=16;m.fill_bus=4;
 if(clean)m.evicted_line=32;
 actor.admit(m.set,pub,[&](Cycle t){admitted=t;actor.push(m,[&](Cycle t){ready=t;q.post(t+3,{},[pub](auto&q,auto){q.complete(pub);});},t);},0);
 while(q.step(true)){}assert(!q.progress().failed&&admitted==0&&ready&&!actor.busy());
 assert(lowers==unsigned(block));assert(ports.size()==(block?8u:1u)+(clean?1u:0u));
 if(!block&&!clean)assert(*ready==4&&std::get<2>(ports[0]));
 if(block&&!clean){assert(*ready==22);for(unsigned b=0;b<8;++b){assert(std::get<1>(ports[b])==m.line*64+b*8);assert(!std::get<2>(ports[b]));}}
 if(clean){bool found=false;for(const auto&p:ports)found|=std::get<1>(p)==32*64&&std::get<2>(p);assert(found);}
}
void finite(){
 Q q({65536,65536,1000000});PostedColdWrite actor(q,[&](auto,PostedColdWrite::Port,Cycle,auto ready){q.complete(ready);},[&](auto,auto,auto,auto){assert(false);});
 std::vector<Q::Token>pub;std::vector<Cycle>accepted;
 for(unsigned i=0;i<12;++i){pub.push_back(*q.token());actor.admit(i,pub.back(),[&](Cycle t){accepted.push_back(t);},0);}
 q.post(30,{},[&](auto&q,auto){q.complete(pub[0]);q.complete(pub[1]);});
 while(q.step(true)){}assert(!q.progress().failed&&accepted.size()==12&&actor.peak_mshrs()==10);
 for(unsigned i=0;i<10;++i)assert(accepted[i]==i);
 assert(accepted[10]==31&&accepted[11]==32);
}
void dirty(bool block){
 Q q({65536,65536,1000000});
 std::vector<std::tuple<Cycle,std::uint64_t,PostedColdWrite::Port>> ports;
 std::vector<Cycle> outer;std::optional<Cycle>new_ready,old_ack,lower_start,first_s4;
 PostedColdWrite actor(q,[&](auto a,auto p,Cycle t,auto done){
   ports.emplace_back(t,a,p);q.complete(done);
 },[&](Cycle latency,Cycle bus,Cycle t,auto done){
   assert(block&&latency==16&&bus==4);q.post(t+latency-bus,{},[done](auto&q,auto){q.complete(done);});
 },[&](Cycle t,auto done){outer.push_back(t);q.complete(done);});
 auto pub=*q.token();spike_timing::WriteMissV5 m;
 m.line=16;m.set=16;m.evicted_line=1040;m.dirty_eviction=true;m.acquire_block=block;
 m.release_latency=40;m.release_bus=8;m.release_writes={9000};
 if(block){m.fill_latency=16;m.fill_bus=4;}
 actor.admit(m.set,pub,[&](Cycle at){actor.push(m,[&](Cycle t){new_ready=t;q.complete(pub);},
 [&](Cycle t){old_ack=t;},[&](Cycle latency,Cycle bus,Cycle t,auto done){
   assert(latency==40&&bus==8);lower_start=t;
   q.post(t+latency-bus,{},[done](auto&q,auto){q.complete(done);});
 },at);
 auto reads=actor.write_dependencies(m.line*64,0xffff);assert(reads.size()==2);
 q.post(at,reads,[&](auto&,auto t){first_s4=t;});
 auto fill=actor.write_dependencies(m.line*64+8,0xff);assert(fill.size()==1&&fill[0].id==reads[1].id);
 },0);
 while(q.step(true)){}
 assert(!q.progress().failed&&!actor.busy()&&new_ready&&old_ack&&lower_start);
 // ReleaseData reads the EVICTED line once. The eight accepted outer-A
 // data beats precede the independent old-DRAM publication/ReleaseAck.
 unsigned reads=0,noop=0,data=0;
 for(const auto&p:ports){const auto kind=std::get<2>(p);if(kind==PostedColdWrite::Port::sourcec_read){
   assert(std::get<1>(p)==*m.evicted_line*64+reads*8);++reads;
 }else if(kind==PostedColdWrite::Port::sinkd_noop)++noop;else ++data;}
 assert(reads==8&&noop==(block?1u:2u)&&data==(block?8u:0u));
 assert(outer.size()==(block?16u:8u));
 for(unsigned i=1;i<8;++i)assert(outer[i]==outer[i-1]+1);
 assert(*lower_start==outer[7]&&*old_ack>*lower_start&&*new_ready<*old_ack);
 assert(first_s4==2); // only the two matching old8B reads, not all8 or ReleaseAck
}
void software_custody(){
 Q q({65536,65536,1000000});PostedColdWrite actor(q,[&](auto,auto,auto,auto accepted){q.complete(accepted);},[](auto,auto,auto,auto){assert(false);});
 unsigned admitted=0;for(unsigned i=0;i<34;++i){auto pub=*q.token();actor.admit(i,pub,[&,pub](Cycle t){++admitted;q.post(t+100,{},[pub](auto&q,auto){q.complete(pub);});},0);}
 while(q.step(true)){}assert(!q.progress().failed&&!actor.busy()&&admitted==34&&actor.peak_mshrs()==10);
}
void native_arrival(){
 Q q({128,128,1000});
 PostedColdWrite actor(q,[](auto,auto,auto,auto){assert(false);},[](auto,auto,auto,auto){assert(false);});
 auto pub=*q.token(),accepted=*q.token();unsigned calls=0;
 actor.admit(1,pub,[&](Cycle t){++calls;assert(t==7);assert(q.complete(accepted));q.complete(pub);},7);
 assert(calls==0&&!q.completed(accepted));
 assert(q.advance(7,true)&&calls==0); // no eager arrival or callback
 assert(q.advance(8,true)&&calls==1&&q.completed(accepted)==7);
 while(q.step(true)){}
 assert(!q.progress().failed&&!actor.busy()&&actor.peak_mshrs()==1);
}
void wormhole(bool zero_offset){
 Q q({65536,65536,1000000});std::vector<Cycle>stored;std::optional<Cycle>ready;
 PostedColdWrite actor(q,[&](auto,auto,Cycle t,auto accepted){q.complete(accepted);stored.push_back(t);},
   [&](Cycle latency,Cycle bus,Cycle t,auto response){q.post(t+latency-bus,{},[response](auto&q,auto){q.complete(response);});});
 auto pub=*q.token();spike_timing::WriteMissV5 law;law.line=16;law.set=16;law.acquire_block=true;law.fill_latency=16;law.fill_bus=4;
 unsigned beats=0;actor.admit(law.set,pub,[&](Cycle at){
   actor.push(law,[&](Cycle t){ready=t;q.complete(pub);if(zero_offset)assert(actor.busy());},{},{},at,{},{},
     PostedColdWrite::Fill{zero_offset,[&](std::size_t beat,Cycle t){assert(beat==beats++);assert(stored.back()==t);}});
 },0);
 while(q.step(true)){}assert(!q.progress().failed&&!actor.busy()&&beats==8&&ready);
 if(zero_offset)assert(*ready<stored.back());else assert(*ready==stored.back()+1);
}
int main(){path(false,false);path(true,false);path(false,true);path(true,true);finite();dirty(false);dirty(true);wormhole(false);wormhole(true);software_custody();native_arrival();}
