#include "fetch_miss_controller.hpp"
#include <cassert>
using namespace spike_timing;
int main(){
 using Q=merlin_timing::PostedTimeline;
 Q q({128,128,1024});FetchMissController controller(q,{2,1,1,1,2});
 std::optional<Q::Token>owner;std::optional<merlin_timing::Cycle>request,ready;
 owner=controller.begin(0,[&](auto at){request=at;q.post(at+7,{},[&](auto&,auto last){assert(controller.response(*owner,last,[&](auto at){ready=at;}));});});
 assert(owner&&controller.busy());assert(q.advance(2,true)&&!request);assert(q.advance(4,true)&&request==3);
 assert(q.advance(10,true)&&!ready&&!q.completed(*owner));assert(q.advance(13,true)&&!ready);
 assert(q.advance(15,true)&&ready==14&&q.completed(*owner)==14&&!controller.busy());
 // Original response can stall arbitrarily; no invented completion or credit.
 owner=controller.begin(20,[&](auto){q.post(70,{},[&](auto&,auto last){controller.response(*owner,last,[&](auto at){ready=at;});});});ready.reset();
 assert(q.advance(69,true)&&!ready&&controller.busy());assert(q.advance(75,true)&&ready==74&&!controller.busy());
 // Duplicate source or response cannot manufacture a second hardware entry.
 Q bad({32,32,100});FetchMissController one(bad,{2,1,1,1,2});assert(one.begin(0,[](auto){}));assert(!one.begin(0,[](auto){}));assert(bad.progress().failed);
 Q twice({32,32,100});FetchMissController original(twice,{2,1,1,1,2});auto t=original.begin(0,[](auto){});assert(t&&twice.advance(4,true));assert(original.response(*t,4,[](auto){}));assert(!original.response(*t,4,[](auto){}));assert(twice.progress().failed);
}
