#ifndef GEMMINI_PACKET_LOAD_HPP
#define GEMMINI_PACKET_LOAD_HPP
#include "provider.hpp"
#include "identity_ingress.hpp"
#include <memory>
#include <merlin_timing/reservations.hpp>
namespace gemmini_annotated_spike {
struct PacketLoadResult { std::optional<Cycle> complete,requests_complete; };
// Each actual Get reopens the memory ledger independently. A packet's complete
// ledger response is a conservative last-beat bound; never divide one scalar
// memory latency equally over rows/beats. Replay its finite merger work after
// that bound. No response interleaving is inferred: retain selected FIFO law.
class PacketLoadStream {
 public:
  explicit PacketLoadStream(Cycle identity_stages,bool source_ingress=false):identity_(identity_stages),transactions_(16),scale_(3) {
    if(source_ingress)ingress_=std::make_unique<IdentityIngress>();
    if(identity_<3 || identity_>4)throw std::invalid_argument("unsupported identity stages");
  }
  PacketLoadResult schedule(const std::vector<ReaderPacket>&packets,Cycle begin,
      const std::function<Result(std::size_t,Cycle)>&memory,
      const std::function<Result(std::size_t,bool,Cycle)>&write) {
    PacketLoadResult out;if(packets.empty() || packets.size()>64 || !response_)return out;
    Cycle requested=begin,complete=begin,last_request=begin;
    for(std::size_t i=0;i<packets.size();++i) {
      const auto &p=packets[i];
      if((p.bytes!=16 && p.bytes!=32 && p.bytes!=64) || !p.useful || p.shift+p.useful>p.bytes ||
          p.address%p.bytes || p.row>=16 || p.outputs.empty() || p.outputs.size()>5)return out;
      const auto tx=transactions_.allocate(std::max(requested,request_));
      if(!tx || tx->admitted>std::numeric_limits<Cycle>::max()-32)return out;
      const auto accepted=tx->admitted+2; // registered translation queues
      const auto fetched=memory(i,accepted);
      if(!fetched.start || !fetched.ready || *fetched.start<accepted ||
          *fetched.ready<*fetched.start || *fetched.ready>std::numeric_limits<Cycle>::max()-32) {
        response_.reset();return out;
      }
      const auto response=std::max(*fetched.ready,*response_);
      const auto beats=p.bytes/16;
      // One source packet can produce several real BeatMerger row outputs.
      // It still owns ONE reader transaction through its incoming last beat.
      std::optional<Cycle> stored_ready,merger_accepted;
      for(const auto &fragment:p.outputs) {
        if(fragment.destination>=128 || !fragment.mask || !fragment.bytes || fragment.bytes>16 ||
            fragment.required_beat>=beats)return out;
        const auto available=std::max(response+fragment.required_beat+1,
            merger_accepted ? *merger_accepted+1 : Cycle{0});
        if(ingress_) {
          const auto stream=ingress_->schedule(available,
              [&](Cycle at){return write(fragment.destination,fragment.destination_complete,at);});
          if(!stream.complete || !stream.accepted){response_.reset();return out;}
          stored_ready=stored_ready ? std::max(*stored_ready,*stream.complete) : stream.complete;
          merger_accepted=stream.accepted;
        } else {
          const auto slot=scale_.allocate(available);
          if(!slot || slot->admitted>std::numeric_limits<Cycle>::max()-32)return out;
          const auto stored=write(fragment.destination,fragment.destination_complete,slot->admitted+identity_-1);
          if(!stored.start || !stored.ready || *stored.start<slot->admitted+identity_-1 ||
              *stored.ready!=*stored.start+1){response_.reset();return out;}
          scale_.release(*slot,*stored.start+1);
          stored_ready=stored_ready ? std::max(*stored_ready,*stored.ready) : stored.ready;
          merger_accepted=slot->admitted;
        }
      }
      // Tracker ownership follows incoming last beat, not destination publish.
      transactions_.release(*tx,response+beats);
      response_=std::max(response+beats,*merger_accepted+1);
      requested=tx->admitted+1;request_=requested;last_request=accepted+1;
      complete=std::max(complete,*stored_ready);
    }
    out.complete=complete;out.requests_complete=last_request;return out;
  }
 private:
  std::unique_ptr<IdentityIngress> ingress_;
  Cycle identity_,request_=0;std::optional<Cycle>response_=Cycle{0};
  merlin_timing::ReservationWindow transactions_,scale_;
};
}
#endif
