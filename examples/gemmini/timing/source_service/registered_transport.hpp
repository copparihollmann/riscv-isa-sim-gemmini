#ifndef GEMMINI_POSTED_REGISTERED_TRANSPORT_HPP
#define GEMMINI_POSTED_REGISTERED_TRANSPORT_HPP
#include <merlin_timing/posted_timeline.hpp>
#include <deque>
#include <memory>
namespace gemmini_annotated_spike {
// TileLink D arbitration owns an ORIGINAL message, not independently
// arbitrated beats. This is an ordering obligation, not another hardware
// queue/credit or a latency. The owner releases it on its actual last D.fire;
// missing/stalled beats therefore keep later packets backpressured.
// Selected source: tilelink/Arbiter.scala beatsLeft/muxState; DMA.scala
// StreamReader binds XactTracker.peek through BeatMerger until last D.fire.
class PostedPacketLock {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;using Token=Q::Token;
 Q&q_;std::optional<Token>last_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("packet ownership token bound");return *t;}
 public:
 struct Packet{Token admitted,released;};
 explicit PostedPacketLock(Q&q):q_(q){}
 Packet acquire(Cycle at){
   Packet p{token(),token()};std::vector<Token>deps;if(last_)deps.push_back(*last_);last_=p.released;
   q_.post(at,std::move(deps),[admitted=p.admitted](auto&q,auto){q.complete(admitted);},Q::Kind::response_beat);
   return p;
 }
};
// Finite non-flow registered queues. A pipe queue may reuse a dequeue credit
// on that edge; a non-pipe FULL queue can reuse it only on the next edge.
// Consumers own their completion token until the actual downstream handshake.
// This supplies transport only, never cache latency or a DMA completion fee.
class PostedRegisteredTransport {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;using Token=Q::Token;
 public:
 struct Spec{std::size_t entries;bool pipe;};
 using Sink=std::function<void(Cycle,Token)>;
 private:
 struct Item{Sink sink;Token accepted;Cycle visible;bool started=false;};
 struct Waiting{Sink sink;Token accepted;};
 struct Queue{Spec spec;std::deque<std::shared_ptr<Item>>items;std::deque<Waiting>waiting;
   std::optional<Cycle>last_enqueue,full_dequeue,last_dequeue,previous_enqueue,previous_dequeue;std::size_t peak=0;};
 Q&q_;std::vector<Queue>queues_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("registered transport token budget");return *t;}
 bool available(const Queue&v,Cycle at)const{return v.items.size()<v.spec.entries&&v.last_enqueue!=std::optional<Cycle>{at}&&
   (v.spec.pipe||v.full_dequeue!=std::optional<Cycle>{at});}
 void wake(std::size_t i,Cycle at){
   auto &v=queues_[i];if(v.waiting.empty())return;
   if(!available(v,at)){if(v.items.size()<v.spec.entries)q_.post(at+1,{},[this,i](auto&,auto t){wake(i,t);},Q::Kind::source_arrival);return;}
   auto w=std::move(v.waiting.front());v.waiting.pop_front();enqueue(i,std::move(w),at);
   if(!v.waiting.empty())q_.post(at+1,{},[this,i](auto&,auto t){wake(i,t);},Q::Kind::source_arrival);
 }
 void enqueue(std::size_t i,Waiting w,Cycle at){
   auto &v=queues_[i];v.items.push_back(std::make_shared<Item>(Item{std::move(w.sink),w.accepted,at+1,false}));
   v.previous_enqueue=v.last_enqueue;v.last_enqueue=at;v.peak=std::max(v.peak,v.items.size());q_.complete(w.accepted);kick(i,at);
 }
 Token offer(std::size_t i,Sink sink,Cycle at){
   auto accepted=token();q_.post(std::max(at,q_.now()),{},[this,i,sink=std::move(sink),accepted](auto&,auto time)mutable{
     auto &v=queues_[i];Waiting w{std::move(sink),accepted};
     if(v.waiting.empty()&&available(v,time))enqueue(i,std::move(w),time);
     else{if(v.waiting.size()>=16){q_.fail("registered transport source bound");return;}v.waiting.push_back(std::move(w));wake(i,time);}
   },Q::Kind::source_arrival);return accepted;
 }
 void kick(std::size_t i,Cycle at){
   auto &v=queues_[i];if(v.items.empty()||v.items.front()->started)return;
   if(v.last_dequeue==std::optional<Cycle>{at}){
     q_.post(at+1,{},[this,i](auto&,auto t){kick(i,t);},Q::Kind::source_arrival);return;
   }
   auto item=v.items.front();item->started=true;
   q_.post(std::max(at,item->visible),{},[this,i,item](auto&,auto time){
     auto consumed=token();
     if(i+1<queues_.size()){
       auto accepted=offer(i+1,item->sink,time);
       q_.post(time,{accepted},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::source_arrival);
     }else item->sink(time,consumed);
     q_.post(time,{consumed},[this,i,item](auto&,auto t){
       auto &v=queues_[i];if(v.items.empty()||v.items.front()!=item){q_.fail("registered transport FIFO identity");return;}
       const bool full=v.items.size()==v.spec.entries;v.items.pop_front();if(full)v.full_dequeue=t;
       v.previous_dequeue=v.last_dequeue;v.last_dequeue=t;
       wake(i,t);kick(i,t);
     },Q::Kind::source_arrival);
   },Q::Kind::source_arrival);
 }
 public:
 PostedRegisteredTransport(Q&q,std::vector<Spec>specs):q_(q){
   if(specs.empty()||specs.size()>16)throw std::invalid_argument("registered transport stage bound");
   for(auto spec:specs){if(!spec.entries||spec.entries>16)throw std::invalid_argument("registered transport capacity");queues_.push_back(Queue{spec,{},{},{},{},{},{},{},0});}
 }
 Token push(Sink sink,Cycle at){if(!sink)throw std::invalid_argument("registered transport requires consumer");return offer(0,std::move(sink),at);}
 std::vector<std::size_t>peaks()const{std::vector<std::size_t>out;for(const auto&v:queues_)out.push_back(v.peak);return out;}
 bool busy()const{for(const auto&v:queues_)if(!v.items.empty()||!v.waiting.empty())return true;return false;}
 struct EdgeActivity{std::size_t begin,end;bool enqueued,dequeued;};
 // Read-only previous-edge state, sufficient for an owning RTL actor's
 // registered ready equation. No new queue capacity or hidden latency.
 EdgeActivity previous_edge(std::size_t index,Cycle at)const{
   const auto&v=queues_.at(index);if(at!=q_.now())throw std::invalid_argument("queue edge query is not current");
   if(!at)return {0,0,false,false};
   const auto enq=[&](Cycle t){return v.last_enqueue==std::optional<Cycle>{t}||v.previous_enqueue==std::optional<Cycle>{t};};
   const auto deq=[&](Cycle t){return v.last_dequeue==std::optional<Cycle>{t}||v.previous_dequeue==std::optional<Cycle>{t};};
   const auto end=std::int64_t(v.items.size())-enq(at)+deq(at);
   const auto begin=end-enq(at-1)+deq(at-1);
   if(begin<0||end<0)throw std::logic_error("queue edge accounting underflow");
   return {std::size_t(begin),std::size_t(end),enq(at-1),deq(at-1)};
 }
 std::size_t occupancy(std::size_t index=0)const{return queues_.at(index).items.size();}
};
// One selected SourceD owns these registers across ALL opcodes. Keeping the
// actual S2/S3/S4 credits shared allows S1 to accept the next request after its
// last input, without creating independent response or writeback pipelines.
struct PostedSourceDPipeline {
 PostedRegisteredTransport s2,s3,s4;
 explicit PostedSourceDPipeline(merlin_timing::PostedTimeline&q):s2(q,{{1,true}}),s3(q,{{1,true}}),s4(q,{{1,true}}){}
};
}
#endif
