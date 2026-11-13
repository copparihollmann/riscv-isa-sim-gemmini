#pragma once
#include <array>
#include <cstdint>
#include <deque>
#include <optional>
#include <stdexcept>

// Ownership ledger only.  This is NOT a translated VMU, source-ready model or
// timing backend.  The circular reserve/ordered completion contract follows
// saturn/common/ReorderBuffer.scala and mem/Mem.scala (store_req_q / SIFQ).
namespace iris::vse_boundary {
struct Identity {
  unsigned hart=0; uint64_t epoch=0,command=0,pc=0; uint32_t raw=0;
  bool operator==(const Identity&)const=default;
};
struct Token {
  unsigned tag=0; uint64_t generation=0;
  bool operator==(const Token&)const=default;
};
struct Request {
  Identity owner; Token token; unsigned first_word=0,words=0;
  uint64_t address=0; bool last=false;
  std::array<uint8_t,16> data{},known{};
  uint16_t mask=0;
};
class OrderedStores {
 public:
  static constexpr unsigned capacity=16, request_queue_capacity=2;
  bool reserve_ready()const{return live_<capacity&&requests_.size()<request_queue_capacity;}
  bool empty()const{return live_==0;}
  unsigned live()const{return live_;}
  unsigned request_count()const{return requests_.size();}
  unsigned sifq_count()const{return sifq_.size();}
  Request reserve(Request r){
    if(!reserve_ready())throw std::logic_error("VSE_BOUNDARY_RESERVE_WITHOUT_CREDIT");
    if(r.owner.hart>1||!r.owner.epoch||!r.owner.command||!r.words||r.words>4||r.address%16||!r.mask)
      throw std::logic_error("VSE_BOUNDARY_INVALID_OWNED_REQUEST");
    if(slots_[enq_])throw std::logic_error("VSE_BOUNDARY_CIRCULAR_SLOT_STILL_OWNED");
    const uint16_t expected=uint16_t((uint32_t(1)<<(4*r.words))-1);
    if(r.mask!=expected)throw std::logic_error("VSE_BOUNDARY_NONCONTIGUOUS_FINITE_MASK");
    r.token={enq_,++generations_[enq_]};slots_[enq_]=Slot{r,false,false};
    requests_.push_back(r.token);enq_=(enq_+1)%capacity;++live_;return r;
  }
  std::optional<Request> request()const {
    if(requests_.empty())return {};
    return get(requests_.front()).request;
  }
  void accepted(Token t){
    if(requests_.empty()||requests_.front()!=t)throw std::logic_error("VSE_BOUNDARY_REQUEST_ACCEPT_OWNER_ORDER");
    auto&s=get(t);if(s.sent)throw std::logic_error("VSE_BOUNDARY_REQUEST_ACCEPT_DUPLICATE");
    s.sent=true;sifq_.push_back(t);requests_.pop_front();
  }
  Request acknowledge(Token t){
    auto&s=get(t);if(!s.sent||s.acked)throw std::logic_error("VSE_BOUNDARY_ACK_NOT_UNIQUE_ACCEPTED_OWNER");
    s.acked=true;return s.request;
  }
  std::optional<Request> release(){
    if(sifq_.empty())return {};
    auto&s=get(sifq_.front());if(!s.acked)return {};
    if(s.request.token.tag!=deq_)throw std::logic_error("VSE_BOUNDARY_SIFQ_ROB_HEAD_DISAGREEMENT");
    auto r=s.request;sifq_.pop_front();slots_[deq_].reset();deq_=(deq_+1)%capacity;--live_;return r;
  }
 private:
  struct Slot{Request request;bool sent,acked;};
  std::array<std::optional<Slot>,capacity>slots_{};
  std::array<uint64_t,capacity>generations_{};
  std::deque<Token>requests_,sifq_;unsigned enq_=0,deq_=0,live_=0;
  Slot&get(Token t){
    if(t.tag>=capacity||!slots_[t.tag]||slots_[t.tag]->request.token!=t)
      throw std::logic_error("VSE_BOUNDARY_STALE_OR_UNOWNED_GENERATION");
    return *slots_[t.tag];
  }
  const Slot&get(Token t)const{return const_cast<OrderedStores*>(this)->get(t);}
};
} // namespace iris::vse_boundary
