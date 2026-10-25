#include "posted_readout_frontend.hpp"
#include <cassert>
using namespace gemmini_annotated_spike;
int main(){
 using Q=merlin_timing::PostedTimeline;Q q({65536,65536,1000000});
 ReadoutStreamConfig c{2,6,2,6,5,8,16,16};PostedReadoutFrontend front(q,c);
 std::vector<merlin_timing::Cycle>read,writer;std::vector<Q::Token>accepted;
 for(unsigned i=0;i<16;++i)accepted.push_back(front.push(
   [&](auto at,auto accepted,auto response){read.push_back(at);q.complete(accepted);q.post(at+1,{},[response](auto&q,auto){q.complete(response);},Q::Kind::completion);},
   [&](auto at,auto consumed){writer.push_back(at);q.post(at+(writer.size()==1?7:0),{},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::completion);},1));
 while(q.step(true)){}
 assert(!q.progress().failed&&!front.busy()&&read.size()==16&&writer.size()==16);
 assert(read.front()==2&&writer.front()==12); // dispatch1+SRAM1+normalizer1+scale8
 assert(front.peak_issued()==5);
 for(auto t:accepted)assert(q.completed(t));
 for(std::size_t i=1;i<read.size();++i)assert(read[i]>=read[i-1]+1&&writer[i]>=writer[i-1]+1);
 assert(writer.back()>writer.front()+15); // real finite metadata and stalled writer
}
