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
 // A local ACC port can retain the pixel for multiple edges. No replacement
 // or upstream request acceptance may use that register before write.fire.
 Q held({4096,8192,100000});std::vector<Cycle>fires,inputs;
 PostedZeroWriter asynchronous(held,[](const auto&,Cycle){return true;},
   [&](const auto&,Cycle at,PostedZeroWriter::Accepted accepted){
     held.post(at+7,{},[&,accepted](auto&,Cycle t){fires.push_back(t);accepted(t);},Q::Kind::local_publish);
   });
 asynchronous.push({{0,0xffff,{}},{16,3,{}}},[&](Cycle t){inputs.push_back(t);asynchronous.push({{1,1,{}}},[&](Cycle t){inputs.push_back(t);},t+1);},0);
 while(held.step(true)){}assert(!held.progress().failed&&!asynchronous.busy());
 assert(asynchronous.peak_registers()==2&&inputs==std::vector<Cycle>({0,9})&&fires==std::vector<Cycle>({9,17,25}));
 std::cout<<"ZeroWriter request1/pixel1 same-edge replacement, retained masks and stalled ownership PASS\n";
}
