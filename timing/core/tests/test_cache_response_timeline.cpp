#include <merlin_timing/cache_response_timeline.hpp>
#include <cassert>
#include <iostream>
using namespace merlin_timing;
int main() {
  CacheResponseSpec s{4,6,1,1,2};
  CacheResponseInputs i{100,{0,0,0,0},0,false};
  auto t=plan_cache_response(s,i);
  assert(t.complete && t.accepted_beats==std::vector<std::uint64_t>({106,107,108,109}));
  assert(t.line_visible==110 && t.lookup_accepted==110 && t.lookup_response==112);
  // Backpressure delays dependent later beats, not merely a resource counter.
  i.receiver_ready[1]=115; t=plan_cache_response(s,i);
  assert(t.complete && t.accepted_beats==std::vector<std::uint64_t>({106,115,116,117}));
  assert(t.lookup_response==120);
  i.replay_request_ready=130;t=plan_cache_response(s,i);assert(t.lookup_response==132);
  i.replay_request_ready.reset();t=plan_cache_response(s,i);
  assert(t.response_complete && !t.complete && t.line_visible==118 && !t.lookup_response);
  i.receiver_ready[2].reset();t=plan_cache_response(s,i);
  assert(!t.response_complete && !t.complete && t.accepted_beats.size()==2);
  i={100,{0,0,0,0},0,true};t=plan_cache_response(s,i);
  assert(t.response_complete && !t.complete && !t.line_visible);
  i.invalidated_during_refill=false;s.first_response_cycles.reset();
  assert(!plan_cache_response(s,i).response_complete);
  s.first_response_cycles=6;i.request_accepted=~std::uint64_t{0};
  assert(!plan_cache_response(s,i).complete);
  s.beats=4097;assert(!plan_cache_response(s,i).complete);
  // Different generic bus geometry: no target-name/line-size dispatch.
  s={2,3,2,0,1};i={0,{0,0},7,false};t=plan_cache_response(s,i);
  assert(t.complete && t.accepted_beats==std::vector<std::uint64_t>({3,5}) && t.lookup_response==8);
  std::cout<<"cache response timeline: response, visibility, replay, backpressure and unknown checks pass\n";
}
