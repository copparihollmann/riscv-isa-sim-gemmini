#ifndef SPIKE_TIMING_SOURCE_ACTOR_ACTIVITY_HPP
#define SPIKE_TIMING_SOURCE_ACTOR_ACTIVITY_HPP
#include "source_actor.hpp"
#include <array>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include <algorithm>
#include <limits>
#include <stdexcept>
namespace spike_timing {
// Source callback edges may describe a stage's future interval. Advance only
// at the committed CPU-start watermark, never at a future resource booking.
// Completed histories are discarded; memory is bounded by open actors and
// pending edges. Prefix actors survive the ROI boundary for exact clipping.
class SourceActorActivity {
public:
 using Cycle=std::uint64_t;using Role=SourceActorRoleV1;
 static constexpr std::size_t N=std::size_t(Role::count);
 struct Row{const char*name;const char*meaning;std::uint64_t active=0,units=0,peak=0,starts=0;std::int64_t live=0;bool covered=false;std::uint64_t capacity=0;};
 struct Pair{std::size_t left,right;std::uint64_t active=0;};
 explicit SourceActorActivity(std::size_t bound=65536):bound_(bound),rows_{{
  {"load.command_inflight","load-lane RS allocation through original command completion, including configuration; envelope"},
  {"store.command_inflight","store-lane RS allocation through original command completion, including configuration; envelope"},
  {"execute.command_inflight","execute-lane RS allocation through original result tag completion, including configuration; envelope"},
  {"load.rs_wait","RS allocation to controller issue; combined dependency and admission wait"},
  {"store.rs_wait","RS allocation to controller issue; combined dependency and admission wait"},
  {"execute.rs_wait","RS allocation to controller issue; combined dependency and admission wait"},
  {"execute.feed","selected source feed stage; modeled service, not PE occupancy"},
  {"reader.slot_residency","source packet slot reservation through last accepted D beat"},
  {"writer.state","captured packet/row until final client A enqueue; not memory completion"},
  {"writer.slot_residency","source xactBusy reservation through accepted client D acknowledgement"}
 }},pairs_{{std::size_t(Role::reader_slot),std::size_t(Role::execute_feed),0},
             {std::size_t(Role::writer_state),std::size_t(Role::execute_feed),0},
             {std::size_t(Role::reader_slot),std::size_t(Role::writer_state),0}} {
  if(!bound_||bound_>1048576)throw std::invalid_argument("invalid source actor diagnostic bound");
 }
 void role(Role role,std::uint64_t capacity){const auto i=std::size_t(role);if(i>=N||rows_[i].covered){unavailable("duplicate or unknown source role declaration");return;}rows_[i].covered=true;rows_[i].capacity=capacity;}
 void unavailable(const std::string&r){if(reason_.empty())reason_=r;}
 void edge(Role role,std::uint64_t id,Cycle at,bool begin){
  if(closed_||!reason_.empty())return;
  auto r=std::size_t(role);if(r>=N||at<cursor_){unavailable("source edge precedes committed watermark or has unknown role");return;}
  const auto key=std::make_pair(r,id);
  if(begin){if(open_.size()>=bound_||open_.count(key)){unavailable("source actor identity or open capacity");return;}open_[key]=at;}
  else {auto it=open_.find(key);if(it==open_.end()||at<it->second){unavailable("source actor close lacks matching start");return;}open_.erase(it);}
  if(pending_>=bound_){unavailable("source actor pending edge capacity");return;}
  edges_[at].push_back({r,begin?1:-1});++pending_;
 }
 void begin(std::optional<Cycle>at){if(first_||!at||*at<cursor_){unavailable("source ROI opening unavailable");return;}first_=at;}
 void end(std::optional<Cycle>at){if(!first_||!at||*at<*first_||*at<cursor_){unavailable("source ROI closing unavailable");closed_=true;return;}last_=at;advance(*at);closed_=true;}
 void advance(Cycle at){
  if(closed_||!reason_.empty())return;
  if(at<cursor_){unavailable("nonmonotonic source watermark");return;}
  while(!edges_.empty()&&edges_.begin()->first<=at){auto it=edges_.begin();integrate(it->first);for(auto e:it->second){auto&r=rows_[e.row];r.live+=e.delta;if(r.live<0||(r.capacity&&std::uint64_t(r.live)>r.capacity)){unavailable("source occupancy underflow");return;}if(e.delta>0&&first_&&it->first>=*first_&&(!last_||it->first<*last_))++r.starts;}pending_-=it->second.size();edges_.erase(it);}integrate(at);
 }
 bool complete()const{return reason_.empty()&&first_&&last_&&*last_>*first_;}
 const auto&rows()const{return rows_;}const auto&pairs()const{return pairs_;}
 const auto&reason()const{return reason_;}auto first()const{return first_;}auto last()const{return last_;}
private:
 struct Edge{std::size_t row;int delta;};std::size_t bound_,pending_=0;
 std::array<Row,N>rows_;std::vector<Pair>pairs_;std::map<Cycle,std::vector<Edge>>edges_;
 std::map<std::pair<std::size_t,std::uint64_t>,Cycle>open_;
 Cycle cursor_=0;std::optional<Cycle>first_,last_;std::string reason_;bool closed_=false;
 void add(std::uint64_t&n,Cycle d,std::uint64_t units=1){if((units&&d>UINT64_MAX/units)||n>UINT64_MAX-d*units){unavailable("source activity integral overflow");return;}n+=d*units;}
 void integrate(Cycle at){auto a=std::max(cursor_,first_.value_or(at)),b=std::min(at,last_.value_or(at));if(b>a){for(auto&r:rows_)if(r.live>0){add(r.active,b-a);add(r.units,b-a,r.live);r.peak=std::max(r.peak,std::uint64_t(r.live));}for(auto&p:pairs_)if(rows_[p.left].live&&rows_[p.right].live)add(p.active,b-a);}cursor_=at;}
};
}
#endif
