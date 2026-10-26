#ifndef GEMMINI_POSTED_COMMAND_INGRESS_HPP
#define GEMMINI_POSTED_COMMAND_INGRESS_HPP
#include <merlin_timing/posted_timeline.hpp>
#include <merlin_timing/engine.hpp>
#include <array>
#include <deque>
#include <memory>
#include <vector>
namespace gemmini_annotated_spike {
// Selected non-flow/non-pipe registered queues only. Original source PC/bits
// and register operands travel with their OWN accepted command; a later CPU
// instruction never supplies a deferred actor's provenance.
class PostedCommandIngress {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
 public:
 struct Request{std::uint64_t pc,bits,rs1,rs2;Cycle source;};
 using Ready=std::function<bool(const Request&,Cycle)>;
 using Consume=std::function<void(const Request&,Cycle)>;
 struct Coverage{std::vector<std::size_t>peak;std::uint64_t raw_accepted=0,rs_accepted=0;Cycle source_wait=0;};
 private:
 struct Entry{Request request;Cycle visible;};
 struct Waiting{Request request;Q::Token accepted;};
 Q&q_;std::vector<std::size_t>capacity_;Ready ready_;Consume consume_;
 std::vector<std::deque<Entry>>queues_;
 std::optional<Waiting>waiting_;bool ticking_=false;
 Cycle next_tick_=0;std::optional<Cycle> last_tick_,last_accept_;bool raw_was_full_=false;Coverage coverage_;
 void enqueue(const Waiting&w,Cycle at){
   last_accept_=at;queues_[0].push_back({w.request,at+1});++coverage_.raw_accepted;
   coverage_.source_wait+=at-w.request.source;
   q_.complete(w.accepted);measure();
 }
 void measure(){for(std::size_t i=0;i<queues_.size();++i)coverage_.peak[i]=std::max(coverage_.peak[i],queues_[i].size());}
 void schedule(Cycle at){
   if(ticking_)return;
   ticking_=true;at=std::max({at,q_.now(),next_tick_});
   q_.post(at,{},[this](auto&,auto t){tick(t);},Q::Kind::source_arrival);
 }
 void tick(Cycle at){
   ticking_=false;next_tick_=at+1;
   std::vector<std::size_t>old(queues_.size());for(std::size_t i=0;i<queues_.size();++i)old[i]=queues_[i].size();
   last_tick_=at;raw_was_full_=old[0]>=capacity_[0];
   if(!queues_.back().empty()&&queues_.back().front().visible<=at&&ready_(queues_.back().front().request,at)){
     auto request=queues_.back().front().request;queues_.back().pop_front();++coverage_.rs_accepted;consume_(request,at);
   }
   // No flow: a new entry is invisible until the following cycle. No pipe:
   // a FULL destination cannot use its just-dequeued credit on this edge.
   for(int i=int(queues_.size())-2;i>=0;--i)if(!queues_[i].empty()&&queues_[i].front().visible<=at&&old[i+1]<capacity_[i+1]){
     auto entry=queues_[i].front();queues_[i].pop_front();entry.visible=at+1;queues_[i+1].push_back(std::move(entry));
   }
   if(waiting_&&old[0]<capacity_[0]){auto wait=*waiting_;waiting_.reset();enqueue(wait,at);}
   measure();if(busy())schedule(at+1);
 }
 public:
 PostedCommandIngress(Q&q,std::array<std::size_t,4>capacity,Ready ready,Consume consume,bool rocc_router=false):q_(q),capacity_(capacity.begin(),capacity.end()),ready_(std::move(ready)),consume_(std::move(consume)){
   if(rocc_router)capacity_.insert(capacity_.begin(),2);
   queues_.resize(capacity_.size());coverage_.peak.resize(capacity_.size());
   if(!ready_||!consume_)throw std::invalid_argument("missing raw ingress ownership");
   for(auto n:capacity_)if(n!=2)throw std::invalid_argument("unsupported selected raw queue capacity");
 }
 merlin_timing::Result push(Request request){
   if(waiting_){q_.fail("multiple open scalar CPU RoCC sources");return {};}
   auto done=q_.token();if(!done)return {};
   request.source=std::max(request.source,q_.now());
   q_.post(request.source,{},[this,request,done](auto&,auto at){
     Waiting wait{request,*done};
     const bool no_pipe_release=last_tick_&&*last_tick_==at&&raw_was_full_;
     if(queues_[0].size()<capacity_[0]&&!no_pipe_release&&last_accept_!=std::optional<Cycle>{at})enqueue(wait,at);else waiting_=wait;
     schedule(at+1);
   },Q::Kind::source_arrival);
   while(!q_.completed(*done)&&!q_.progress().failed)if(!q_.step(true)){q_.fail("raw ingress acceptance deadlock");break;}
   const auto accepted=q_.completed(*done);return {accepted,accepted,accepted};
 }
 bool busy()const{if(waiting_)return true;for(const auto&q:queues_)if(!q.empty())return true;return false;}
 bool drain(){while(busy()&&!q_.progress().failed)if(!q_.step(true))return q_.fail("raw ingress drain deadlock");return !q_.progress().failed;}
 const Coverage&coverage()const{return coverage_;}
};
}
#endif
