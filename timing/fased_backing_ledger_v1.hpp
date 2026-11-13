#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <deque>
#include <map>
#include <optional>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>

namespace iris::fased_backing {
// Functional ownership only. No latency, readiness or target clock is invented.
// Memory commits at B acceptance are observable only after an explicit external
// fence checkpoint. This is not the full FASED host ingress/token/DRAM model.
struct Bits {std::uint64_t value=0,known=0;};
inline std::uint64_t mask(unsigned width){if(!width||width>64)throw std::invalid_argument("IRIS_FASED_BACKING_BIT_WIDTH");return width==64?~std::uint64_t(0):(std::uint64_t(1)<<width)-1;}
inline Bits known(unsigned width,std::uint64_t value){return {value,mask(width)};}
struct Request {
  Bits address,id,len,size,burst,lock;
  static Request concrete(std::uint64_t address,unsigned id,unsigned len,unsigned size=3,unsigned burst=1,bool lock=false){
    return {known(33,address),known(4,id),known(8,len),known(3,size),known(2,burst),known(1,lock)};
  }
};
struct WBeat {
  Bits data,strobe,last;
  static WBeat concrete(std::uint64_t data,unsigned strobe,bool last){return {known(64,data),known(8,strobe),known(1,last)};}
};
struct Domain {std::uint64_t base,bytes;};
struct Byte {std::uint8_t value,known;};
struct ReadPayload {unsigned id;std::uint64_t data,known;bool last;};
struct Step {
  std::optional<Request>ar{},aw{};
  std::optional<WBeat>w{};
  bool r_fire=false,b_fire=false;
  std::optional<Bits>read_egress{},write_egress{};
};
enum class Visibility {ExternalFencedDisjoint};

class Ledger {
  struct Address {std::uint64_t address;unsigned id,len;};
  struct ReadOwner {std::uint64_t sequence;Address address;std::vector<std::uint64_t>data;unsigned beat=0;};
  struct WriteOwner {std::uint64_t sequence;Address address;std::vector<WBeat>data;};
  struct Word {std::uint64_t value=0,known=0;};
  struct State {
    std::uint64_t next_sequence=0;
    std::deque<ReadOwner>reads;
    std::deque<WriteOwner>aws,writes;
    std::deque<std::vector<WBeat>>completed_w;
    std::vector<WBeat>partial_w;
    std::optional<ReadOwner>active_r;
    std::optional<WriteOwner>active_b;
    std::map<std::uint64_t,Address>live_reads,live_writes;
    unsigned complete_w_count=0,retained_w_beats=0;
    std::vector<std::pair<std::uint64_t,std::uint64_t>>writes_since_fence;
  };
  std::vector<Domain>domains_;
  unsigned read_capacity_,write_capacity_;
  State state_;
  std::map<std::uint64_t,Word>memory_;
  bool initialization_open_=true;
  std::uint64_t edges_=0,accepted_ar_=0,accepted_aw_=0,accepted_w_=0,accepted_b_=0,accepted_r_=0,fences_=0,written_bytes_=0;

