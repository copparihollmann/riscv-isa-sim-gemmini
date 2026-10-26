#ifndef GEMMINI_POSTED_READ_ALLOCATION_HPP
#define GEMMINI_POSTED_READ_ALLOCATION_HPP
#include "registered_transport.hpp"
#include <timing/read_allocation.hpp>
namespace gemmini_annotated_spike {
// SourceD inner128-bit read stream. Controller/MSHR ownership is supplied by
// the caller and shared with real stores; this actor never creates a parallel
// read-only controller. Whole outer fill is an explicit upstream bound.
class PostedReadAllocationResponse {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;using Token=Q::Token;
 public:
 using Read=std::function<void(std::uint64_t,Cycle,Token,Token)>;
 using Done=std::function<void(Cycle)>;
 using Sink=std::function<void(std::size_t,Cycle,Token)>;
 private:
 struct Pending{spike_timing::ReadAllocationV7 request;Read read;Done done;std::size_t next=0,returned=0;std::optional<Token>inner_e;Done input_done;Sink sink;};
 Q&q_;std::optional<Cycle>last_response_;std::unique_ptr<PostedRegisteredTransport>pipeline_;std::shared_ptr<PostedSourceDPipeline>shared_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("read allocation response token bound");return *t;}
 void finish_response(const std::shared_ptr<Pending>&p,std::size_t beat,Cycle at,std::optional<Token>consumed){
   last_response_=at;if(consumed){
     if(shared_){
       // Reads also retire through S4 (s1_retires = !s1_single). Although no
       // bank write is needed, this is the SAME finite register as stores.
       auto entered=shared_->s4.push([this](Cycle,Token stored){q_.complete(stored);},at);
       q_.post(at,{entered},[consumed](auto&q,auto){q.complete(*consumed);},Q::Kind::response_beat);
     }else q_.complete(*consumed);
   }
   if(!beat&&p->inner_e)q_.post(at+1,{},[done=*p->inner_e](auto&q,auto){q.complete(done);},Q::Kind::response_beat);
   if(++p->returned==p->request.inner_bytes/16){
     std::vector<Token>deps;if(p->inner_e)deps.push_back(*p->inner_e);
     q_.post(at,std::move(deps),[p](auto&,auto now){p->done(now);},Q::Kind::command_retire);
   }
 }
 void respond(const std::shared_ptr<Pending>&p,std::size_t beat,Token ready,Cycle at,std::optional<Token>consumed={}){
   q_.post(at,{ready},[this,p,beat,consumed](auto&,auto now){
     const auto response=std::max(now,last_response_?*last_response_+1:now);
     q_.post(response,{},[this,p,beat,consumed](auto&,auto t){
       if(p->sink){
         const auto accepted=token();p->sink(beat,t,accepted);
         q_.post(t,{accepted},[this,p,beat,consumed](auto&,auto end){finish_response(p,beat,end,consumed);},Q::Kind::response_beat);
       }else finish_response(p,beat,t,consumed);
     },Q::Kind::response_beat);
   },Q::Kind::response_beat);
 }
 void issue(const std::shared_ptr<Pending>&p,Cycle at){
   const auto beat=p->next++;auto accepted=token(),ready=token();
   p->read(p->request.inner_address+beat*16,at,accepted,ready);
   q_.post(at,{accepted},[this,p,beat,ready](auto&,auto now){
     if(pipeline_||shared_){
       // s1 progresses only when BOTH the real SRAM read and finite s2
       // acceptance have succeeded. A response still waits its SRAM data.
       auto response=[this,p,beat,ready](Cycle t,Token consumed){respond(p,beat,ready,t,consumed);};
       const auto entered=shared_?shared_->s2.push([this,response=std::move(response)](Cycle t,Token consumed)mutable{
         const auto entered=shared_->s3.push(std::move(response),t);
         q_.post(t,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::response_beat);
       },now):pipeline_->push(std::move(response),now);
       q_.post(now,{entered},[this,p](auto&,auto t){
         if(p->next<p->request.inner_bytes/16)q_.post(t+1,{},[this,p](auto&,auto next){issue(p,next);},Q::Kind::operand_consume);
         else if(p->input_done)p->input_done(t);
       },Q::Kind::operand_consume);
     }else if(p->next<p->request.inner_bytes/16)
       q_.post(now+1,{},[this,p](auto&,auto t){issue(p,t);},Q::Kind::operand_consume);
   },Q::Kind::operand_consume);
   if(!pipeline_&&!shared_)respond(p,beat,ready,at);
 }
 public:
 explicit PostedReadAllocationResponse(Q&q,bool source_input_retirement=false,std::shared_ptr<PostedSourceDPipeline>shared={}):q_(q),shared_(std::move(shared)){
   if(source_input_retirement&&!shared_)pipeline_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{1,true},{1,true}});
 }
 bool push(const spike_timing::ReadAllocationV7&r,Read read,Done done,Cycle at,Done input_done={},Sink sink={}){
   if(!read||!done||r.inner_bytes<16||r.inner_bytes>64||r.inner_bytes%16||r.inner_address%16||
      r.inner_address/64!=r.miss.line||(r.inner_address+r.inner_bytes-1)/64!=r.miss.line||
      (r.inner_acquire&&(r.inner_bytes!=64||r.inner_address%64)))return q_.fail("unsupported original inner read geometry");
   auto p=std::make_shared<Pending>(Pending{r,std::move(read),std::move(done),0,0,{},std::move(input_done),std::move(sink)});
   // SinkE is direct (no queue); Rocket accepts E with FIRST cached GrantData
   // and the MSHR sees its registered response on the next edge.
   if(r.inner_acquire)p->inner_e=token();
   q_.post(at,{},[this,p](auto&,auto t){issue(p,t);},Q::Kind::operand_consume);return true;
 }
};
}
#endif
