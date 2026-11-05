#include "posted_accumulator.hpp"
#include <cassert>
#include <map>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;
int main(){
 Q q({1024,1024,10000});PostedAccumulator mem(q,2,512);std::map<unsigned,unsigned>edge;
 auto offer=[&](unsigned id,unsigned row,bool write,bool rmw,unsigned at,bool ex=false){
   mem.offer(row,write,rmw,[](auto){return true;},[&,id](auto t){assert(edge.emplace(id,t).second);},at,ex);
 };
 // Independent ports accept an overwrite and unrelated read together.
 offer(0,0,true,false,0);offer(1,1,false,false,0);
 // RMW takes the read port. A normal same-bank read waits, but another bank
 // remains available. Same-row RMW cannot reuse either live pipeline slot.
 offer(2,2,true,true,1);offer(3,3,false,false,1);offer(4,512,false,false,1);
 offer(5,2,true,true,2);offer(6,2,false,false,2);
 while(q.step(true)){}assert(!q.progress().failed);
 assert(edge[0]==0&&edge[1]==0&&edge[2]==1&&edge[4]==1);
 assert(edge[5]==4); // both t2 and t3 still have registered prior writes
 assert(edge[3]==5&&edge[6]==7);
 // Scratchpad mux gives Execute priority over DMA writes on the same bank.
 Q p({128,128,1000});PostedAccumulator priority(p,1,512);std::map<unsigned,unsigned>order;
 priority.offer(0,true,false,[](auto){return true;},[&](auto t){order[0]=t;},0);
 priority.offer(1,true,false,[](auto){return true;},[&](auto t){order[1]=t;},0,true);
 while(p.step(true)){}assert(!p.progress().failed&&order[1]==0&&order[0]==1);
 // ZeroWriter is below BOTH DMA and Execute, independent of offer order.
 Q z({128,128,1000});PostedAccumulator mux(z,1,512);std::map<unsigned,unsigned>zero;
 mux.offer(0,true,false,[](auto){return true;},[&](auto t){zero[0]=t;},0,false,true);
 mux.offer(1,true,false,[](auto){return true;},[&](auto t){zero[1]=t;},0);
 mux.offer(2,true,false,[](auto){return true;},[&](auto t){zero[2]=t;},0,true);
 while(z.step(true)){}assert(!z.progress().failed&&zero[2]==0&&zero[1]==1&&zero[0]==2);
}
