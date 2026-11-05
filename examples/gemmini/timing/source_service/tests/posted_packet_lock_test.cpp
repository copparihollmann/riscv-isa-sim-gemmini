#include "registered_transport.hpp"
#include <cassert>
#include <vector>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;
// An aggregate private-probe completion and a beat-driven cache response
// share the same registered client D transport. B's first beat must not enter
// ahead of A's delayed final beat and hold that queue waiting for A's merger.
void mixed(bool lock,bool omit_last=false){
 Q q({4096,4096,10000});PostedRegisteredTransport d(q,{{1,true},{1,true}});PostedPacketLock messages(q);
 auto a=messages.acquire(0),b=messages.acquire(1);
 auto merged=*q.token();std::vector<unsigned>seen;
 auto offer=[&](unsigned packet,unsigned beat,merlin_timing::Cycle at){
   auto send=[&,packet,beat](auto&,auto time){
     d.push([&,packet,beat](auto when,auto consumed){
       std::vector<Q::Token>deps;if(packet)deps.push_back(merged);
       q.post(when,std::move(deps),[&,packet,beat,consumed](auto&,auto at){
         seen.push_back(packet*10+beat);q.complete(consumed);
         if(!packet&&beat==1){
           q.complete(a.released);
           // Local output publication is independent of the last client
           // D.fire. A new message must retain the real merger obligation.
           q.post(at+3,{},[merged](auto&q,auto){q.complete(merged);});
         }else if(packet)q.complete(b.released);
       });
     },time);
   };
   q.post(at,lock?std::vector<Q::Token>{packet?b.admitted:a.admitted}:std::vector<Q::Token>{},send);
 };
 offer(0,0,0);offer(1,0,1);if(!omit_last)offer(0,1,12);
 while(q.step(true)){}
 assert(!q.progress().failed);
 if(lock&&!omit_last){
   assert(seen==std::vector<unsigned>({0,1,10}));assert(q.completed(a.released)&&q.completed(b.released));
   assert(q.progress().complete&&!d.busy());
 }else{
   assert(seen==std::vector<unsigned>({0}));assert(!q.completed(a.released)&&!q.completed(b.released));
   assert(!q.progress().complete); // no invented completion or suppressed guard
 }
 for(auto peak:d.peaks())assert(peak<=1);
}
void no_added_stage(){
 Q q({4096,4096,10000});PostedPacketLock lock(q);PostedRegisteredTransport transport(q,{{1,true}});
 const auto p=lock.acquire(0);std::vector<merlin_timing::Cycle>times;
 for(unsigned beat=0;beat<2;++beat)q.post(beat,{p.admitted},[&,beat](auto&,auto at){
   transport.push([&,beat](auto time,auto consumed){times.push_back(time);q.complete(consumed);
     if(beat==1)q.complete(p.released);},at);
 });
 while(q.step(true)){}
 assert(!q.progress().failed&&q.progress().complete);
 assert(times==std::vector<merlin_timing::Cycle>({1,2})); // only original Queue1 visibility
}
int main(){mixed(false);mixed(true);mixed(true,true);no_added_stage();}
