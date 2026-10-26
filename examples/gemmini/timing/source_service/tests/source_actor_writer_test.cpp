#include "posted_one_beat_writer.hpp"
#include "posted_full_packet_writer.hpp"
#include <timing/source_actor_activity.hpp>
#include <cassert>
using namespace gemmini_annotated_spike;
using A=spike_timing::SourceActorActivity;
using R=spike_timing::SourceActorRoleV1;
struct Observation {std::vector<std::uint64_t>requests,finished;A activity;};
Observation run(bool diagnostic,bool multi){
 using Q=merlin_timing::PostedTimeline;Q q({65536,65536,1000000});
 PostedRegisteredTransport a(q,{{2,false},{2,false}}),d(q,{{2,false},{2,false}});
 PostedOneBeatWriter one(q,a,d);PostedFullPacketWriter full(q,a,d,40);
 Observation out;out.activity.begin(0);
 spike_timing::SourceActorSinkV1 sink;sink.opaque=&out.activity;
 sink.role=[](void*p,R r,std::uint64_t capacity){static_cast<A*>(p)->role(r,capacity);};
 sink.edge=[](void*p,R r,std::uint64_t id,std::uint64_t at,bool begin){static_cast<A*>(p)->edge(r,id,at,begin);};
 if(diagnostic){sink.role(sink.opaque,R::writer_state,1);sink.role(sink.opaque,R::writer_slot,16);one.source_actors(sink);full.source_actors(sink);}
 std::vector<Q::Token>done;
 for(unsigned i=0;i<20;++i){
   const auto finish=*q.token();done.push_back(finish);
   if(multi)full.push(4,[&](auto t,auto response,auto,const auto&data,const auto&popped){
     out.requests.push_back(t);
     for(unsigned n=0;n<data.size();++n)q.post(t,{data[n]},[token=popped[n]](auto&q,auto){q.complete(token);},Q::Kind::completion);
     q.post(t+50,{},[response](auto&q,auto){q.complete(response);},Q::Kind::completion);
   },i*8,finish);
   else one.push([&](auto t,auto response){out.requests.push_back(t);q.post(t+50,{},[response](auto&q,auto){q.complete(response);},Q::Kind::completion);},i*8,finish);
 }
 while(q.step(true)){}
 assert(!q.progress().failed&&!one.busy()&&!full.busy());
 for(auto token:done){assert(q.completed(token));out.finished.push_back(*q.completed(token));}
 out.activity.end(q.now()+1);return out;
}
int main(){
 for(bool multi:{false,true}){
   auto off=run(false,multi),on=run(true,multi);
   assert(off.requests==on.requests&&off.finished==on.finished);
   assert(on.activity.complete());
   const auto&state=on.activity.rows()[std::size_t(R::writer_state)];
   const auto&slots=on.activity.rows()[std::size_t(R::writer_slot)];
   assert(state.active>0&&state.peak==1&&slots.active>state.active&&slots.peak<=16&&slots.starts==20);
 }
}
