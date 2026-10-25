#ifndef SPIKE_TIMING_POSTED_MEMORY_HPP
#define SPIKE_TIMING_POSTED_MEMORY_HPP
#include "memory.hpp"
#include <merlin_timing/posted_engine_stage.hpp>
namespace spike_timing {
// Actual native MemorySystem consumer for deferred source acceptance. The
// source owner supplies an ACCEPTED time, not just CPU submission; all other
// source arrivals before each advanced frontier must already be posted.
// Legacy SharedEffects provides only aggregate payload-completion service.
// It does not establish per-beat readiness, MSHR ownership or source-closed RR.
// No observer/profile opts into this helper automatically.
class PostedAggregateMemory {
 public:
 static bool post_accepted(merlin_timing::PostedTimeline&q,MemorySystem&memory,
       merlin_timing::Engine&engine,std::vector<MemoryEffect> effects,std::string path,
       merlin_timing::Cycle accepted,std::vector<merlin_timing::PostedTimeline::Token> dependencies,
       merlin_timing::PostedTimeline::Token completion) {
   return q.post(accepted,std::move(dependencies),
       [&memory,&engine,effects=std::move(effects),path=std::move(path),completion](auto&q,auto at){
     // Classification happens HERE, after intervening CPU/device arrivals.
     // It must never happen when the future transaction is merely posted.
     auto observed=memory.access(effects,path);
     if(!observed.latency){q.fail("accepted memory source has unresolved aggregate service");return;}
     merlin_timing::OwnedStage stage;stage.earliest=at;stage.reads=std::move(observed.reads);
     stage.writes=std::move(observed.writes);stage.demands=std::move(observed.demands);
     stage.latency=observed.latency;stage.hold_reads_until_ready=true;
     // An aggregate service callback is NOT an actual response beat.
     stage.kind=merlin_timing::PostedTimeline::Kind::other;
     merlin_timing::PostedEngineStage::post(q,engine,std::move(stage),{},completion);
   },merlin_timing::PostedTimeline::Kind::memory_accept);
 }
};
}
#endif
