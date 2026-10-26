#ifndef GEMMINI_POSTED_ACCUMULATOR_HPP
#define GEMMINI_POSTED_ACCUMULATOR_HPP
#include <merlin_timing/posted_timeline.hpp>
#include <deque>
#include <functional>
namespace gemmini_annotated_spike {
// Selected AccumulatorMem, acc_singleported=false, acc_latency=2. Each
// physical bank has one read and one write port. RMW uses the read port on
// write acceptance; the write itself publishes two edges later. Registered
// pipelined_writes blocks reads and RMW to its address INCLUDING its final
// publication edge. Plain writes can overlap unrelated reads and old writes.
class PostedAccumulator {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
 public:using Accept=std::function<void(Cycle)>;using Ready=std::function<bool(Cycle)>;
 private:
 struct Request{std::uint64_t row;bool write,rmw,execute;Ready ready;Accept accepted;};
 struct Write{std::uint64_t row;Cycle accepted;};
 struct Bank{std::deque<Request>reads,writes;std::deque<Write>pipeline;};
 Q&q_;std::uint64_t rows_;std::vector<Bank>banks_;
 std::optional<Cycle>scheduled_,settled_;
 void kick(Cycle at){
   if(scheduled_&&*scheduled_<=at)return;
   scheduled_=at;
   q_.post_settled(at,{},[this,at](auto&,auto t){if(scheduled_!=std::optional<Cycle>{at})return;scheduled_.reset();settle(t);},Q::Kind::operand_consume);
 }
 void settle(Cycle at){
   settled_=at;bool pending=false;unsigned rmws=0;
   for(auto&b:banks_){
     while(!b.pipeline.empty()&&b.pipeline.front().accepted+2<at)b.pipeline.pop_front();
     const auto hazard=[&](std::uint64_t row){for(const auto&w:b.pipeline)if(w.row==row)return true;return false;};
     // io.read.req.ready sees write.valid && write.bits.acc, including a
     // write blocked by the same-address pipeline hazard.
     const bool accumulating=!b.writes.empty()&&b.writes.front().rmw;
     std::optional<std::uint64_t>written;
     if(!b.writes.empty()){
       auto&r=b.writes.front();
       if((!r.rmw||!hazard(r.row))&&r.ready(at)){
         if(r.rmw&&++rmws>1){q_.fail("shared ACC adder has simultaneous RMW owners");return;}
         auto fire=std::move(r.accepted);written=r.row;b.pipeline.push_back({r.row,at});b.writes.pop_front();fire(at);
       }
     }
     if(!accumulating&&!b.reads.empty()){
       auto&r=b.reads.front();
       if(written!=std::optional<std::uint64_t>{r.row}&&!hazard(r.row)&&r.ready(at)){
         auto fire=std::move(r.accepted);b.reads.pop_front();fire(at);
       }
     }
     pending|=!b.reads.empty()||!b.writes.empty();
   }
   if(pending)kick(at+1);
 }
 public:
 PostedAccumulator(Q&q,std::size_t banks,std::uint64_t rows):q_(q),rows_(rows),banks_(banks){
   if(!banks||!rows)throw std::invalid_argument("selected accumulator bank geometry required");
 }
 void offer(std::uint64_t row,bool write,bool rmw,Ready ready,Accept accepted,Cycle at,bool execute=false){
   if(row/rows_>=banks_.size()||(!write&&rmw)||!ready||!accepted){q_.fail("invalid accumulator row request");return;}
   q_.post(at,{},[this,row,write,rmw,execute,ready=std::move(ready),accepted=std::move(accepted)](auto&,auto t)mutable{
     // Requests enabled by a registered response after this edge settles
     // become visible next edge; already offered owners retain their place.
     if(settled_==std::optional<Cycle>{t}){
       offer(row,write,rmw,std::move(ready),std::move(accepted),t+1,execute);return;
     }
     auto&b=banks_.at(row/rows_);auto&pending=write?b.writes:b.reads;
     if(pending.size()>=65536){q_.fail("accumulator software owner custody bound");return;}
     Request r{row,write,rmw,execute,std::move(ready),std::move(accepted)};
     if(execute)pending.push_front(std::move(r));else pending.push_back(std::move(r));kick(t);
   },Q::Kind::source_arrival);
 }
};
}
#endif
