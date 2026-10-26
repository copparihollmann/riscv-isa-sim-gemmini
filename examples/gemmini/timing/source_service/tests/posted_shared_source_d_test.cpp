#include "posted_full_packet_writer.hpp"
#include "posted_read_allocation.hpp"
#include <cassert>
using namespace gemmini_annotated_spike;
int main(){
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
 Q q({8192,8192,100000});auto pipeline=std::make_shared<PostedSourceDPipeline>(q);
 PostedFullPacketSourceD stores(q,pipeline);PostedReadAllocationResponse reads(q,true,pipeline);
 auto payload=*q.token(),popped=*q.token(),ack=*q.token(),accepted=*q.token();
 q.post(0,{},[payload](auto&q,auto){q.complete(payload);});Cycle first_input=99,write_publication=99,read_input=99,read_response=99,second_ack=99;
 auto read_done=*q.token();auto second_ready=*q.token(),second_accepted=*q.token();
 q.post(0,{},[second_accepted](auto&q,auto){q.complete(second_accepted);});
 auto second=[&](Cycle at){
   auto data=*q.token(),pop=*q.token();q.complete(data);
   stores.push({data},{pop},second_ready,second_accepted,[&](auto,Cycle,auto stored){q.complete(stored);},at);
   q.post(at,{second_ready},[&](auto&,auto t){second_ack=t;},Q::Kind::response_beat);
 };
 stores.push({payload},{popped},ack,accepted,[&](auto,Cycle t,auto stored){
   write_publication=t;q.post(40,{},[stored](auto&q,auto){q.complete(stored);},Q::Kind::local_publish);
 },0,{},[&](Cycle t){
   first_input=t;
   spike_timing::ReadAllocationV7 request;request.inner_address=0x80000040;request.inner_bytes=16;request.miss.line=request.inner_address/64;
   reads.push(request,[&](auto,Cycle at,auto accepted,auto ready){
     q.complete(accepted);q.post(at+2,{},[ready](auto&q,auto){q.complete(ready);},Q::Kind::response_beat);
   },[&](Cycle t){read_response=t;q.complete(read_done);},t+1,[&](Cycle t){read_input=t;second(t+1);});
 });
 q.post(20,{},[accepted](auto&q,auto){q.complete(accepted);},Q::Kind::response_beat);
 while(q.step(true)){}
 assert(!q.progress().failed&&!stores.busy());
 assert(q.completed(read_done)&&first_input==0&&read_input<write_publication);
 // S1 can admit a read before the preceding store publishes. It cannot
 // bypass the held store ACK at S3, or a held physical S4 writeback.
 assert(write_publication==21&&read_response==21&&second_ack>=41);
 assert(pipeline->s2.peaks()==std::vector<std::size_t>{1});
 assert(pipeline->s3.peaks()==std::vector<std::size_t>{1});
 assert(pipeline->s4.peaks()==std::vector<std::size_t>{1});
 assert(!pipeline->s2.busy()&&!pipeline->s3.busy()&&!pipeline->s4.busy());
}
