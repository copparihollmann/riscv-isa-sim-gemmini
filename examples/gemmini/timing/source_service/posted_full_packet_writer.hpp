#ifndef GEMMINI_POSTED_FULL_PACKET_WRITER_HPP
#define GEMMINI_POSTED_FULL_PACKET_WRITER_HPP
#include "registered_transport.hpp"
namespace gemmini_annotated_spike {
// Selected aligned PutFull domain, at most one cache line / four client beats.
// The original packet owns one xactBusy source and one D response. SinkA's
// finite payload entries are released by the actual SourceD S2 pop, not D-ACK.
class PostedFullPacketWriter {
 using Q=merlin_timing::PostedTimeline;using Token=Q::Token;using Cycle=merlin_timing::Cycle;
 public:
 using Memory=std::function<void(Cycle,Token,Token,const std::vector<Token>&,const std::vector<Token>&)>;
 private:
 struct Packet{Memory memory;Token captured,done,d_accepted;std::vector<Token>data,popped;std::size_t beats;std::shared_ptr<Packet>next;};
 Q&q_;PostedRegisteredTransport&shared_a_,&shared_d_;PostedRegisteredTransport local_a_,local_d_;
 std::size_t live_=0,peak_=0,payload_live_=0,payload_peak_=0,payload_capacity_;
 bool busy_=false;std::deque<std::shared_ptr<Packet>>waiting_;std::shared_ptr<Packet>credit_wait_;
 std::deque<std::function<void(Cycle)>>payload_wait_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("full writer token budget");return *t;}
 void next(Cycle at){if(!busy_&&!waiting_.empty()){auto p=waiting_.front();waiting_.pop_front();capture(p,at);}}
 void capture(std::shared_ptr<Packet>p,Cycle at){busy_=true;q_.complete(p->captured);q_.post(at+1,{},[this,p](auto&,auto t){issue(p,0,t);},Q::Kind::source_arrival);}
 void acknowledge(std::shared_ptr<Packet>p,Cycle at){
   if(!live_){q_.fail("full writer xactBusy underflow");return;}--live_;q_.complete(p->done);
   if(credit_wait_){auto pending=std::move(credit_wait_);credit_wait_.reset();q_.post(at+1,{},[this,pending](auto&,auto t){issue(pending,0,t);},Q::Kind::source_arrival);}
 }
 void sink(std::shared_ptr<Packet>p,std::size_t beat,Token consumed,Cycle at){
   if(payload_live_==payload_capacity_){payload_wait_.push_back([this,p,beat,consumed](Cycle t){sink(p,beat,consumed,t);});return;}
   ++payload_live_;payload_peak_=std::max(payload_peak_,payload_live_);q_.complete(p->data.at(beat));q_.complete(consumed);
   q_.post(at,{p->popped.at(beat)},[this](auto&,auto t){
     if(!payload_live_){q_.fail("SinkA payload underflow");return;}--payload_live_;
     if(!payload_wait_.empty()){auto w=std::move(payload_wait_.front());payload_wait_.pop_front();q_.post(t+1,{},[w=std::move(w)](auto&,auto now){w(now);},Q::Kind::source_arrival);}
   },Q::Kind::operand_consume);
   if(beat)return;
   auto ready=token();p->memory(at,ready,p->d_accepted,p->data,p->popped);
   q_.post(at,{ready},[this,p](auto&,auto t){
     auto entered=shared_d_.push([this,p](Cycle at,Token consumed){
       auto entered=local_d_.push([this,p](Cycle t,Token consumed){acknowledge(p,t);q_.complete(consumed);},at);
       q_.post(at,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::response_beat);
     },t);
     q_.post(t,{entered},[p](auto&q,auto){q.complete(p->d_accepted);},Q::Kind::response_beat);
   },Q::Kind::response_beat);
 }
 void issue(std::shared_ptr<Packet>p,std::size_t beat,Cycle at){
   if(!beat&&live_==16){if(credit_wait_){q_.fail("multiple full writer state registers");return;}credit_wait_=p;return;}
   // Source allocation is held while the first untranslated beat is pending;
   // no later packet can bypass this one open writer state register.
   if(!beat){++live_;peak_=std::max(peak_,live_);}
   auto entered=local_a_.push([this,p,beat](Cycle at,Token consumed){
     auto shared=shared_a_.push([this,p,beat](Cycle t,Token consumed){sink(p,beat,consumed,t);},at);
     q_.post(at,{shared},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::source_arrival);
   },at);
   q_.post(at,{entered},[this,p,beat](auto&,auto t){
     if(beat+1<p->beats)q_.post(t+1,{},[this,p,beat](auto&,auto now){issue(p,beat+1,now);},Q::Kind::source_arrival);
     else if(p->next)q_.post(t+1,{},[this,next=p->next](auto&,auto now){issue(next,0,now);},Q::Kind::source_arrival);
     // state_machine_ready_for_req is combinational on the final A fire:
     // a following row may capture on THIS edge; its first A is next cycle.
     else{busy_=false;next(t);}
   },Q::Kind::source_arrival);
 }
 public:
 PostedFullPacketWriter(Q&q,PostedRegisteredTransport&a,PostedRegisteredTransport&d,std::size_t payload_capacity):q_(q),shared_a_(a),shared_d_(d),
   local_a_(q,{{1,true},{1,true},{2,false}}),local_d_(q,{{2,false}}),payload_capacity_(payload_capacity){
   if(!payload_capacity||payload_capacity>4096)throw std::invalid_argument("full writer requires bounded actual SinkA payload capacity");
 }
 Token push(std::size_t beats,Memory memory,Cycle at,Token done){
   return push_row({beats},{std::move(memory)},at,{done});
 }
 Token push_row(std::vector<std::size_t>beats,std::vector<Memory>memory,Cycle at,std::vector<Token>done){
   if(beats.empty()||beats.size()>4||beats.size()!=memory.size()||beats.size()!=done.size())throw std::invalid_argument("full writer requires original bounded row packet sequence");
   std::shared_ptr<Packet>p,prior;
   for(std::size_t packet=0;packet<beats.size();++packet){
     if(!beats[packet]||beats[packet]>4||!memory[packet])throw std::invalid_argument("full writer requires original1..4beat packet owner");
     auto current=std::make_shared<Packet>(Packet{std::move(memory[packet]),token(),done[packet],token(),{},{},beats[packet],{}});
     for(std::size_t i=0;i<beats[packet];++i){current->data.push_back(token());current->popped.push_back(token());}
     if(prior)prior->next=current;else p=current;prior=current;
   }
   // StreamWriter holds the captured row while bytesSent advances between
   // original packets; only the first packet incurs io.req capture.
   q_.post(std::max(at,q_.now()),{},[this,p](auto&,auto t){if(busy_){if(waiting_.size()>=16){q_.fail("full writer request custody bound");return;}waiting_.push_back(p);}else capture(p,t);},Q::Kind::source_arrival);
   return p->captured;
 }
 std::size_t peak_transactions()const{return peak_;}
 std::size_t peak_payload_beats()const{return payload_peak_;}
 bool busy()const{return busy_||live_||payload_live_||credit_wait_||!waiting_.empty()||!payload_wait_.empty()||local_a_.busy()||local_d_.busy();}
};
// SourceD's full-write subset: S1 reforms the original request, S2 holds data
// from SinkA, S3 emits ACK only on the first internal beat, S4 publishes each
// accepted bank write. No partial RMW, cold miss, retry or guessed SRAM fee.
class PostedFullPacketSourceD {
 using Q=merlin_timing::PostedTimeline;using Token=Q::Token;using Cycle=merlin_timing::Cycle;
 public:using Publish=std::function<void(std::size_t,Cycle,Token)>;
 private:
 struct Request{std::vector<Token>data,popped;Token accepted,d_ready,d_accepted;Publish publish;};
 Q&q_;PostedRegisteredTransport s2_,s3_,s4_;bool busy_=false;std::deque<std::shared_ptr<Request>>waiting_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("full SourceD token budget");return *t;}
 void start(std::shared_ptr<Request>r,Cycle at){busy_=true;q_.complete(r->accepted);form(r,0,at);}
 void form(std::shared_ptr<Request>r,std::size_t beat,Cycle at){
   auto entered=s2_.push([this,r,beat](Cycle time,Token consumed){
     q_.post(time,{r->data.at(beat)},[this,r,beat,consumed](auto&,auto ready){
       q_.complete(r->popped.at(beat));
       auto entered=s3_.push([this,r,beat](Cycle t,Token consumed){
         if(!beat)q_.complete(r->d_ready);
         std::vector<Token>ack;if(!beat)ack.push_back(r->d_accepted);
         q_.post(t,std::move(ack),[this,r,beat,consumed](auto&,auto accepted){
           auto entered=s4_.push([r,beat](Cycle time,Token stored){r->publish(beat,time,stored);},accepted);
           q_.post(accepted,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::response_beat);
         },Q::Kind::response_beat);
       },ready);
       q_.post(ready,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::response_beat);
     },Q::Kind::response_beat);
   },at);
   q_.post(at,{entered},[this,r,beat](auto&,auto t){
     if(beat+1<r->data.size())q_.post(t+1,{},[this,r,beat](auto&,auto now){form(r,beat+1,now);},Q::Kind::source_arrival);
     else q_.post(t+1,{},[this](auto&,auto now){busy_=false;if(!waiting_.empty()){auto next=waiting_.front();waiting_.pop_front();start(next,now);}},Q::Kind::source_arrival);
   },Q::Kind::source_arrival);
 }
 public:
 explicit PostedFullPacketSourceD(Q&q):q_(q),s2_(q,{{1,true}}),s3_(q,{{1,true}}),s4_(q,{{1,true}}){}
 Token push(std::vector<Token>data,std::vector<Token>popped,Token ack_ready,Token ack_accepted,Publish publish,Cycle at){
   if(data.empty()||data.size()>4||data.size()!=popped.size()||!publish)throw std::invalid_argument("full SourceD requires original packet payload owners");
   auto r=std::make_shared<Request>(Request{std::move(data),std::move(popped),token(),ack_ready,ack_accepted,std::move(publish)});
   q_.post(std::max(at,q_.now()),{},[this,r](auto&,auto t){if(busy_){if(waiting_.size()>=16){q_.fail("full SourceD request custody bound");return;}waiting_.push_back(r);}else start(r,t);},Q::Kind::source_arrival);return r->accepted;
 }
 bool busy()const{return busy_||!waiting_.empty()||s2_.busy()||s3_.busy()||s4_.busy();}
};
}
#endif
