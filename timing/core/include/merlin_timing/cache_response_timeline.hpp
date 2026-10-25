#ifndef MERLIN_TIMING_CACHE_RESPONSE_TIMELINE_HPP
#define MERLIN_TIMING_CACHE_RESPONSE_TIMELINE_HPP
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <vector>

namespace merlin_timing {
// Inactive, explicitly invoked candidate. No cache-state inference, price defaults,
// retirement prediction, or selected-target/model constants live in this helper.
struct CacheResponseSpec {
  std::uint32_t beats = 0;
  std::optional<std::uint64_t> first_response_cycles;
  std::optional<std::uint64_t> beat_interval_cycles;
  std::optional<std::uint64_t> line_visible_after_last_cycles;
  std::optional<std::uint64_t> lookup_response_cycles;
};
struct CacheResponseInputs {
  std::optional<std::uint64_t> request_accepted;
  // Every beat requires an explicit lower bound from receiver/arbiter state.
  // Zero is an explicit no-backpressure assumption, not a default observation.
  std::vector<std::optional<std::uint64_t>> receiver_ready;
  std::optional<std::uint64_t> replay_request_ready;
  // A flush during this transaction prevents a successful refill publication.
  bool invalidated_during_refill = false;
};
struct CacheResponseTimeline {
  std::vector<std::uint64_t> accepted_beats;
  std::optional<std::uint64_t> line_visible;
  std::optional<std::uint64_t> lookup_accepted;
  std::optional<std::uint64_t> lookup_response;
  bool response_complete = false;
  bool complete = false;
  std::string unresolved;
};
inline CacheResponseTimeline plan_cache_response(const CacheResponseSpec &spec,
                                                 const CacheResponseInputs &input) {
  CacheResponseTimeline out;
  auto stop = [&](const char *reason) { out.unresolved=reason; return out; };
  auto sum = [](std::uint64_t a, std::uint64_t b)->std::optional<std::uint64_t> {
    if (b>std::numeric_limits<std::uint64_t>::max()-a) return {};
    return a+b;
  };
  if (!spec.beats || spec.beats>4096 || input.receiver_ready.size()!=spec.beats)
    return stop("response beat geometry is missing or exceeds bounded scope");
  if (!input.request_accepted || !spec.first_response_cycles ||
      !spec.beat_interval_cycles || !*spec.beat_interval_cycles)
    return stop("request admission or response service is unknown");
  auto next=sum(*input.request_accepted,*spec.first_response_cycles);
  if (!next) return stop("response cycle overflow");
  for (std::uint32_t i=0;i<spec.beats;++i) {
    if (!input.receiver_ready[i]) return stop("receiver or arbiter admission is unknown");
    auto accepted=*next>*input.receiver_ready[i]?*next:*input.receiver_ready[i];
    out.accepted_beats.push_back(accepted);
    if (i+1<spec.beats) {
      next=sum(accepted,*spec.beat_interval_cycles);
      if (!next) return stop("response cycle overflow");
    }
  }
  out.response_complete=true;
  if (input.invalidated_during_refill)
    return stop("invalidation prevents this transaction publishing a valid line");
  if (!spec.line_visible_after_last_cycles) return stop("line publication boundary is unknown");
  out.line_visible=sum(out.accepted_beats.back(),*spec.line_visible_after_last_cycles);
  if (!out.line_visible) return stop("line publication cycle overflow");
  if (!input.replay_request_ready) return stop("frontend replay admission is unknown");
  out.lookup_accepted=*out.line_visible>*input.replay_request_ready?
      *out.line_visible:*input.replay_request_ready;
  if (!spec.lookup_response_cycles) return stop("lookup response pipeline is unknown");
  out.lookup_response=sum(*out.lookup_accepted,*spec.lookup_response_cycles);
  if (!out.lookup_response) return stop("lookup response cycle overflow");
  out.complete=true;
  return out;
}
} // namespace merlin_timing
#endif
