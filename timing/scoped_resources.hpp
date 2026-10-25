#ifndef SPIKE_TIMING_SCOPED_RESOURCES_HPP
#define SPIKE_TIMING_SCOPED_RESOURCES_HPP
#include "core/include/merlin_timing/engine.hpp"
#include <map>
#include <string>

namespace spike_timing {
// Bounded online sweep of *modeled reservations*. Cross-window bookings are
// retained as pending endpoints, not replayed from instruction-count deltas.
class ScopedResources {
public:
  using Cycle=merlin_timing::Cycle;
  struct Row {
    merlin_timing::ResourceId id;std::size_t capacity;
    uint64_t busy=0,active=0,queued=0,queue_active=0,peak_units=0,peak_queue=0;
    int64_t units=0,waiting=0;
  };
  struct Pair {std::size_t left,right;uint64_t active=0;};
  explicit ScopedResources(const std::vector<merlin_timing::ResourceSpec>& resources):rows_{} {
    for(const auto& r:resources){index_[r.id]=rows_.size();rows_.push_back({r.id,r.capacity});}
  }
  void pair(uint32_t left,uint32_t right) {
    if(pairs_.size()>=32||left==right||!index_.count(left)||!index_.count(right))
      throw std::invalid_argument("invalid scoped overlap pair");
    for(const auto& p:pairs_)if((rows_[p.left].id==left&&rows_[p.right].id==right)||
        (rows_[p.left].id==right&&rows_[p.right].id==left))throw std::invalid_argument("duplicate scoped overlap pair");
    pairs_.push_back({index_.at(left),index_.at(right)});
  }
  void begin(std::optional<Cycle> cycle) {
    if(begin_||!cycle||*cycle<cursor_){complete_=false;return;}begin_=cycle;
  }
  void end(std::optional<Cycle> cycle) {
    if(!begin_||!cycle||*cycle<*begin_||*cycle<cursor_){complete_=false;closed_=true;return;}
    end_=cycle;advance(*cycle);closed_=true;
  }
  void record(const merlin_timing::Trace& trace) {
    if(closed_||!complete_)return;
    if(trace.frontier_before)advance(*trace.frontier_before);
    else {complete_=false;return;}
    if(std::string(trace.action)!="submit"&&std::string(trace.action)!="submit_detached")return;
    if(trace.result.unknown!=merlin_timing::UnknownReason::none){complete_=false;return;}
    for(std::size_t i=0;i<trace.event.demands.size;++i){
      const auto& d=trace.event.demands[i];
      if(!trace.result.start||!trace.result.issue||!d.occupancy||
          *d.occupancy>UINT64_MAX-*trace.result.start||!index_.count(d.resource)) {complete_=false;return;}
      const auto key=index_.at(d.resource);
      interval(*trace.result.start,*trace.result.start+*d.occupancy,key,d.units,false);
      interval(*trace.result.issue,*trace.result.start,key,1,true);
    }
  }
  bool complete()const{return complete_&&begin_&&end_&&*end_>*begin_;}
  std::optional<Cycle> first()const{return begin_;}
  std::optional<Cycle> last()const{return end_;}
  const std::vector<Row>& rows()const{return rows_;}
  const std::vector<Pair>& pairs()const{return pairs_;}
private:
  struct Edge{std::size_t resource;int64_t amount;bool queue;};
  static constexpr std::size_t max_pending_edges=65536;
  std::map<Cycle,std::vector<Edge>> edges_;
  std::map<uint32_t,std::size_t> index_;
  std::vector<Row> rows_;std::vector<Pair> pairs_;
  std::optional<Cycle> begin_,end_;Cycle cursor_=0;
  std::size_t pending_=0;bool complete_=true,closed_=false;
  void add(uint64_t& destination,uint64_t cycles,uint64_t units=1){
    if(units&&cycles>UINT64_MAX/units){complete_=false;return;}
    const auto amount=cycles*units;if(destination>UINT64_MAX-amount){complete_=false;return;}destination+=amount;
  }
  void integrate(Cycle next){
    if(next<cursor_){complete_=false;return;}
    const auto first=std::max(cursor_,begin_.value_or(next));
    const auto last=std::min(next,end_.value_or(next));
    if(last>first){
      const auto elapsed=last-first;
      for(auto& r:rows_){
        if(r.units<0||r.waiting<0||uint64_t(r.units)>r.capacity){complete_=false;continue;}
        add(r.busy,elapsed,r.units);add(r.queued,elapsed,r.waiting);
        if(r.units)add(r.active,elapsed);if(r.waiting)add(r.queue_active,elapsed);
        r.peak_units=std::max(r.peak_units,uint64_t(r.units));r.peak_queue=std::max(r.peak_queue,uint64_t(r.waiting));
      }
      for(auto& p:pairs_)if(rows_[p.left].units&&rows_[p.right].units)add(p.active,elapsed);
    }
    cursor_=next;
  }
  void advance(Cycle next){
    if(next<cursor_){complete_=false;return;}
    while(!edges_.empty()&&edges_.begin()->first<=next){
      auto found=edges_.begin();integrate(found->first);
      for(const auto& e:found->second){auto& r=rows_[e.resource];(e.queue?r.waiting:r.units)+=e.amount;--pending_;}
      edges_.erase(found);
    }
    integrate(next);
  }
  void interval(Cycle first,Cycle last,std::size_t resource,uint64_t units,bool queue){
    if(last<first||first<cursor_||units>INT64_MAX||pending_>max_pending_edges-2){complete_=false;return;}
    if(first==last||units==0)return;
    edges_[first].push_back({resource,int64_t(units),queue});edges_[last].push_back({resource,-int64_t(units),queue});pending_+=2;
  }
};
}
#endif
