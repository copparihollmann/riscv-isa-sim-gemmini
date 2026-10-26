#include "posted_zero_writer.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
int main(){
 for(bool stall:{false,true}){
  Q q({4096,8192,100000});std::vector<Cycle>accepted,writes;std::vector<std::uint64_t>masks;
  PostedZeroWriter actor(q,[&](const auto&,Cycle t){return !stall||t>=10;},[&](const auto&r,Cycle t){writes.push_back(t);masks.push_back(r.mask);});
  actor.push({{0,0xffff,{}},{16,7,{}}},[&](Cycle t){accepted.push_back(t);actor.push({{1,31,{}}},[&](Cycle t){accepted.push_back(t);},t+1);},0);
  while(q.step(true)){}assert(!q.progress().failed&&!actor.busy()&&actor.peak_registers()==2);
  assert(accepted.size()==2&&accepted[0]==0&&accepted[1]==(stall?10:2));
  assert(writes==std::vector<Cycle>({stall?10u:2u,stall?11u:3u,stall?12u:4u}));assert(masks==std::vector<std::uint64_t>({65535,7,31}));
 }
 std::cout<<"ZeroWriter request1/pixel1 same-edge replacement, retained masks and stalled ownership PASS\n";
}
