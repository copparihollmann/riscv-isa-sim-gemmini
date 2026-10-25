#include "posted_read_allocation.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
void path(unsigned bytes,bool acquire){
 Q q({4096,4096,65536});PostedReadAllocationResponse actor(q);
 spike_timing::ReadAllocationV7 r;r.miss.line=0x100;r.inner_address=0x4000;r.inner_bytes=bytes;r.inner_acquire=acquire;
 unsigned accepted=0;std::optional<Cycle>done;
 assert(actor.push(r,[&](auto address,Cycle at,auto take,auto ready){
   assert(address==r.inner_address+accepted*16&&at==accepted);++accepted;q.complete(take);
   q.post(at+2,{},[ready](auto&q,auto){q.complete(ready);});
 },[&](Cycle t){done=t;},0));
 assert(!done&&accepted==0);while(q.step(true)){}
 if(q.progress().failed||done!=bytes/16+1)std::cerr<<"bytes="<<bytes<<" acq="<<acquire<<" done="<<done.value_or(9999)<<" reason="<<q.reason()<<"\n";
 assert(!q.progress().failed&&accepted==bytes/16&&done==bytes/16+1);
}
void invalid(){
 Q q({4096,4096,65536});PostedReadAllocationResponse actor(q);
 spike_timing::ReadAllocationV7 r;r.miss.line=0x100;r.inner_address=0x4030;r.inner_bytes=32;
 assert(!actor.push(r,[](auto,auto,auto,auto){assert(false);},[](auto){assert(false);},0));
 assert(q.progress().failed&&q.summary().peak_pending==0);
}
int main(){path(16,false);path(32,false);path(64,false);path(64,true);invalid();}
