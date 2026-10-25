#ifndef GEMMINI_SCRATCHPAD_LOAD_HPP
#define GEMMINI_SCRATCHPAD_LOAD_HPP
#include "provider.hpp"
#include <merlin_timing/reservations.hpp>

namespace gemmini_annotated_spike {
// Narrow provisional producer: aligned one-beat int8 rows, identity scaling,
// translation hits. Existing memory observations price each actual row. FIFO
// responses are a conservative approximation, not a claim of TL response order.
struct ScratchpadLoadConfig {
  std::size_t transactions=16, scale_entries=3;
  Cycle translation_stages=2, identity_stages=3;
  bool independent_request_admission=false;
  bool partial_single_beat_rows=false;
  Cycle partial_request_capture_stages=0;
};
struct ScratchpadLoadResult {
  std::optional<Cycle> complete, requests_complete;
  std::vector<Cycle> requested, service_start, response, written;
};
class ScratchpadLoadStream {
public:
  explicit ScratchpadLoadStream(ScratchpadLoadConfig config)
      : c_(config), transactions_(config.transactions), scale_(config.scale_entries) {
    if(config.transactions!=16 || config.scale_entries!=3 || config.translation_stages!=2 ||
        (config.identity_stages!=3 && config.identity_stages!=4) ||
        config.partial_request_capture_stages!=(config.partial_single_beat_rows?1u:0u))
      throw std::invalid_argument("unsupported scratchpad identity row pipeline");
  }
  ScratchpadLoadResult schedule(std::size_t rows, Cycle begin,
      const std::function<Result(std::size_t,Cycle)> &memory,
      const std::function<Result(std::size_t,Cycle)> &write,
      bool partial_row=false) {
    ScratchpadLoadResult out;
    if((partial_row && !c_.partial_single_beat_rows) || !rows || rows>16 || !response_frontier_ ||
        begin>std::numeric_limits<Cycle>::max()-1048576) return out;
    // StreamReaderCore captures each DMA request in req/state before its
    // first untranslated Get. Throughput remains one row per cycle when the
    // previous one-beat request fires; this is startup, not per-row occupancy.
    const Cycle capture=partial_row?c_.partial_request_capture_stages:0;
    Cycle request=begin+capture+(c_.independent_request_admission?0:c_.translation_stages), complete=begin;
    Cycle last_request=begin;
    for(std::size_t row=0;row<rows;++row) {
      const auto tx=transactions_.allocate(c_.independent_request_admission ?
          std::max(request,request_frontier_) : request);
      if(!tx || tx->admitted>std::numeric_limits<Cycle>::max()-16)return out;
      // Selected reader reserves its transaction before the two registered
      // translation queues. Explicit A-ready/translation-hit assumptions allow
      // the next request to enter independently of a prior response's RAW wait.
      const auto accepted=tx->admitted+(c_.independent_request_admission?c_.translation_stages:0);
      const auto fetched=memory(row,accepted);
      if(!fetched.start || !fetched.ready || *fetched.start<accepted ||
          *fetched.ready<*fetched.start || *fetched.ready>std::numeric_limits<Cycle>::max()-16) {
        response_frontier_.reset();return out;
      }
      // Capacity includes the identity FIFO only; treating its upstream input
      // register as part of this capacity is conservative under backpressure.
      const auto slot=scale_.allocate(std::max(*fetched.ready,*response_frontier_));
      if(!slot || slot->admitted>std::numeric_limits<Cycle>::max()-16) {
        response_frontier_.reset();return out;
      }
      // XactTracker releases on last incoming beat, NOT destination publication.
      transactions_.release(*tx,slot->admitted+1);
      const auto stored=write(row,slot->admitted+c_.identity_stages);
      if(!stored.start || !stored.ready || *stored.start<slot->admitted+c_.identity_stages ||
          *stored.ready!=*stored.start+1) {response_frontier_.reset();return out;}
      scale_.release(*slot,*stored.start+1);
      response_frontier_=slot->admitted+1;
      request=c_.independent_request_admission ? tx->admitted+1 : *fetched.start+1;
      if(c_.independent_request_admission)request_frontier_=request;
      last_request=c_.independent_request_admission ? accepted+1 : request;
      complete=std::max(complete,*stored.ready);
      out.requested.push_back(c_.independent_request_admission ? accepted : *fetched.start);
      out.service_start.push_back(*fetched.start);out.response.push_back(slot->admitted);
      out.written.push_back(*stored.start);
    }
    out.complete=complete;out.requests_complete=last_request;return out;
  }
private:
  ScratchpadLoadConfig c_;
  merlin_timing::ReservationWindow transactions_,scale_;
  std::optional<Cycle> response_frontier_=Cycle{0};
  Cycle request_frontier_=0;
};
} // namespace gemmini_annotated_spike
#endif
