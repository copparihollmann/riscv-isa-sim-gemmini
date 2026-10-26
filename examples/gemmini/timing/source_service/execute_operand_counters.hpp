#ifndef GEMMINI_EXECUTE_OPERAND_COUNTERS_HPP
#define GEMMINI_EXECUTE_OPERAND_COUNTERS_HPP
#include <array>
#include <cstdint>
#include <stdexcept>
namespace gemmini_annotated_spike {
// ExecuteController.scala310-409, selected non-transposed WS/SP domain.
// `ready` and `control_ready` are actual handshakes from the finite SRAM /
// control pipelines. This component supplies no independent latency or credit.
class ExecuteOperandCounters {
 public:
 struct Operand {std::uint32_t address=0;unsigned rows=0;bool garbage=true,active=false;};
 struct Request {unsigned operand,bank,row;};
 struct Signals {
   std::array<bool,3>valid{},fire{},physical{};
   std::array<Request,3>request{};
   bool last=false;
 };
 private:
 std::array<Operand,3>operands_;
 std::array<unsigned,3>counter_{};
 std::array<bool,3>started_{};
 unsigned total_,dim_,bank_rows_,bank_count_;
 bool complete_=false;
 unsigned next(unsigned x)const{return x+1==total_?0:x+1;}
 public:
 ExecuteOperandCounters(std::array<Operand,3>operands,unsigned total,unsigned dim,
                        unsigned bank_rows,unsigned bank_count)
 :operands_(operands),total_(total),dim_(dim),bank_rows_(bank_rows),bank_count_(bank_count){
   if(dim!=16||total<4||total>dim||!bank_rows||!bank_count)
     throw std::invalid_argument("operand counters require selected WS geometry and floor4");
   for(const auto&o:operands_)if(o.rows>dim||(!o.garbage&&o.address>=std::uint64_t(bank_rows)*bank_count))
     throw std::invalid_argument("operand counters require source-bound SP row addresses");
 }
 const auto&counters()const{return counter_;}
 const auto&started()const{return started_;}
 unsigned total_rows()const{return total_;}
 bool complete()const{return complete_;}
 Signals signals(std::array<bool,3>ready,bool control_ready)const{
   if(complete_)throw std::logic_error("operand source already consumed");
   Signals s;
   std::array<unsigned,3>address{};
   for(unsigned i=0;i<3;++i){
     address[i]=operands_[i].address+(i==2?dim_-1-counter_[i]:counter_[i]);
     s.request[i]={i,address[i]/bank_rows_,address[i]%bank_rows_};
   }
   for(unsigned i=0;i<3;++i){
     s.valid[i]=true;
     for(unsigned j=0;j<3;++j)if(i!=j){
       const bool same_bank=operands_[i].active&&operands_[j].active&&
         !operands_[i].garbage&&!operands_[j].garbage&&address[i]/bank_rows_==address[j]/bank_rows_;
       const bool same_counter=started_[i]==started_[j]&&counter_[i]==counter_[j];
       // Source intentionally includes garbage/disabled/padded operands in
       // the one-ahead guard. Only equal-counter port priority tests garbage.
       const bool one_ahead=started_[i]&&counter_[i]==next(counter_[j]);
       if((same_bank&&j<i&&same_counter)||one_ahead)s.valid[i]=false;
     }
     const bool unpadded=i==2?dim_-1-counter_[i]<operands_[i].rows:counter_[i]<operands_[i].rows;
     s.physical[i]=s.valid[i]&&operands_[i].active&&!operands_[i].garbage&&unpadded;
     if(s.physical[i]&&s.request[i].bank>=bank_count_)
       throw std::invalid_argument("operand row crosses actual scratchpad capacity");
     s.fire[i]=s.valid[i]&&(!s.physical[i]||ready[i]);
   }
   s.last=control_ready&&(started_[0]||started_[1]||started_[2]);
   for(unsigned i=0;i<3;++i)s.last=s.last&&((counter_[i]==total_-1&&s.fire[i])||counter_[i]==0);
   return s;
 }
 Signals step(std::array<bool,3>ready,bool control_ready){
   auto s=signals(ready,control_ready);
   const bool firing=operands_[0].active||operands_[1].active||operands_[2].active;
   for(unsigned i=0;i<3;++i){
     if(!firing){counter_[i]=0;started_[i]=false;}
     else if(s.fire[i]&&control_ready){counter_[i]=next(counter_[i]);started_[i]=true;}
   }
   if(s.last){started_.fill(false);complete_=true;}
   return s;
 }
};
}
#endif
