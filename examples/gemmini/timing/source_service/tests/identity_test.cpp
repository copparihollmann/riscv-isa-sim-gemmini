#include "identity_ingress.hpp"
#include <cassert>
#include <deque>
#include <iostream>
using namespace gemmini_annotated_spike;
struct Rows {std::vector<Cycle> accepted,written;};
Rows reference(const std::vector<Cycle>&arrivals,Cycle blocked){
 Rows out;const auto n=arrivals.size();out.accepted.resize(n);out.written.resize(n);
 std::deque<std::size_t> q,ring;std::size_t input=n,pixel=n,next=0,done=0;
 for(Cycle t=0;t<10000;++t){
  const bool wf=pixel!=n&&t>=blocked;
  const bool pp=!ring.empty()&&(pixel==n||wf);
  const bool inf=input!=n&&ring.size()<3;
  const bool dq=!q.empty()&&(input==n||inf);
  const bool enq=next<n&&arrivals[next]<=t&&q.size()<2;
  const auto oldinput=input;
  if(wf){out.written[pixel]=t;pixel=n;++done;}
  if(pp){pixel=ring.front();ring.pop_front();}
  if(inf){ring.push_back(oldinput);input=n;}
  if(dq){input=q.front();q.pop_front();}
  if(enq){out.accepted[next]=t;q.push_back(next++);}
  if(done==n)return out;
 }
 assert(false);return out;
}
int main(){
 for(Cycle block:{0u,7u,40u})for(unsigned pattern:{0u,1u,2u}){
  std::vector<Cycle> arrivals;for(unsigned r=0;r<24;++r)arrivals.push_back(pattern==0?0:r*(pattern==1?1:7));
  auto ref=reference(arrivals,block);IdentityIngress pipe;Rows actual;Cycle port=0;
  for(auto arrival:arrivals){
   const auto result=pipe.schedule(arrival,[&](Cycle at){at=std::max({at,block,port});port=at+1;actual.written.push_back(at);return Result{at,at,at+1,merlin_timing::UnknownReason::none};});
   assert(result.accepted&&result.complete);actual.accepted.push_back(*result.accepted);
  }
  assert(actual.accepted==ref.accepted&&actual.written==ref.written);
 }
 std::cout<<"Exact2/1/3/1 identity stage admissions equal independent clock-step model for9arrival/backpressure scenarios; no lumped-capacity grant PASS\n";
}
