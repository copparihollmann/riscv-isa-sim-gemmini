#include "registered_transport.hpp"
#include <cassert>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;
int main(){
 for(bool pipe:{false,true}){
   Q q({4096,4096,10000});PostedRegisteredTransport transport(q,{{1,pipe}});
   std::vector<merlin_timing::Cycle>times;std::optional<Q::Token>held;
   auto first=transport.push([&](auto at,auto consumed){times.push_back(at);held=consumed;},0);
   auto second=transport.push([&](auto at,auto consumed){times.push_back(at);q.complete(consumed);},0);
   q.post(5,{},[&](auto&,auto){assert(held);q.complete(*held);},Q::Kind::completion);
   while(q.step(true)){}
   assert(!q.progress().failed&&q.completed(first)&&q.completed(second)&&!transport.busy());
   assert(times==std::vector<merlin_timing::Cycle>({1,pipe?6u:7u}));
   assert(transport.peaks()==std::vector<std::size_t>{1});
 }
 Q q({4096,4096,10000});PostedRegisteredTransport p(q,{{1,true},{1,true},{2,false},{2,false},{2,false}});
 std::vector<merlin_timing::Cycle>times;
 for(unsigned i=0;i<8;++i)p.push([&](auto at,auto consumed){times.push_back(at);q.complete(consumed);},i);
 while(q.step(true)){}
 assert(!q.progress().failed&&!p.busy());
 assert(times==std::vector<merlin_timing::Cycle>({5,6,7,8,9,10,11,12}));
 const auto peaks=p.peaks();for(std::size_t i=0;i<peaks.size();++i)assert(peaks[i]<=(i<2?1:2));
 // An already visible second entry cannot dequeue on the same edge as a
 // stalled head; pipe permits enqueue/dequeue reuse, not two dequeue fires.
 Q stalled({128,128,1000});PostedRegisteredTransport two(stalled,{{2,false}});
 std::optional<Q::Token>hold;std::vector<merlin_timing::Cycle>accepted;
 two.push([&](auto at,auto done){accepted.push_back(at);hold=done;},0);
 two.push([&](auto at,auto done){accepted.push_back(at);const auto previous=two.previous_edge(0,at);
   assert(previous.begin==2&&previous.end==1&&!previous.enqueued&&previous.dequeued);stalled.complete(done);},1);
 stalled.post(5,{},[&](auto&q,auto){assert(hold);q.complete(*hold);});
 while(stalled.step(true)){}assert(!stalled.progress().failed);
 assert((accepted==std::vector<merlin_timing::Cycle>{1,6}));
}
