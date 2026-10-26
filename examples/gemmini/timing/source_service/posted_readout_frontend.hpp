#ifndef GEMMINI_POSTED_READOUT_FRONTEND_HPP
#define GEMMINI_POSTED_READOUT_FRONTEND_HPP
#include "registered_transport.hpp"
#include "streamed_readout.hpp"
namespace gemmini_annotated_spike {
// Source-owned unpooled accumulator response path. Geometry, real SRAM port
// ownership and the writer are callbacks; no arithmetic/DRAM service is priced
// here. The response register holds when downstream cannot accept. Metadata
// stays live until its corresponding writer request actually accepts.
class PostedReadoutFrontend {
 using Q=merlin_timing::PostedTimeline;using Token=Q::Token;using Cycle=merlin_timing::Cycle;
 public:
 using Read=std::function<void(Cycle,Token,Token)>; // request accepted, SRAM response ready
 using Writer=PostedRegisteredTransport::Sink;
 private:
 struct Row{Read read;Writer writer;Token dispatch_consumed;bool bypass=false;};
 Q&q_;ReadoutStreamConfig config_;PostedRegisteredTransport dispatch_,normalizer_,scale_,bypass_,bypass_norm_;
 std::optional<Token> ordered_writer_;
 bool read_busy_=false;std::size_t issued_=0,peak_issued_=0;
 std::deque<std::function<void(Cycle)>>read_wait_,issue_wait_;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("readout frontend token budget");return *t;}
 void wake_read(Cycle at){if(read_busy_||read_wait_.empty())return;auto next=std::move(read_wait_.front());read_wait_.pop_front();next(at);}
 void scale_offer(Writer writer,Cycle at,Token norm_consumed,bool bypass=false){
   if(issued_>=config_.issue_metadata){issue_wait_.push_back([this,writer=std::move(writer),norm_consumed,bypass](Cycle t)mutable{scale_offer(std::move(writer),t,norm_consumed,bypass);});return;}
   ++issued_;peak_issued_=std::max(peak_issued_,issued_);
   auto accepted=(bypass?bypass_:scale_).push([this,writer=std::move(writer)](Cycle t,Token scale_consumed)mutable{
     auto writer_accepted=token();writer(t,writer_accepted);
     q_.post(t,{writer_accepted},[this,scale_consumed](auto&,auto now){
       if(!issued_){q_.fail("readout issue metadata underflow");return;}
       --issued_;q_.complete(scale_consumed);
       // Selected write_issue queue is pipe=true: its released credit is
       // available on this SAME edge, unlike default non-pipe data queues.
       if(!issue_wait_.empty()){auto next=std::move(issue_wait_.front());issue_wait_.pop_front();next(now);}
     },Q::Kind::source_arrival);
   },at);
   q_.post(at,{accepted},[norm_consumed](auto&q,auto){q.complete(norm_consumed);},Q::Kind::source_arrival);
 }
 void read(std::shared_ptr<Row>row,Cycle at){
   if(read_busy_){read_wait_.push_back([this,row](Cycle t){read(row,t);});return;}
   read_busy_=true;auto accepted=token(),response=token();row->read(at,accepted,response);
   q_.post(at,{accepted},[row](auto&q,auto){q.complete(row->dispatch_consumed);},Q::Kind::operand_consume);
   q_.post(at,{response},[this,row](auto&,auto time){
     auto entered=(row->bypass?bypass_norm_:normalizer_).push([this,writer=row->writer,bypass=row->bypass](Cycle at,Token consumed)mutable{scale_offer(std::move(writer),at,consumed,bypass);},time);
     q_.post(time,{entered},[this](auto&,auto t){read_busy_=false;wake_read(t);},Q::Kind::response_beat);
   },Q::Kind::response_beat);
 }
 public:
 PostedReadoutFrontend(Q&q,ReadoutStreamConfig config):q_(q),config_(config),
   dispatch_(q,{{config.dispatch,false}}),normalizer_(q,{{config.norm_passthrough,false}}),
   scale_(q,std::vector<PostedRegisteredTransport::Spec>(config.scale_stages,{1,true})),
   bypass_(q,{{config.scale_metadata,false},{config.issue_metadata,true}}),bypass_norm_(q,{{config.norm_metadata,false}}){
   if(!config.norm_metadata||!config.scale_metadata||!config.issue_metadata||config.issue_metadata>256 ||
      config.norm_metadata<config.norm_passthrough||config.scale_metadata<config.norm_passthrough)
     throw std::invalid_argument("unsupported readout metadata geometry");
 }
 Token push(Read read_port,Writer writer,Cycle at){
   if(!read_port||!writer)throw std::invalid_argument("readout frontend needs source owners");
   return dispatch_.push([this,read_port=std::move(read_port),writer=std::move(writer)](Cycle time,Token consumed)mutable{
     read(std::make_shared<Row>(Row{std::move(read_port),std::move(writer),consumed}),time);
   },at);
 }
 // Pool padding is a garbage-address metadata bypass: no SRAM access,
 // normalizer arithmetic or eight-stage scale data path. FIFO writer order
 // still keeps a ready padding request behind any older normal scale data.
 Token push_ordered(Read read_port,Writer writer,Cycle at,bool garbage=false){
   if(!read_port||!writer)throw std::invalid_argument("ordered readout needs source owners");
   const auto previous=ordered_writer_;const auto done=token();ordered_writer_=done;
   Writer ordered=[this,previous,done,writer=std::move(writer)](Cycle t,Token consumed)mutable{
     std::vector<Token>deps;if(previous)deps.push_back(*previous);
     q_.post(t,std::move(deps),[this,done,writer=std::move(writer),consumed](auto&,auto now)mutable{
       writer(now,consumed);q_.post(now,{consumed},[done](auto&q,auto){q.complete(done);},Q::Kind::source_arrival);
     },Q::Kind::source_arrival);
   };
   return dispatch_.push([this,read_port=std::move(read_port),writer=std::move(ordered),garbage](Cycle time,Token consumed)mutable{
     read(std::make_shared<Row>(Row{std::move(read_port),std::move(writer),consumed,garbage}),time);
   },at);
 }
 std::size_t peak_issued()const{return peak_issued_;}
 bool busy()const{return read_busy_||issued_||!read_wait_.empty()||!issue_wait_.empty()||dispatch_.busy()||normalizer_.busy()||scale_.busy()||bypass_.busy()||bypass_norm_.busy();}
};
}
#endif
