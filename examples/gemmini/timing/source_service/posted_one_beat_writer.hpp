#ifndef GEMMINI_POSTED_ONE_BEAT_WRITER_HPP
#define GEMMINI_POSTED_ONE_BEAT_WRITER_HPP
#include "registered_transport.hpp"
#include <timing/source_actor.hpp>
namespace gemmini_annotated_spike {
// Selected one-full-client-beat writer route. Memory supplies its own D-ready
// token; this actor supplies no cache/DRAM fee or physical-storage publication.
// Request capture, translation, client/shared buffers and finite xactBusy
// ownership remain separate. It is not an admission law for partial/multibeat.
class PostedOneBeatWriter {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;using Token=Q::Token;
 public:using Memory=PostedRegisteredTransport::Sink;
 using Idle=std::function<void(Cycle)>;
 using TransactionMemory=std::function<void(Cycle,Token,Token)>; // ACK valid, ACK accepted by shared D
 private:
 std::optional<spike_timing::SourceActorSinkV1>actor_sink_;
 void actor(spike_timing::SourceActorRoleV1 role,std::uint64_t id,Cycle at,bool begin){if(actor_sink_)actor_sink_->edge(actor_sink_->opaque,role,id,at,begin);}
 struct Row{TransactionMemory memory;Token accepted,done,d_accepted;Idle idle{};};
 Q&q_;PostedRegisteredTransport &shared_a_,&shared_d_;
 PostedRegisteredTransport local_a_,local_d_;
 std::size_t live_=0,peak_=0;bool busy_=false;
 std::deque<std::shared_ptr<Row>>waiting_;std::shared_ptr<Row>credit_wait_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("writer token budget");return *t;}
 void next(Cycle at){if(!busy_&&!waiting_.empty()){auto row=waiting_.front();waiting_.pop_front();capture(row,at);}}
 void capture(std::shared_ptr<Row>row,Cycle at){
   busy_=true;actor(spike_timing::SourceActorRoleV1::writer_state,row->accepted.id,at,true);q_.complete(row->accepted);
   // req := io.req.bits; state := s_writing_new_block. The first
   // untranslated beat is visible in the FOLLOWING cycle.
   q_.post(at+1,{},[this,row](auto&,auto t){issue(row,t);},Q::Kind::source_arrival);
 }
 void acknowledge(std::shared_ptr<Row>row,Cycle at){
   if(!live_){q_.fail("writer xactBusy underflow");return;}
   --live_;actor(spike_timing::SourceActorRoleV1::writer_slot,row->accepted.id,at,false);q_.complete(row->done);
   // xactBusy removes a D-acknowledged source at the edge: an otherwise
   // FULL bitmap cannot reuse that source combinationally on this edge.
   if(credit_wait_){auto pending=std::move(credit_wait_);credit_wait_.reset();q_.post(at+1,{},[this,pending](auto&,auto t){issue(pending,t);},Q::Kind::source_arrival);}
 }
 void issue(std::shared_ptr<Row>row,Cycle at){
   if(live_==16){if(credit_wait_){q_.fail("multiple open writer state registers");return;}credit_wait_=row;return;}
   ++live_;actor(spike_timing::SourceActorRoleV1::writer_slot,row->accepted.id,at,true);peak_=std::max(peak_,live_);
   auto entered=local_a_.push([this,row](Cycle t,Token local_consumed){
     auto shared_entered=shared_a_.push([this,row](Cycle time,Token shared_consumed){
       auto response=token();row->memory(time,response,row->d_accepted);q_.complete(shared_consumed);
       q_.post(time,{response},[this,row](auto&,auto ready){
         auto entered=shared_d_.push([this,row](Cycle t,Token shared_consumed){
           auto client_entered=local_d_.push([this,row](Cycle at,Token consumed){acknowledge(row,at);q_.complete(consumed);},t);
           q_.post(t,{client_entered},[shared_consumed](auto&q,auto){q.complete(shared_consumed);},Q::Kind::response_beat);
         },ready);
         q_.post(ready,{entered},[row](auto&q,auto){q.complete(row->d_accepted);},Q::Kind::response_beat);
       },Q::Kind::response_beat);
     },t);
     q_.post(t,{shared_entered},[local_consumed](auto&q,auto){q.complete(local_consumed);},Q::Kind::source_arrival);
   },at);
   q_.post(at,{entered},[this,row](auto&,auto t){actor(spike_timing::SourceActorRoleV1::writer_state,row->accepted.id,t,false);busy_=false;if(row->idle)q_.post(t+1,{},[row](auto&,auto when){row->idle(when);},Q::Kind::source_arrival);next(t);},Q::Kind::source_arrival);
 }
 public:
 void source_actors(const spike_timing::SourceActorSinkV1&sink){actor_sink_=sink;}
 PostedOneBeatWriter(Q&q,PostedRegisteredTransport&a,PostedRegisteredTransport&d):q_(q),shared_a_(a),shared_d_(d),
   local_a_(q,{{1,true},{1,true},{2,false}}),local_d_(q,{{2,false}}){}
 Token push(Memory memory,Cycle at,Token done){
   if(!memory)throw std::invalid_argument("writer requires D response owner");
   return push_transaction([memory=std::move(memory)](Cycle t,Token ready,Token){memory(t,ready);},at,done);
 }
 Token push_transaction(TransactionMemory memory,Cycle at,Token done,Idle idle={}){
   auto accepted=token();if(!memory)throw std::invalid_argument("writer requires D response owner");
   auto row=std::make_shared<Row>(Row{std::move(memory),accepted,done,token(),std::move(idle)});
   q_.post(std::max(at,q_.now()),{},[this,row](auto&,auto t){
     if(busy_){if(waiting_.size()>=16){q_.fail("writer source custody bound");return;}waiting_.push_back(row);}else capture(row,t);
   },Q::Kind::source_arrival);return accepted;
 }
 std::size_t peak_transactions()const{return peak_;}
 bool busy()const{return busy_||live_||credit_wait_||!waiting_.empty()||local_a_.busy()||local_d_.busy();}
};
}
#endif
