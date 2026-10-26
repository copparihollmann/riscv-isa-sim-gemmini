#ifndef SPIKE_TIMING_FETCH_MISS_CONTROLLER_HPP
#define SPIKE_TIMING_FETCH_MISS_CONTROLLER_HPP
#include <merlin_timing/posted_timeline.hpp>
#include <functional>
#include <optional>
namespace spike_timing {
// Selected Rocket no-ITIM, one-outstanding demand I$ miss controller. The
// caller owns cache classification, original LLC transaction and all beats.
// Tile A/D Queue2 cannot fill: one demand and an always-ready I$ D receiver.
// Their registered handoffs still precede LLC admission / I$ line validity.
// This does not supply speculative Frontend/FQ or predictor state.
class FetchMissController {
 using Q=merlin_timing::PostedTimeline;
 public:
 using Cycle=merlin_timing::Cycle;using Token=Q::Token;
 struct Spec{Cycle lookup,request_queue,response_queue,line_valid,replay_lookup;};
 using Edge=std::function<void(Cycle)>;
 private:
 enum class State{idle,lookup,request,lower,response,line,replay};
 Q&q_;Spec spec_;State state_=State::idle;std::optional<Token>owner_;
 bool owned(Token t,State state){if(!owner_||owner_->id!=t.id||state_!=state)return q_.fail("I$ original miss controller identity/state");return true;}
 public:
 FetchMissController(Q&q,Spec spec):q_(q),spec_(spec){
   if(spec.lookup!=2||spec.request_queue!=1||spec.response_queue!=1||spec.line_valid!=1||spec.replay_lookup!=2)
     throw std::invalid_argument("I$ controller differs from selected Rocket lookup/buffer/valid/replay stages");
 }
 std::optional<Token>begin(Cycle at,Edge lower){
   if(state_!=State::idle||!lower){q_.fail("I$ demand exceeds original single outstanding refill");return {};}
   auto token=q_.token();if(!token)return {};owner_=*token;state_=State::lookup;
   q_.post(at+spec_.lookup,{},[this,t=*token,lower=std::move(lower)](auto&,auto at){
     if(!owned(t,State::lookup))return;
     state_=State::request;
     q_.post(at+spec_.request_queue,{},[this,t,lower](auto&,auto admitted){if(!owned(t,State::request))return;
     state_=State::lower;lower(admitted);},Q::Kind::memory_accept);
   },Q::Kind::memory_accept);return token;
 }
 bool response(Token t,Cycle last,Edge ready){
   if(!ready||!owned(t,State::lower))return false;
   state_=State::response;
   q_.post(last+spec_.response_queue,{},[this,t,ready=std::move(ready)](auto&,auto received){
     if(!owned(t,State::response))return;
     state_=State::line;
     // Last D beat writes tag/vb_array. The refill write blocks req.ready
     // on this edge; its registered valid line permits next-edge replay.
     q_.post(received+spec_.line_valid,{},[this,t,ready](auto&,auto replay){
       if(!owned(t,State::line))return;
     state_=State::replay;
       q_.post(replay+spec_.replay_lookup,{},[this,t,ready](auto&,auto at){
         if(!owned(t,State::replay))return;
     state_=State::idle;owner_.reset();q_.complete(t);ready(at);
       },Q::Kind::local_publish);
     },Q::Kind::memory_accept);
   },Q::Kind::response_beat);return true;
 }
 bool busy()const{return state_!=State::idle;}
};
}
#endif
