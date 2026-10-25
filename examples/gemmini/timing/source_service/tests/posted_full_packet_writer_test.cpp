#include "posted_full_packet_writer.hpp"
#include <timing/write_transaction.hpp>
#include <cassert>
using namespace gemmini_annotated_spike;
int main(){
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
 Q q({65536,65536,1000000});PostedRegisteredTransport a(q,{{2,false},{2,false}}),d(q,{{2,false},{2,false}});
 PostedFullPacketWriter writer(q,a,d,40);PostedFullPacketSourceD source(q);
 unsigned requests=0,publications=0;std::vector<Cycle>acks,last_publish,request_times;std::optional<Cycle>first_final_publish;std::vector<Q::Token>done;
 std::function<void(unsigned,Cycle)>issue;
 issue=[&](unsigned i,Cycle at){
   auto complete=*q.token();done.push_back(complete);auto last=std::make_shared<Cycle>(0);
   auto entered=writer.push(4,[&,last,i](Cycle t,auto ready,auto accepted,const auto&data,const auto&popped){
     ++requests;request_times.push_back(t);
     q.post(t+2,{},[&,last,i,ready,accepted,data,popped](auto&,auto now){
       source.push(data,popped,ready,accepted,[&,last,i](auto beat,Cycle time,auto stored){
         if(!i&&beat==3)first_final_publish=time;
         ++publications;*last=time;q.post(time+2,{},[stored](auto&q,auto){q.complete(stored);},Q::Kind::local_publish);
       },now);
     },Q::Kind::memory_accept);
   },at,complete);
   q.post(at,{complete},[&,last](auto&,auto t){acks.push_back(t);last_publish.push_back(*last);},Q::Kind::completion);
   if(i+1<20)q.post(at,{entered},[&,i](auto&,auto t){issue(i+1,t+1);},Q::Kind::source_arrival);
 };
 issue(0,0);while(q.step(true)){}
 assert(!q.progress().failed&&!writer.busy()&&!source.busy());
 assert(requests==20&&publications==80&&acks.size()==20&&writer.peak_transactions()<=16&&writer.peak_payload_beats()<=40);
 for(auto token:done)assert(q.completed(token));
 // First-beat D-ACK is not a promise that the last S4 write has published.
 assert(first_final_publish&&acks.front()<*first_final_publish);
 assert(request_times.at(1)-request_times.at(0)==4); // last A permits same-edge next-row capture
 // Withhold a later A beat: SourceD must neither invent its payload nor
 // manufacture a second D response for that internal beat.
 Q late({4096,4096,100000});PostedFullPacketSourceD held(late);std::vector<Q::Token>data,popped;
 for(unsigned i=0;i<4;++i){data.push_back(*late.token());popped.push_back(*late.token());}
 auto ready=*late.token(),accepted=*late.token();std::vector<Cycle>stored;
 held.push(data,popped,ready,accepted,[&](auto,Cycle t,auto consumed){stored.push_back(t);late.complete(consumed);},0);
 late.post(0,{},[&](auto&q,auto){q.complete(data[0]);q.complete(data[1]);q.complete(data[2]);},Q::Kind::response_beat);
 late.post(0,{ready},[accepted](auto&q,auto){q.complete(accepted);},Q::Kind::response_beat);
 late.post(30,{},[&](auto&q,auto){q.complete(data[3]);},Q::Kind::response_beat);
 while(late.step(true)){}assert(!late.progress().failed&&!held.busy()&&stored.size()==4);
 assert(late.completed(ready)==2&&stored.back()>=32&&late.completed(popped.back())==30);
 // Two original32B packets share ONE captured64B row. The second packet
 // follows the first's two A beats, without inventing another io.req cycle.
 Q row({4096,4096,100000});PostedRegisteredTransport ra(row,{{2,false},{2,false}}),rd(row,{{2,false},{2,false}});
 PostedFullPacketWriter split(row,ra,rd,40);std::vector<Cycle>starts;std::vector<Q::Token>acks2{*row.token(),*row.token()};
 PostedFullPacketWriter::Memory memory=[&](Cycle t,auto ready,auto,const auto&data,const auto&popped){
   starts.push_back(t);row.post(t+10,{},[ready](auto&q,auto){q.complete(ready);},Q::Kind::response_beat);
   for(std::size_t i=0;i<data.size();++i)row.post(t,{data[i]},[pop=popped[i]](auto&q,auto){q.complete(pop);},Q::Kind::operand_consume);
 };
 auto captured=split.push_row({2,2},{memory,memory},0,acks2);
 while(row.step(true)){}assert(!row.progress().failed&&!split.busy()&&row.completed(captured)==0);
 assert(starts==std::vector<Cycle>({6,8}));for(auto token:acks2)assert(row.completed(token));
 spike_timing::FullWritePacketV3 packet;packet.address=0x81000000;packet.transaction_bytes=64;packet.beat_bytes=16;
 assert(spike_timing::full_write_packet_valid(packet));packet.transaction_bytes=48;assert(!spike_timing::full_write_packet_valid(packet));
}
