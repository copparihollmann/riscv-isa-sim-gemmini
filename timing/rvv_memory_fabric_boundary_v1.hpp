#pragma once
#include <array>
#include <cstdint>
#include <deque>
#include <optional>
#include <stdexcept>

namespace iris::rvv_memory_boundary_v1 {

// Control translation of the configured ReorderBuffer(Bool(),16). This is not
// an AddrGen, SIFQ, VMU, TL ready generator or memory latency model.
struct RobInput {
  bool reset=false, reserve_ready=false, push_valid=false;
  unsigned push_tag=0;
  bool deq_ready=false, known=false;
};
struct RobOutput {
  bool qualified=false, reserve_valid=false;
  unsigned reserve_tag=0;
  bool deq_valid=false, reserve_fire=false, deq_fire=false, busy=false;
};
class ComputeStoreRob {
 public:
  void evaluate(RobInput in) {
    prepared_=false;
    if (!in.known || (in.push_valid && in.push_tag>=16))
      throw std::invalid_argument("IRIS_STORE_ROB_UNKNOWN_OR_EXCESS_WIDTH");
    if (!initialized_ && !in.reset)
      throw std::logic_error("IRIS_STORE_ROB_ACTUAL_RESET_REQUIRED");
    const bool same=enq_==deq_, empty=same&&!maybe_full_, full=same&&maybe_full_;
    if (!in.reset && in.push_valid && (valids_&(1u<<in.push_tag)))
      throw std::logic_error("IRIS_STORE_ROB_DUPLICATE_COMPLETION");
    input_=in;
    output_={initialized_,!full,enq_,!empty&&
      (bool(valids_&(1u<<deq_))||(in.push_valid&&in.push_tag==deq_)),false,false,!empty};
    output_.reserve_fire=output_.reserve_valid&&in.reserve_ready;
    output_.deq_fire=output_.deq_valid&&in.deq_ready;
    prepared_=true;
  }
  RobOutput sample() const {
    if (!prepared_) throw std::logic_error("IRIS_STORE_ROB_SAMPLE_WITHOUT_EVALUATE");
    return output_;
  }
  void commit() {
    if (!prepared_) throw std::logic_error("IRIS_STORE_ROB_COMMIT_WITHOUT_EVALUATE");
    if (input_.reset) {valids_=0;enq_=deq_=0;maybe_full_=false;initialized_=true;}
    else {
      if (input_.push_valid) {
        const unsigned bit=1u<<input_.push_tag;
        if (input_.deq_ready&&deq_==input_.push_tag) valids_&=~bit;
        else valids_|=bit;
      }
      if (output_.deq_fire) valids_&=~(1u<<deq_);
      if (output_.reserve_fire) enq_=(enq_+1)&15;
      if (output_.deq_fire) deq_=(deq_+1)&15;
      if (output_.reserve_fire!=output_.deq_fire) maybe_full_=output_.reserve_fire;
    }
    prepared_=false;
  }
 private:
  unsigned valids_=0,enq_=0,deq_=0;
  bool maybe_full_=false,initialized_=false,prepared_=false;
  RobInput input_{};RobOutput output_{};
};

struct Edges {bool rocket,uncore,bringup,serial;};
struct Stamp {std::uint64_t master_tick,native_whole;bool native_half;};
// Explicit qualified profile, not a frequency/default inference. Caller must
// bind these phase origins/reset waveforms to its integration receipt.
class SourceClocks {
 public:
  SourceClocks(std::uint64_t master_hz,std::uint64_t native_hz,
               std::array<unsigned,4>periods,std::array<unsigned,4>origins)
      :periods_(periods),origins_(origins) {
    if (master_hz!=1000000000ULL||native_hz!=500000000ULL||
        periods!=std::array<unsigned,4>{2,2,1,10})
      throw std::invalid_argument("IRIS_STORE_CLOCK_PROFILE_MISMATCH");
    for(unsigned i=0;i<4;++i)if(origins_[i]>=periods_[i])
      throw std::invalid_argument("IRIS_STORE_CLOCK_ORIGIN_OUTSIDE_PERIOD");
  }
  Edges edges(std::uint64_t t)const {
    return {t%periods_[0]==origins_[0],t%periods_[1]==origins_[1],
            t%periods_[2]==origins_[2],t%periods_[3]==origins_[3]};
  }
  static Stamp stamp(std::uint64_t master_tick) {
    return {master_tick,master_tick/2,bool(master_tick&1)};
  }
 private:std::array<unsigned,4>periods_,origins_;
};

struct Owner {
  unsigned hart,tag,bytes;
  std::uint64_t command,generation;
  bool A_accepted=false,ACK_received=false;
};
// A fail-closed sidecar, not hidden RTL state. Generation and command metadata
// never drive ready. Source ROB/SIFQ events alone call reserve/retire; physical
// A/D handshakes alone call accept_A/ack. No memory writes happen in this class.
class StoreOwners {
 public:
  explicit StoreOwners(unsigned hart):hart_(hart) {
    if(hart>1)throw std::invalid_argument("IRIS_STORE_OWNER_COMPUTE_HART_ONLY");
  }
  Owner reserve(unsigned tag,std::uint64_t command,unsigned bytes) {
    if(tag>=16||tag!=next_tag_||owners_[tag]||order_.size()==16||!command||
       !bytes||bytes>16||(bytes%4)||generation_==UINT64_MAX)
      throw std::invalid_argument("IRIS_STORE_OWNER_ILLEGAL_RESERVATION");
    Owner owner{hart_,tag,bytes,command,++generation_,false,false};
    owners_[tag]=owner;order_.push_back(tag);next_tag_=(next_tag_+1)&15;
    return owner;
  }
  void accept_A(unsigned tag,std::uint64_t generation) {
    auto&o=find(tag);
    if(o.generation!=generation||o.A_accepted)
      throw std::logic_error("IRIS_STORE_OWNER_STALE_OR_DUPLICATE_A");
    o.A_accepted=true;
  }
  Owner ack(unsigned source,bool denied,bool corrupt,bool control_known) {
    if(!control_known||source>=16||denied||corrupt)
      throw std::invalid_argument("IRIS_STORE_OWNER_UNQUALIFIED_D");
    auto&o=find(source);
    if(!o.A_accepted||o.ACK_received)
      throw std::logic_error("IRIS_STORE_OWNER_UNMATCHED_OR_DUPLICATE_ACK");
    o.ACK_received=true;
    return o; // Optional mirror publication is the caller's explicit policy.
  }
  Owner retire(unsigned tag) {
    auto&o=find(tag);
    if(order_.empty()||order_.front()!=tag||!o.ACK_received)
      throw std::logic_error("IRIS_STORE_OWNER_UNORDERED_RETIREMENT");
    auto copy=o;owners_[tag].reset();order_.pop_front();return copy;
  }
  bool pending()const{return !order_.empty();}
  unsigned outstanding()const{return order_.size();}
  static unsigned physical_store_source(unsigned tag) {
    if(tag>=16)throw std::invalid_argument("IRIS_STORE_SOURCE_TAG_WIDTH");
    return tag; // writer=input1 -> source[4]=0 in the bound saved TLXbar.
  }
 private:
  Owner&find(unsigned tag){
    if(tag>=16||!owners_[tag])throw std::logic_error("IRIS_STORE_OWNER_UNKNOWN_TAG");
    return *owners_[tag];
  }
  unsigned hart_,next_tag_=0;std::uint64_t generation_=0;
  std::array<std::optional<Owner>,16>owners_{};std::deque<unsigned>order_;
};
}
