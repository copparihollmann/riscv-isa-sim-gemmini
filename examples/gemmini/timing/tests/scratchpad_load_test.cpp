#include "scratchpad_load.hpp"
#include <cassert>
using namespace gemmini_annotated_spike;
int main() {
  // A cacheline RAW service delay is not request admission. Selected source
  // credits still limit ingress, and FIFO responses retain their dependence.
  ScratchpadLoadStream admitted({16,3,2,3,true});
  const auto queued=admitted.schedule(16,0,[](std::size_t row,Cycle at) {
    const auto service=row==1 ? Cycle{80} : at;
    return Result{service,service,service+20};
  },[](std::size_t,Cycle at){return Result{at,at,at+1};});
  assert(queued.requested[0]==2 && queued.requested[1]==3 && queued.requested[2]==4);
  assert(queued.service_start[1]==80 && queued.response[2]>=queued.response[1]+1);
  assert(queued.requests_complete==18);
  const auto next=admitted.schedule(16,0,[](std::size_t,Cycle at){return Result{at,at,at+20};},
      [](std::size_t,Cycle at){return Result{at,at,at+1};});
  // A transaction cannot recycle before its last incoming beat; even when
  // begin repeats, neither the shared request channel nor credits time-travel.
  assert(next.requested[0]>=queued.response[0]+3);
  assert(next.requested[1]>=queued.response[1]+3);
  // Requests remain independent of destination-bank delay until the bounded
  // identity queue fills. Never release a transaction at request submission.
  ScratchpadLoadStream stream({16,3,2,3});
  const auto result=stream.schedule(16,0,[](std::size_t,Cycle at) {
    return Result{at,at,at+20,merlin_timing::UnknownReason::none};
  },[](std::size_t,Cycle at) {
    const auto accepted=std::max(Cycle{100},at);
    return Result{at,accepted,accepted+1,merlin_timing::UnknownReason::none};
  });
  assert(result.complete && result.requested[0]==2 && result.response[0]==22);
  assert(result.response[1]==23 && result.response[2]==24);
  assert(result.response[3]>=101 && result.written[0]==100);
  assert(result.requests_complete==18); // not destination completion
  ScratchpadLoadStream delayed({16,3,2,4});
  const auto floor=delayed.schedule(1,0,[](std::size_t,Cycle at) {
    return Result{at,at,at+10,merlin_timing::UnknownReason::none};
  },[](std::size_t,Cycle at){return Result{at,at,at+1,merlin_timing::UnknownReason::none};});
  assert(floor.complete==17);
  const auto unknown=delayed.schedule(1,0,[](std::size_t,Cycle){return Result{};},
      [](std::size_t,Cycle){assert(false);return Result{};});
  assert(!unknown.complete);
  const auto poisoned=delayed.schedule(1,0,[](std::size_t,Cycle){assert(false);return Result{};},
      [](std::size_t,Cycle){assert(false);return Result{};});
  assert(!poisoned.complete);
  // Startup capture is separate from the per-row initiation interval, and
  // transaction release precedes destination publication (not request issue).
  ScratchpadLoadStream partial({16,3,2,4,true,true,1});
  const auto small=partial.schedule(8,10,[](std::size_t,Cycle at) {
    return Result{at,at,at+6};
  },[](std::size_t,Cycle at){return Result{at,at,at+1};},true);
  assert(small.requested.front()==13 && small.requested.back()==20);
  assert(small.requests_complete==21 && small.response.front()==19);
  assert(small.written.front()==23 && small.complete==35);
  ScratchpadLoadStream disabled({16,3,2,4,true});
  const auto refused=disabled.schedule(1,0,[](std::size_t,Cycle){assert(false);return Result{};},
      [](std::size_t,Cycle){assert(false);return Result{};},true);
  assert(!refused.complete);
  bool rejected=false;try { ScratchpadLoadStream invalid({16,4,2,3}); }
  catch(const std::invalid_argument &) {rejected=true;}assert(rejected);
}