  static void require(bool value,const char*message){if(!value)throw std::runtime_error(message);}
  static std::uint64_t bits(Bits value,unsigned width){
    const auto m=mask(width);
    require(!(value.value&~m)&&!(value.known&~m),"IRIS_FASED_BACKING_EXCESS_FIELD_WIDTH");
    require(value.known==m,"IRIS_FASED_BACKING_UNKNOWN_REQUIRED_FIELD");return value.value;
  }
  void mapped(std::uint64_t address,std::uint64_t bytes)const{
    require(bytes&&address<(std::uint64_t(1)<<33)&&bytes<=(std::uint64_t(1)<<33)-address,"IRIS_FASED_BACKING_ADDRESS_OVERFLOW");
    require(std::any_of(domains_.begin(),domains_.end(),[&](const auto&d){return address>=d.base&&address-d.base<=d.bytes&&bytes<=d.bytes-(address-d.base);}),"IRIS_FASED_BACKING_UNMAPPED_BYTES");
  }
  Address address(const Request&r)const{
    const auto a=bits(r.address,33);const auto id=bits(r.id,4),len=bits(r.len,8),size=bits(r.size,3),burst=bits(r.burst,2),lock=bits(r.lock,1);
    require(len<8&&size==3&&burst==1&&lock==0&&(a&7)==0,"IRIS_FASED_BACKING_FULL64_INCR_SCOPE");
    const auto bytes=(len+1)*8;mapped(a,bytes);
    require((a>>12)==((a+bytes-1)>>12),"IRIS_FASED_BACKING_4K_CROSSING");
    return {a,unsigned(id),unsigned(len)};
  }
  static std::pair<std::uint64_t,std::uint64_t>lines(const Address&a){return {a.address&~std::uint64_t(63),(a.address+(a.len+1)*8-1)&~std::uint64_t(63)};}
  static bool overlaps(const Address&a,const Address&b){auto x=lines(a),y=lines(b);return x.first<=y.second&&y.first<=x.second;}
  static void visibility(const State&s,const Address&a){
    const auto x=lines(a);
    for(const auto&y:s.writes_since_fence)require(!(x.first<=y.second&&y.first<=x.second),"IRIS_FASED_BACKING_EXTERNAL_FENCE_REQUIRED");
  }
  static void w_valid(const WBeat&w){
    const auto strobe=bits(w.strobe,8);bits(w.last,1);
    for(unsigned byte=0;byte<8;++byte)if(strobe&(1u<<byte))require(((w.data.known>>(8*byte))&255)==255,"IRIS_FASED_BACKING_UNKNOWN_STROBED_BYTE");
  }
  static bool empty(const State&s){return s.live_reads.empty()&&s.live_writes.empty()&&s.completed_w.empty()&&s.partial_w.empty()&&s.reads.empty()&&s.aws.empty()&&s.writes.empty()&&!s.active_r&&!s.active_b&&!s.complete_w_count&&!s.retained_w_beats;}
  std::uint64_t snapshot(std::uint64_t address)const{
    mapped(address,8);const auto i=memory_.find(address);require(i!=memory_.end()&&i->second.known==~std::uint64_t(0),"IRIS_FASED_BACKING_UNDEFINED_READ_BYTES");return i->second.value;
  }
  static void pair_writes(State&s){
    while(!s.aws.empty()&&!s.completed_w.empty()){
      auto owner=s.aws.front();auto data=s.completed_w.front();
      require(data.size()==owner.address.len+1,"IRIS_FASED_BACKING_AWLEN_WLAST_MISMATCH");
      for(unsigned beat=0;beat<data.size();++beat){w_valid(data[beat]);require(bool(data[beat].last.value)==(beat+1==data.size()),"IRIS_FASED_BACKING_WLAST_POSITION");}
      owner.data=std::move(data);s.writes.push_back(std::move(owner));s.aws.pop_front();s.completed_w.pop_front();
    }
  }

