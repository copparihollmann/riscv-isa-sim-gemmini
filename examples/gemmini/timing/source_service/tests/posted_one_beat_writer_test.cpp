#include "posted_one_beat_writer.hpp"
#include <cassert>
using namespace gemmini_annotated_spike;
int main(){
 using Q=merlin_timing::PostedTimeline;Q q({65536,65536,1000000});PostedRegisteredTransport a(q,{{2,false},{2,false}}),d(q,{{2,false},{2,false}});
 PostedOneBeatWriter writer(q,a,d);std::vector<merlin_timing::Cycle>requests;std::vector<Q::Token>done;
 std::function<void(unsigned,merlin_timing::Cycle)>issue;
 issue=[&](unsigned i,auto at){
   auto finish=*q.token();done.push_back(finish);
   auto accepted=writer.push([&](auto t,auto response){requests.push_back(t);q.post(t+50,{},[response](auto&q,auto){q.complete(response);},Q::Kind::completion);},at,finish);
   if(i+1<20)q.post(at,{accepted},[&,i](auto&,auto t){issue(i+1,t+1);},Q::Kind::source_arrival);
 };
 issue(0,0);while(q.step(true)){}
 assert(!q.progress().failed&&!writer.busy()&&requests.size()==20&&writer.peak_transactions()==16);
 assert(requests.front()==6); // capture1 +translation2 +clientA1 +sharedA2
 for(auto t:done)assert(q.completed(t));
 assert(requests[16]>=requests[0]+50+3+1+5); // D3, nextedgecredit, requesttransport5
}
