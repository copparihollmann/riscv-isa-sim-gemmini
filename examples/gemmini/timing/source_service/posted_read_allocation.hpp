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
 private:
 struct Pending{spike_timing::ReadAllocationV7 request;Read read;Done done;std::size_t next=0,returned=0;std::optional<Token>inner_e;};
 Q&q_;std::optional<Cycle>last_response_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("read allocation response token bound");return *t;}
 void issue(const std::shared_ptr<Pending>&p,Cycle at){
   const auto beat=p->next++;auto accepted=token(),ready=token();
   p->read(p->request.inner_address+beat*16,at,accepted,ready);
   q_.post(at,{accepted},[this,p](auto&,auto now){if(p->next<p->request.inner_bytes/16)
     q_.post(now+1,{},[this,p](auto&,auto t){issue(p,t);},Q::Kind::operand_consume);
   },Q::Kind::operand_consume);
   q_.post(at,{ready},[this,p,beat](auto&,auto now){
     const auto response=std::max(now,last_response_?*last_response_+1:now);
     q_.post(response,{},[this,p,beat](auto&,auto t){
       last_response_=t;
       if(!beat&&p->inner_e)q_.post(t+1,{},[done=*p->inner_e](auto&q,auto){q.complete(done);},Q::Kind::response_beat);
       if(++p->returned==p->request.inner_bytes/16){
         std::vector<Token>deps;if(p->inner_e)deps.push_back(*p->inner_e);
         q_.post(t,std::move(deps),[p](auto&,auto now){p->done(now);},Q::Kind::command_retire);
       }
     },Q::Kind::response_beat);
   },Q::Kind::response_beat);
 }
 public:
 explicit PostedReadAllocationResponse(Q&q):q_(q){}
 bool push(const spike_timing::ReadAllocationV7&r,Read read,Done done,Cycle at){
   if(!read||!done||r.inner_bytes<16||r.inner_bytes>64||r.inner_bytes%16||r.inner_address%16||
      r.inner_address/64!=r.miss.line||(r.inner_address+r.inner_bytes-1)/64!=r.miss.line||
      (r.inner_acquire&&(r.inner_bytes!=64||r.inner_address%64)))return q_.fail("unsupported original inner read geometry");
   auto p=std::make_shared<Pending>(Pending{r,std::move(read),std::move(done),0,0,{}});
   // SinkE is direct (no queue); Rocket accepts E with FIRST cached GrantData
   // and the MSHR sees its registered response on the next edge.
   if(r.inner_acquire)p->inner_e=token();
   q_.post(at,{},[this,p](auto&,auto t){issue(p,t);},Q::Kind::operand_consume);return true;
 }
};
}
#endif