 public:
  Ledger(std::vector<Domain>domains,unsigned read_capacity,unsigned write_capacity,Visibility policy):domains_(std::move(domains)),read_capacity_(read_capacity),write_capacity_(write_capacity){
    require(policy==Visibility::ExternalFencedDisjoint,"IRIS_FASED_BACKING_EXPLICIT_VISIBILITY_POLICY");
    require(read_capacity&&read_capacity<=16&&write_capacity&&write_capacity<=16,"IRIS_FASED_BACKING_EXPLICIT_CAPACITY_ENVELOPE");
    require(!domains_.empty(),"IRIS_FASED_BACKING_EXPLICIT_DOMAIN_REQUIRED");
    std::sort(domains_.begin(),domains_.end(),[](auto a,auto b){return a.base<b.base;});
    std::uint64_t end=0;for(const auto&d:domains_){require(d.bytes&&d.base<(std::uint64_t(1)<<33)&&d.bytes<=(std::uint64_t(1)<<33)-d.base&&d.base>=end,"IRIS_FASED_BACKING_INVALID_OR_OVERLAPPING_DOMAINS");end=d.base+d.bytes;}
  }
  void initialize(std::uint64_t address,std::span<const Byte>data){
    require(initialization_open_&&state_.next_sequence==0&&empty(state_),"IRIS_FASED_BACKING_LATE_INITIALIZATION_FORBIDDEN");mapped(address,data.size());
    auto next=memory_;
    for(std::size_t i=0;i<data.size();++i){const auto a=address+i;auto&w=next[a&~std::uint64_t(7)];const auto shift=(a&7)*8,m=std::uint64_t(255)<<shift;w.value=(w.value&~m)|(std::uint64_t(data[i].value)<<shift);w.known=(w.known&~m)|(std::uint64_t(data[i].known)<<shift);}
    memory_=std::move(next);
  }
  Byte inspect(std::uint64_t address)const{
    mapped(address,1);const auto p=memory_.find(address&~std::uint64_t(7));if(p==memory_.end())return {0,0};const auto shift=(address&7)*8;return {std::uint8_t(p->second.value>>shift),std::uint8_t(p->second.known>>shift)};
  }
  std::optional<ReadPayload>read_payload()const{
    if(!state_.active_r)return{};
    const auto&a=*state_.active_r;return ReadPayload{a.address.id,a.data.at(a.beat),~std::uint64_t(0),a.beat==a.address.len};
  }
  std::optional<unsigned>write_payload()const{return state_.active_b?std::optional<unsigned>(state_.active_b->address.id):std::nullopt;}
  bool idle()const{return empty(state_);}
  unsigned read_count()const{return state_.live_reads.size();}
  unsigned write_count()const{return state_.live_writes.size();}
  unsigned complete_w_count()const{return state_.complete_w_count;}
  std::uint64_t committed_edges()const{return edges_;}
  std::uint64_t written_bytes()const{return written_bytes_;}
  std::uint64_t fence_checkpoints()const{return fences_;}
  void reset(std::uint64_t edge){require(edge==edges_,"IRIS_FASED_BACKING_STALE_EDGE");initialization_open_=false;require(idle(),"IRIS_FASED_BACKING_RESET_WITH_OWNED_TRANSACTIONS");++edges_;}
  void acknowledge_external_fence(){
    // Caller-supplied, explicitly scoped boundary. This is not a simulation
    // of a RISC-V FENCE and does not prove dirty caches have been written back.
    require(idle(),"IRIS_FASED_BACKING_FENCE_WITH_OWNED_TRANSACTIONS");state_.writes_since_fence.clear();++fences_;
  }
  void advance(std::uint64_t edge,const Step&e){
    require(edge==edges_,"IRIS_FASED_BACKING_STALE_EDGE");
    initialization_open_=false;
    if(!e.ar&&!e.aw&&!e.w&&!e.r_fire&&!e.b_fire&&!e.read_egress&&!e.write_egress){++edges_;return;}
    auto next=state_;
    // All new requests see preedge live owners, even if a response is also
    // accepted now. This deliberately refuses unqualified same-edge RAW/WAW.
    if(e.aw){const auto a=address(*e.aw);visibility(next,a);require(state_.live_writes.size()<write_capacity_,"IRIS_FASED_BACKING_AW_CAPACITY");
      for(const auto&[id,b]:next.live_reads)require(!overlaps(a,b),"IRIS_FASED_BACKING_LIVE_WRITE_READ_LINE_CONFLICT");
      for(const auto&[id,b]:next.live_writes)require(!overlaps(a,b),"IRIS_FASED_BACKING_LIVE_WRITE_WRITE_LINE_CONFLICT");
      const auto seq=next.next_sequence++;next.live_writes.emplace(seq,a);next.aws.push_back({seq,a,{}});}
    if(e.w){w_valid(*e.w);require(state_.complete_w_count<write_capacity_&&next.retained_w_beats<write_capacity_*8,"IRIS_FASED_BACKING_W_CAPACITY");
      require(next.partial_w.size()<8,"IRIS_FASED_BACKING_W_BURST_BOUND");next.partial_w.push_back(*e.w);++next.retained_w_beats;
      if(e.w->last.value){next.completed_w.push_back(std::move(next.partial_w));next.partial_w.clear();++next.complete_w_count;}
      else require(next.partial_w.size()<8,"IRIS_FASED_BACKING_MISSING_WLAST");}
    pair_writes(next);
    if(e.ar){const auto a=address(*e.ar);visibility(next,a);require(state_.live_reads.size()<read_capacity_,"IRIS_FASED_BACKING_AR_CAPACITY");
      require(next.partial_w.empty()&&next.completed_w.empty(),"IRIS_FASED_BACKING_READ_WITH_UNOWNED_W_DATA");
      for(const auto&[id,b]:next.live_writes)require(!overlaps(a,b),"IRIS_FASED_BACKING_LIVE_READ_WRITE_LINE_CONFLICT");
      ReadOwner owner{next.next_sequence++,a,{}};for(unsigned beat=0;beat<=a.len;++beat)owner.data.push_back(snapshot(a.address+8*beat));
      next.live_reads.emplace(owner.sequence,a);next.reads.push_back(std::move(owner));}
    if(e.r_fire){require(bool(next.active_r),"IRIS_FASED_BACKING_UNOWNED_R_ACCEPTANCE");auto&a=*next.active_r;if(a.beat++==a.address.len){next.live_reads.erase(a.sequence);next.active_r.reset();}}
    std::optional<WriteOwner>publish;
    if(e.b_fire){require(bool(next.active_b),"IRIS_FASED_BACKING_UNOWNED_B_ACCEPTANCE");publish=*next.active_b;next.live_writes.erase(publish->sequence);require(next.complete_w_count>0&&next.retained_w_beats>=publish->data.size(),"IRIS_FASED_BACKING_LOST_W_CREDIT");--next.complete_w_count;next.retained_w_beats-=publish->data.size();next.writes_since_fence.push_back(lines(publish->address));next.active_b.reset();}
    if(e.read_egress){const auto id=bits(*e.read_egress,4);require(!next.active_r&&!next.reads.empty()&&next.reads.front().address.id==id,"IRIS_FASED_BACKING_READ_EGRESS_OWNER");next.active_r=std::move(next.reads.front());next.reads.pop_front();}
    if(e.write_egress){const auto id=bits(*e.write_egress,4);require(!next.active_b&&!next.writes.empty()&&next.writes.front().address.id==id,"IRIS_FASED_BACKING_WRITE_EGRESS_OWNER");next.active_b=std::move(next.writes.front());next.writes.pop_front();}
    // Prepare the entire memory update before changing any live state. Reads
    // of these lines still require the explicit external fence checkpoint.
    if(publish){auto memory=memory_;std::uint64_t changed=0;
      for(unsigned beat=0;beat<publish->data.size();++beat){const auto a=publish->address.address+8*beat;const auto&b=publish->data[beat];auto&w=memory[a];
        for(unsigned byte=0;byte<8;++byte)if(b.strobe.value&(1u<<byte)){const auto shift=8*byte;const auto m=std::uint64_t(255)<<shift;w.value=(w.value&~m)|(b.data.value&m);w.known|=m;++changed;}}
      memory_=std::move(memory);written_bytes_+=changed;}
    state_=std::move(next);++edges_;accepted_ar_+=bool(e.ar);accepted_aw_+=bool(e.aw);accepted_w_+=bool(e.w);accepted_r_+=e.r_fire;accepted_b_+=e.b_fire;
  }
};
}
