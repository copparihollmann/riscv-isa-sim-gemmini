#include "posted_read_allocation.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
void path(unsigned bytes,bool acquire,bool pipeline=false){
 Q q({4096,4096,65536});PostedReadAllocationResponse actor(q,pipeline);
 spike_timing::ReadAllocationV7 r;r.miss.line=0x100;r.inner_address=0x4000;r.inner_bytes=bytes;r.inner_acquire=acquire;
 unsigned accepted=0;std::optional<Cycle>done,input_done;
 assert(actor.push(r,[&](auto address,Cycle at,auto take,auto ready){
   assert(address==r.inner_address+accepted*16&&at==accepted);++accepted;q.complete(take);
   q.post(at+2,{},[ready](auto&q,auto){q.complete(ready);});
 },[&](Cycle t){done=t;},0,[&](Cycle t){input_done=t;}));
 assert(!done&&accepted==0);while(q.step(true)){}
 if(q.progress().failed||done!=bytes/16+1)std::cerr<<"bytes="<<bytes<<" acq="<<acquire<<" done="<<done.value_or(9999)<<" reason="<<q.reason()<<"\n";
 assert(!q.progress().failed&&accepted==bytes/16&&done==bytes/16+1);
 if(pipeline)assert(input_done==bytes/16-1&&*input_done<*done);
}
void invalid(){
 Q q({4096,4096,65536});PostedReadAllocationResponse actor(q);
 spike_timing::ReadAllocationV7 r;r.miss.line=0x100;r.inner_address=0x4030;r.inner_bytes=32;
 assert(!actor.push(r,[](auto,auto,auto,auto){assert(false);},[](auto){assert(false);},0));
 assert(q.progress().failed&&q.summary().peak_pending==0);
}
void pipelined_requests(){
 Q q({4096,4096,65536});PostedReadAllocationResponse actor(q,true);
 spike_timing::ReadAllocationV7 r;r.miss.line=0x100;r.inner_address=0x4000;r.inner_bytes=16;
 std::vector<Cycle>inputs,responses;
 std::function<void(unsigned,Cycle)>post;
 post=[&](unsigned n,Cycle at){assert(actor.push(r,[&,n](auto,Cycle t,auto take,auto ready){
   q.complete(take);q.post(n==0?8:t+2,{},[ready](auto&q,auto){q.complete(ready);});
 },[&](Cycle t){responses.push_back(t);},at,[&,n](Cycle t){inputs.push_back(t);if(n<2)q.post(t+1,{},[&,n](auto&,auto next){post(n+1,next);});}));};
 post(0,0);while(q.step(true)){}
 assert(!q.progress().failed&&inputs.size()==3&&responses.size()==3);
 assert(inputs[0]==0&&inputs[1]==1&&inputs[1]<responses[0]);
 assert(responses[0]==8&&responses[1]==9&&responses[2]==10); // finite pipeline preserves stalled D ordering
}
void sink_backpressure(){
 Q q({4096,4096,65536});PostedReadAllocationResponse actor(q,true);
 spike_timing::ReadAllocationV7 r;r.miss.line=0x100;r.inner_address=0x4000;r.inner_bytes=16;
 std::vector<Cycle>inputs,responses;std::function<void(unsigned,Cycle)>post;
 post=[&](unsigned n,Cycle at){assert(actor.push(r,[&](auto,Cycle t,auto take,auto ready){
   q.complete(take);q.post(t+2,{},[ready](auto&q,auto){q.complete(ready);});
 },[&](Cycle t){responses.push_back(t);},at,[&,n](Cycle t){inputs.push_back(t);if(n<2)q.post(t+1,{},[&,n](auto&,auto next){post(n+1,next);});},
 [&,n](std::size_t beat,Cycle t,auto accepted){assert(beat==0);q.post(n==0?8:t,{},[accepted](auto&q,auto){q.complete(accepted);});}));};
 post(0,0);while(q.step(true)){}
 assert(!q.progress().failed&&inputs.size()==3&&responses.size()==3);
 assert(inputs[0]==0&&inputs[1]==1&&inputs[2]>=8);
 assert(responses[0]==8&&responses[1]>responses[0]&&responses[2]>responses[1]);
}
int main(){path(16,false);path(32,false);path(64,false);path(64,true);path(16,false,true);path(64,false,true);path(64,true,true);pipelined_requests();sink_backpressure();invalid();}
