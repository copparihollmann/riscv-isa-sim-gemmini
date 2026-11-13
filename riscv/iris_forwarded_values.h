#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <memory>
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
 private:
  struct Counts {size_t cells=0,peak_cells=0,peak_records=0;};
  struct Cell {
    Tag tag;
    bool ready=false,canceled=false;
    Value value;
    std::shared_ptr<Counts> counts;
    Cell(Tag tag,std::shared_ptr<Counts> counts):tag(tag),counts(std::move(counts)) {
      ++this->counts->cells;this->counts->peak_cells=std::max(this->counts->peak_cells,this->counts->cells);
    }
    ~Cell() {--counts->cells;}
  };
 public:
  struct Source {std::shared_ptr<const Cell> producer;Value snapshot;};
  struct Operands {Source rs1,rs2;};
  ForwardedValues(Snapshot architectural,size_t maximum_live):architectural_(architectural),maximum_live_(maximum_live) {
    if(!maximum_live || maximum_live>1024)throw std::invalid_argument("IRIS_SHADOW_EXPLICIT_CAPACITY_REQUIRED");
    architectural_[0]=uint64_t(0);
  }
  Operands latch(unsigned rs1,unsigned rs2) const {return {source(rs1),source(rs2)};}
  std::array<Value,2> read(const Operands& operands) const {return {read(operands.rs1),read(operands.rs2)};}
  void issue(Tag tag,uint32_t instruction,uint64_t pc) {
    const auto decoded=PureAluValue::decode(instruction);
    if(!decoded)throw std::invalid_argument("IRIS_SHADOW_ALU_OUTSIDE_SOURCE_SUBSET");
    const auto operands=latch(decoded->uses_rs1?decoded->rs1:0,decoded->uses_rs2?decoded->rs2:0);
    insert(tag,*decoded,pc,operands,false);
  }
  void issue_external(Tag tag,unsigned rd) {
    if(rd>31)throw std::invalid_argument("IRIS_SHADOW_REGISTER_OUTSIDE_XPR");
    PureAluValue op;op.rd=rd;insert(tag,op,0,latch(0,0),true);
  }
  void complete_external(Tag tag,Value value) {
    auto& row=record(tag);
    if(!row.external || row.cell->ready)throw std::logic_error("IRIS_SHADOW_EXTERNAL_RESULT_PHASE");
    row.cell->value=value;row.cell->ready=true;
  }
  Value complete(Tag tag) {
    auto& row=record(tag);
    if(row.cell->ready || row.external)throw std::logic_error("IRIS_SHADOW_RESULT_COMPLETED_TWICE_OR_EXTERNAL");
    const auto operands=read(row.operands);
    if(operands[0] && operands[1])row.cell->value=row.op.evaluate(row.pc,*operands[0],*operands[1]);
    else {
      const auto word=row.op.instruction,kind=word&0xfe00707f;
      if(row.op.rs1==row.op.rs2 && (kind==0x40000033 || kind==0x4000003b || kind==0x4033))row.cell->value=uint64_t(0);
      if((word&0x707f)==0x7013 && (word>>20)==0)row.cell->value=uint64_t(0);
      if((word&0x707f)==0x6013 && (word>>20)==4095)row.cell->value=~uint64_t(0);
    }
    row.cell->ready=true;row.operands={};return row.cell->value;
  }
  void commit(Tag tag,Value observed) {
    // Only uncommitted records are retained. Checking the first key is
    // constant time and does not scan any retired instruction history.
    if(records_.empty() || records_.begin()->first!=tag)throw std::logic_error("IRIS_SHADOW_COMMIT_OUT_OF_ORDER");
    auto it=records_.begin();auto& row=it->second;
    if(!row.cell->ready)throw std::logic_error("IRIS_SHADOW_COMMIT_NOT_READY");
    if(row.op.rd && row.cell->value && row.cell->value!=observed)throw std::logic_error("IRIS_SHADOW_ARCHITECTURAL_RESULT_MISMATCH");
    if(row.op.rd) {
      architectural_[row.op.rd]=observed;row.cell->value=observed;
      if(last_writer_[row.op.rd]==row.cell)last_writer_[row.op.rd].reset();
    }
    last_committed_=tag;
    // Operand/branch handles own the result cell when still needed. Erasing
    // the record cannot invalidate a latched producer or retain its history.
    records_.erase(it);
  }
  void discard_younger(Tag surviving) {
    if(last_committed_ && surviving<*last_committed_)throw std::logic_error("IRIS_SHADOW_CANCEL_AFTER_ARCHITECTURAL_COMMIT");
    if(!records_.count(surviving) && (!last_committed_ || surviving!=*last_committed_))throw std::logic_error("IRIS_SHADOW_CANCEL_ANCHOR_MISSING");
    for(auto it=records_.upper_bound(surviving);it!=records_.end();++it)it->second.cell->canceled=true;
    records_.erase(records_.upper_bound(surviving),records_.end());last_writer_={};
    for(const auto& [tag,row]:records_)if(row.op.rd)last_writer_[row.op.rd]=row.cell;
  }
  const Snapshot& architectural() const {return architectural_;}
  Value future(unsigned reg) const {return read(source(reg));}
  size_t retained_records() const {return records_.size();}
  size_t live_cells() const {return counts_->cells;}
  size_t peak_records() const {return counts_->peak_records;}
  size_t peak_cells() const {return counts_->peak_cells;}
 private:
  struct Record {PureAluValue op;uint64_t pc;Operands operands;std::shared_ptr<Cell> cell;bool external=false;};
  Snapshot architectural_{};
  size_t maximum_live_;
  std::shared_ptr<Counts> counts_=std::make_shared<Counts>();
  std::array<std::shared_ptr<Cell>,32> last_writer_{};
  std::map<Tag,Record> records_;
  std::optional<Tag> last_tag_,last_committed_;
  void insert(Tag tag,PureAluValue op,uint64_t pc,Operands operands,bool external) {
    if(last_tag_ && tag<=*last_tag_)throw std::logic_error("IRIS_SHADOW_TAG_NOT_MONOTONIC");
    if(records_.size()>=maximum_live_ || counts_->cells>=maximum_live_*3)throw std::logic_error("IRIS_SHADOW_EXPLICIT_LIVE_CAPACITY_EXCEEDED");
    auto cell=std::make_shared<Cell>(tag,counts_);records_.emplace(tag,Record{op,pc,operands,cell,external});last_tag_=tag;
    counts_->peak_records=std::max(counts_->peak_records,records_.size());if(op.rd)last_writer_[op.rd]=cell;
  }
  Source source(unsigned reg) const {
    if(reg>31)throw std::invalid_argument("IRIS_SHADOW_REGISTER_OUTSIDE_XPR");
    if(!reg)return {{},uint64_t(0)};
    return {last_writer_[reg],architectural_[reg]};
  }
  Value read(const Source& source) const {
    if(!source.producer)return source.snapshot;
    if(source.producer->canceled)throw std::logic_error("IRIS_SHADOW_CONSUMED_CANCELED_PRODUCER");
    if(!source.producer->ready)throw std::logic_error("IRIS_SHADOW_CONSUMED_BEFORE_RESULT_READY");
    return source.producer->value;
  }
  Record& record(Tag tag) {
    const auto found=records_.find(tag);
    if(found==records_.end())throw std::logic_error("IRIS_SHADOW_UNKNOWN_RESULT_TAG");
    return found->second;
  }
};
}
