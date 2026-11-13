#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <stdexcept>

namespace iris::frontend {
// Private timing values for the qualified30 pure scalar ALUs. This is not
// an architectural register file. Unknown inputs remain optional values;
// partial-bit knownness stays owned by Spike's existing functional policy.
struct PureAluValue {
  unsigned rd=0,rs1=0,rs2=0;
  bool uses_rs1=false,uses_rs2=false,word=false;
  uint32_t instruction=0;
  static std::optional<PureAluValue> decode(uint32_t x) {
    PureAluValue op;op.rd=(x>>7)&31;op.rs1=(x>>15)&31;op.rs2=(x>>20)&31;op.instruction=x;
    const unsigned code=x&127,f=(x>>12)&7,high=x>>25;
    if(code==0x37 || code==0x17)return op;
    op.uses_rs1=true;
    if(code==0x13) {
      if(f==1 && x>>26!=0)return {};
      if(f==5 && x>>26!=0 && x>>26!=16)return {};
      return op;
    }
    if(code==0x1b) {
      op.word=true;
      if(f==0 || (f==1 && high==0) || (f==5 && (high==0 || high==32)))return op;
      return {};
    }
    if(code==0x33 || code==0x3b) {
      op.word=code==0x3b;op.uses_rs2=true;
      if(op.word && f!=0 && f!=1 && f!=5)return {};
      if(high==0 || (high==32 && (f==0 || f==5)))return op;
    }
    return {};
  }
  static uint64_t sext(uint64_t value,unsigned bits) {
    value&=(uint64_t(1)<<bits)-1;
    return (value^(uint64_t(1)<<(bits-1)))-(uint64_t(1)<<(bits-1));
  }
  static uint64_t arithmetic_right(uint64_t value,unsigned shift) {
    if(!shift)return value;
    return (value>>shift)|((value>>63)?(~uint64_t(0)<<(64-shift)):0);
  }
  // pc is the caller's source-width sign-extended PC, not an invented fetch
  // address. Native integration must explicitly supply the per-hart width.
  uint64_t evaluate(uint64_t pc,uint64_t a,uint64_t b) const {
    const uint32_t x=instruction;const unsigned code=x&127,f=(x>>12)&7;
    if(code==0x37)return sext(x&0xfffff000,32);
    if(code==0x17)return pc+sext(x&0xfffff000,32);
    const bool immediate=code==0x13 || code==0x1b;
    const auto operand=immediate?sext(x>>20,12):b;
    const auto shift=unsigned(immediate?x>>20:b)&(word?31:63);
    uint64_t value=0;
    switch(f) {
      case 0:value=!immediate && (x>>25)==32?a-operand:a+operand;break;
      case 1:value=a<<shift;break;
      case 2:value=((a^operand)>>63)?a>>63:a<operand;break;
      case 3:value=a<operand;break;
      case 4:value=a^operand;break;
      case 5:
        if(x&(uint32_t(1)<<30))value=arithmetic_right(word?sext(a,32):a,shift);
        else value=(word?uint64_t(uint32_t(a)):a)>>shift;
        break;
      case 6:value=a|operand;break;
      case 7:value=a&operand;break;
    }
    return word?sext(value,32):value;
  }
};

class ForwardedValues {
 public:
  using Tag=uint64_t;
  using Value=std::optional<uint64_t>;
  using Snapshot=std::array<Value,32>;
  struct Source {std::optional<Tag> producer;Value snapshot;};
  struct Operands {Source rs1,rs2;};
  explicit ForwardedValues(Snapshot architectural):architectural_(architectural) {architectural_[0]=uint64_t(0);}
  Operands latch(unsigned rs1,unsigned rs2) const {return {source(rs1),source(rs2)};}
  std::array<Value,2> read(const Operands& operands) const {return {read(operands.rs1),read(operands.rs2)};}
  void issue(Tag tag,uint32_t instruction,uint64_t pc) {
    if(last_tag_ && tag<=*last_tag_)throw std::logic_error("IRIS_SHADOW_TAG_NOT_MONOTONIC");
    const auto decoded=PureAluValue::decode(instruction);
    if(!decoded)throw std::invalid_argument("IRIS_SHADOW_ALU_OUTSIDE_SOURCE_SUBSET");
    const auto operands=latch(decoded->uses_rs1?decoded->rs1:0,decoded->uses_rs2?decoded->rs2:0);
    records_.emplace(tag,Record{*decoded,pc,operands});last_tag_=tag;
    if(decoded->rd)last_writer_[decoded->rd]=tag;
  }
  void issue_external(Tag tag,unsigned rd) {
    if(rd>31 || (last_tag_ && tag<=*last_tag_))throw std::logic_error("IRIS_SHADOW_EXTERNAL_TAG_OR_REGISTER");
    PureAluValue op;op.rd=rd;Record row{op,0,latch(0,0)};row.external=true;
    records_.emplace(tag,std::move(row));last_tag_=tag;if(rd)last_writer_[rd]=tag;
  }
  void complete_external(Tag tag,Value value) {
    auto& row=record(tag);
    if(!row.external || row.ready)throw std::logic_error("IRIS_SHADOW_EXTERNAL_RESULT_PHASE");
    row.value=value;row.ready=true;
  }
  Value complete(Tag tag) {
    auto& row=record(tag);
    if(row.ready || row.external)throw std::logic_error("IRIS_SHADOW_RESULT_COMPLETED_TWICE_OR_EXTERNAL");
    const auto operands=read(row.operands);
    if(operands[0] && operands[1])row.value=row.op.evaluate(row.pc,*operands[0],*operands[1]);
    else {
      const auto word=row.op.instruction,kind=word&0xfe00707f;
      if(row.op.rs1==row.op.rs2 && (kind==0x40000033 || kind==0x4000003b || kind==0x4033))row.value=uint64_t(0);
      if((word&0x707f)==0x7013 && (word>>20)==0)row.value=uint64_t(0);
      if((word&0x707f)==0x6013 && (word>>20)==4095)row.value=~uint64_t(0);
    }
    row.ready=true;return row.value;
  }
  void commit(Tag tag,Value observed_architectural_result) {
    auto& row=record(tag);
    if(!row.ready || row.committed)throw std::logic_error("IRIS_SHADOW_COMMIT_NOT_READY_OR_DUPLICATE");
    for(const auto& [other,older]:records_)if(other<tag && !older.committed)throw std::logic_error("IRIS_SHADOW_COMMIT_OUT_OF_ORDER");
    if(row.op.rd && row.value && row.value!=observed_architectural_result)throw std::logic_error("IRIS_SHADOW_ARCHITECTURAL_RESULT_MISMATCH");
    if(row.op.rd) {architectural_[row.op.rd]=observed_architectural_result;row.value=observed_architectural_result;}
    row.committed=true;
  }
  // Cancellation affects only private register versions. It cannot undo an
  // accepted cache/refill/memory transaction or a completed guest effect.
  void discard_younger(Tag surviving) {
    if(!records_.count(surviving))throw std::logic_error("IRIS_SHADOW_CANCEL_ANCHOR_MISSING");
    for(auto it=records_.upper_bound(surviving);it!=records_.end();++it)
      if(it->second.committed)throw std::logic_error("IRIS_SHADOW_CANCEL_AFTER_ARCHITECTURAL_COMMIT");
    records_.erase(records_.upper_bound(surviving),records_.end());last_writer_={};
    for(const auto& [tag,row]:records_)if(row.op.rd)last_writer_[row.op.rd]=tag;
  }
  const Snapshot& architectural() const {return architectural_;}
  Value future(unsigned reg) const {return read(source(reg));}
 private:
  struct Record {PureAluValue op;uint64_t pc;Operands operands;bool ready=false,committed=false,external=false;Value value{};};
  Snapshot architectural_{};
  std::array<std::optional<Tag>,32> last_writer_{};
  std::map<Tag,Record> records_;
  std::optional<Tag> last_tag_;
  Source source(unsigned reg) const {
    if(reg>31)throw std::invalid_argument("IRIS_SHADOW_REGISTER_OUTSIDE_XPR");
    if(!reg)return {{},uint64_t(0)};
    return {last_writer_[reg],architectural_[reg]};
  }
  Value read(const Source& source) const {
    if(!source.producer)return source.snapshot;
    const auto found=records_.find(*source.producer);
    if(found==records_.end())throw std::logic_error("IRIS_SHADOW_CONSUMED_CANCELED_PRODUCER");
    if(!found->second.ready)throw std::logic_error("IRIS_SHADOW_CONSUMED_BEFORE_RESULT_READY");
    return found->second.value;
  }
  Record& record(Tag tag) {
    const auto found=records_.find(tag);
    if(found==records_.end())throw std::logic_error("IRIS_SHADOW_UNKNOWN_RESULT_TAG");
    return found->second;
  }
};
}
