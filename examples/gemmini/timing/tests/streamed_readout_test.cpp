#include "streamed_readout.hpp"
#include <cassert>
using namespace merlin_timing;
using namespace gemmini_annotated_spike;
int main() {
  ReadoutStreamConfig c{2,6,2,6,5,8,16,16};
  auto run=[&](ReadoutStreamConfig config,Cycle service,Cycle blocked,Cycle acknowledgement) {
    Cycle free=blocked;
    return stream_readout(config,16,64,0,[&](std::size_t,Cycle at,Cycle beats) {
      const auto start=std::max(at,free);free=start+service;
      return Result{at,start,start+std::max(beats,acknowledgement),UnknownReason::none};
    });
  };
  const auto clean=run(c,4,0,4),dirty=run(c,10,0,10);
  assert(clean.complete && dirty.complete && *dirty.complete>*clean.complete);
  assert(clean.scale_accept[0]==3 && clean.writer_accept[0]==11);
  assert(clean.memory_start[0]==14 && *clean.complete==78);
  assert(*dirty.complete==174);
  for(std::size_t i=1;i<16;++i) {
    assert(clean.memory_start[i]>=clean.memory_start[i-1]+4);
    assert(dirty.memory_start[i]>=dirty.memory_start[i-1]+10);
  }
  const auto blocked=run(c,4,100,4);
  assert(blocked.complete && blocked.memory_start[0]==100 && *blocked.complete> *clean.complete);
  assert(blocked.max_issue_metadata<=5);
  auto narrow=c;narrow.transactions=4;
  const auto credits=run(narrow,4,0,80),wide=run(c,4,0,80);
  assert(credits.complete && wide.complete && *credits.complete>*wide.complete);
  assert(credits.max_transactions<=4 && wide.max_transactions>4);
  auto exhausted=c;exhausted.transactions=2;
  assert(!run(exhausted,4,0,80).complete); // Ack contract precedes blocked final beat.
  auto slow=c;slow.issue_metadata=1;
  const auto bounded=run(slow,4,0,4);
  assert(bounded.complete && *bounded.complete>*clean.complete && bounded.max_issue_metadata==1);
  auto unknown=stream_readout(c,16,64,0,[](std::size_t,Cycle,Cycle){return Result{};});
  assert(!unknown.complete);
  auto stalled=run(c,4,1048576,4);assert(!stalled.complete);
  // A can accept later rows while older private probes wait for their resource.
  // This exposes outstanding credit pressure instead of serializing at A.
  auto split=c;split.independent_request_acceptance=true;
  const auto queued=run(split,10,100,13);
  assert(queued.complete && queued.memory_start[0]==100 && queued.request_accept[0]==14);
  for(std::size_t i=1;i<16;++i) assert(queued.request_accept[i]==14+4*i);
  assert(queued.max_transactions==16 && *queued.complete==263);
  split.transactions=4;
  const auto limited=run(split,10,100,13);
  assert(limited.complete && limited.max_transactions==4);
  assert(limited.request_accept[4]>limited.memory_complete[0]);
  split.transactions=2;
  const auto last_credit=run(split,4,0,80);
  assert(last_credit.complete && last_credit.max_transactions==2);
  // A registered command frontend shifts the complete pipeline once, without
  // changing row service rates or occupying a private probe before arrival.
  split=c;split.independent_request_acceptance=true;split.frontend_registered_cycles=6;
  const auto front=run(split,4,0,10), plain=run(c,4,0,10);
  assert(front.request_accept[0]==plain.request_accept[0]+6);
  assert(*front.complete==*plain.complete+6);
  // Selected public no-backpressure pipeline: one common request delay,
  // independent private service rates and response latency. Do not collapse
  // those stages into one serial command cost or share dirty/clean IDs.
  auto selected=[&](Cycle occupancy,Cycle response) {
    Cycle free=0;
    return stream_readout(split,16,64,0,[&](std::size_t,Cycle at,Cycle beats) {
      const auto start=std::max(at+6,free);free=start+occupancy;
      return Result{at,start,start+std::max(beats,response),UnknownReason::none};
    });
  };
  const auto dirty_pipeline=selected(10,13),clean_pipeline=selected(4,10);
  assert(dirty_pipeline.max_transactions==12 && clean_pipeline.max_transactions==5);
  assert(dirty_pipeline.request_accept[0]==20 && dirty_pipeline.memory_start[0]==26);
}
