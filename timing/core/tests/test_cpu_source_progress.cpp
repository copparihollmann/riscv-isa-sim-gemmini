#include <merlin_timing/posted_engine_stage.hpp>
#include <cassert>
#include <iostream>
using namespace merlin_timing;
int main(){
 // The native owner registers only the original committed CPU execution
 // token. No target command exists in this arbitrarily long scalar prefix.
 Engine engine(8,{{0,1,2}});PostedTimeline q({32,64,16});
 for(unsigned i=0;i<10000;++i){
  auto done=q.token();assert(done&&q.track_source_completion(*done));
  OwnedStage cpu;cpu.origin=StageOrigin{0x80000000+4*i,0x13,i,"cpu.integer"};cpu.earliest=i*3;cpu.latency=2;cpu.writes={1};cpu.demands={{0,1,Cycle{1}}};
  std::optional<Result>accepted;
  assert(PostedEngineStage::post(q,engine,cpu,{},*done,[&](auto&r){accepted=r;}));
  while(!accepted)assert(q.step(true));
  // Admission did not manufacture the completion checkpoint.
  assert(!q.completed(*done));assert(q.advance(i*3+2,true));assert(!q.completed(*done));
  assert(q.advance(i*3+3,true));assert(q.completed(*done)==i*3+2);
 }
 assert(!q.progress().failed&&q.progress().dispatched>q.specification().dispatched);
 assert(q.peak_dispatches_without_source_completion()<q.specification().dispatched);
 // Genuine admission with no completed result does not reset the guard.
 PostedTimeline stalled({8,8,16});auto result=stalled.token();assert(result&&stalled.track_source_completion(*result));
 for(unsigned i=0;i<16;++i){assert(stalled.post(i,{},[](auto&,auto){}));assert(stalled.advance(i+1,true));}
 assert(stalled.post(16,{},[](auto&,auto){}));assert(!stalled.advance(17,true));assert(stalled.reason()=="posted dispatch budget");
 std::cout<<"10000 original CPU result completions progress without target commands; admission/poll-only guard retained PASS\n";
}
