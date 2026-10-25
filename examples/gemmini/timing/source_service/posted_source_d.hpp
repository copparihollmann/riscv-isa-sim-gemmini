#ifndef GEMMINI_POSTED_SOURCE_D_HPP
#define GEMMINI_POSTED_SOURCE_D_HPP
#include "registered_transport.hpp"
#include <array>
namespace gemmini_annotated_spike {
// Selected one-beat SourceD domain: resident/no-probe/no-eviction, original
// Put buffer data present and no external BankedStore stalls. Partial writes
// need a two-register SRAM read; it overlaps S2/S3 rather than adding two
// cycles to ACK. S3 D acceptance and S4 publication remain separate tokens.
class PostedOneBeatSourceD {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;using Token=Q::Token;
 public:using Publish=PostedRegisteredTransport::Sink;
 using Read=std::function<void(Cycle,Token,Token)>; // accepted SRAM request, ready SRAM data
 private:Q&q_;PostedRegisteredTransport response_,publication_;
 std::function<void(bool)>read_observed_;
 std::deque<std::uint64_t>retired_;
 std::uint64_t sram_reads_=0,bypassed_reads_=0;
 struct Request{std::uint64_t address;bool partial;Token accepted,d_ready,d_accepted;Publish publish;Read read;};
 std::deque<std::shared_ptr<Request>>waiting_;bool input_busy_=false;
 std::optional<Cycle>last_input_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("SourceD token budget");return *t;}
 void start(std::shared_ptr<Request>request,Cycle at){
   input_busy_=true;
   if(last_input_==std::optional<Cycle>{at}){q_.post(at+1,{},[this,request](auto&,auto t){start(request,t);},Q::Kind::source_arrival);return;}
   last_input_=at;q_.complete(request->accepted);
   // Pipeline2 guarantees that a non-bypassed S1 read is available when S3
   // becomes valid. A retained bypass can suppress that read, not accelerate
   // the registered response path. No SRAM data is synthesized here.
   auto data_ready=token(),read_accepted=token();
   const auto address=request->address;const bool read=request->partial&&!retained_bypass(address);
   if(read)++sram_reads_;else if(request->partial)++bypassed_reads_;
   if(request->partial&&read_observed_)read_observed_(read);
   if(read&&request->read)request->read(at,read_accepted,data_ready);
   else{q_.complete(read_accepted);q_.post(at+(read?2:0),{},[data_ready](auto&q,auto){q.complete(data_ready);},Q::Kind::response_beat);}
   q_.post(at,{read_accepted},[this,request,address,data_ready](auto&,auto accepted){
   auto entered=response_.push([this,address,data_ready,d_ready=request->d_ready,d_accepted=request->d_accepted,publish=request->publish](Cycle t,Token consumed)mutable{
     q_.post(t,{data_ready},[this,address,d_ready,d_accepted,publish=std::move(publish),consumed](auto&,auto ready)mutable{
     q_.complete(d_ready);
     q_.post(ready,{d_accepted},[this,address,publish=std::move(publish),consumed](auto&,auto accepted)mutable{
       auto entered=publication_.push([this,address,publish=std::move(publish)](Cycle time,Token stored)mutable{
         publish(time,stored);
         q_.post(time,{stored},[this,address](auto&,auto){retired_.push_front(address);if(retired_.size()>3)retired_.pop_back();},Q::Kind::local_publish);
       },accepted);
       q_.post(accepted,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::response_beat);
     },Q::Kind::response_beat);
     },Q::Kind::response_beat);
   },accepted);
   q_.post(accepted,{entered},[this](auto&,auto time){
     input_busy_=false;
     if(!waiting_.empty()){auto next=waiting_.front();waiting_.pop_front();q_.post(time+1,{},[this,next](auto&,auto t){start(next,t);},Q::Kind::source_arrival);input_busy_=true;}
   },Q::Kind::source_arrival);
   },Q::Kind::source_arrival);
 }
 public:
 PostedOneBeatSourceD(Q&q,std::function<void(bool)>read_observed={}):q_(q),response_(q,{{1,true},{1,true}}),publication_(q,{{1,true}}),read_observed_(std::move(read_observed)){}
 Token push(std::uint64_t address,bool partial,Token d_ready,Token d_accepted,Publish publish,Cycle at,Read read={}){
   if(!publish)throw std::invalid_argument("SourceD needs storage publication owner");
   auto accepted=token();auto request=std::make_shared<Request>(Request{address,partial,accepted,d_ready,d_accepted,std::move(publish),std::move(read)});
   q_.post(std::max(at,q_.now()),{},[this,request](auto&,auto t){
     if(input_busy_){if(waiting_.size()>=16){q_.fail("SourceD pending request software custody bound");return;}waiting_.push_back(request);}
     else start(request,t);
   },Q::Kind::source_arrival);return accepted;
 }
 bool retained_bypass(std::uint64_t address)const{return std::find(retired_.begin(),retired_.end(),address)!=retired_.end();}
 bool busy()const{return input_busy_||!waiting_.empty()||response_.busy()||publication_.busy();}
 std::uint64_t sram_reads()const{return sram_reads_;}
 std::uint64_t bypassed_reads()const{return bypassed_reads_;}
};
}
#endif
