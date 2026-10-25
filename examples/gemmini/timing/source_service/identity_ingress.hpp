#ifndef GEMMINI_IDENTITY_INGRESS_HPP
#define GEMMINI_IDENTITY_INGRESS_HPP
#include "provider.hpp"
#include <merlin_timing/reservations.hpp>
namespace gemmini_annotated_spike {
// Selected identity/no-repeat int8 path only. Separate registered queues and
// handshakes; no lumped capacity grant. Source: VectorScalarMultiplier.apply
// Queue2 -> in register -> identity-completed ring3 -> PixelRepeater register.
struct IdentityIngressResult {
 std::optional<Cycle> accepted,complete;
};
class IdentityIngress {
 public:
  IdentityIngress():input_queue_(2),input_register_(1),completed_ring_(3),pixel_register_(1){}
  IdentityIngressResult schedule(Cycle available,const std::function<Result(Cycle)> &write){
    IdentityIngressResult out;
    if(available>std::numeric_limits<Cycle>::max()-1048576)return out;
    const auto q=input_queue_.allocate(std::max(available,next_input_));
    if(!q)return out;
    const auto in=input_register_.allocate(q->admitted+1);
    if(!in)return out;
    // Default Queue2 is non-pipe/non-flow: a full queue sees a dequeue credit
    // only after the edge. The input register itself permits replacement on
    // the same cycle its prior payload fires into the completed ring.
    input_queue_.release(*q,in->admitted+1);
    const auto ring=completed_ring_.allocate(in->admitted+1);
    if(!ring)return out;
    input_register_.release(*in,ring->admitted);
    const auto pixel=pixel_register_.allocate(ring->admitted+1);
    if(!pixel)return out;
    // Ring tail reads prior valid state; no same-edge full-slot recycling.
    completed_ring_.release(*ring,pixel->admitted+1);
    const auto stored=write(pixel->admitted+1);
    if(!stored.start || !stored.ready || *stored.start<pixel->admitted+1 ||
        *stored.ready!=*stored.start+1)return out;
    // PixelRepeater pixel_repeats==1 (stored remaining0) replaces on response
    // fire. Actual SP write still owns all bank/row WAW/WAR through callback.
    pixel_register_.release(*pixel,*stored.start);
    next_input_=q->admitted+1;out.accepted=q->admitted;out.complete=stored.ready;return out;
  }
 private:
  merlin_timing::ReservationWindow input_queue_,input_register_,completed_ring_,pixel_register_;
  Cycle next_input_=0;
};
}
#endif
