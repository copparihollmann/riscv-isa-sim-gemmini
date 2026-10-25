#ifndef GEMMINI_POSTED_BANKED_STORE_HPP
#define GEMMINI_POSTED_BANKED_STORE_HPP
#include <merlin_timing/posted_timeline.hpp>
#include <array>
#include <deque>
namespace gemmini_annotated_spike {
// Exact selected BankedStore request priority. A blocked high-priority mask
// still blocks overlapping lower-priority requests (no cutting in line).
// Noop reserves the same mask while leaving SRAM data unchanged. The owner
// supplies that mask and the accepted callback; no price/cycle law lives here.
class PostedBankedStore {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
 public:
 enum class Port:unsigned{sink_c,source_c,sink_d,source_d_write,source_d_read};
 using Accept=std::function<void(Cycle)>;
 private:
 struct Request{std::uint64_t mask;Accept accepted;};
 Q&q_;unsigned banks_;std::array<std::deque<Request>,5>pending_;
 std::optional<Cycle>scheduled_,settled_;std::array<std::optional<Cycle>,5>fired_;
 void schedule(Cycle at){
   if(scheduled_&&*scheduled_<=at)return;
   scheduled_=at;
   q_.post_settled(at,{},[this,at](auto&,auto t){
     if(scheduled_!=std::optional<Cycle>{at})return;
     scheduled_.reset();settle(t);
   },Q::Kind::local_publish);
 }
 void settle(Cycle at){
   if(settled_==std::optional<Cycle>{at}){q_.fail("repeated BankedStore settled edge");return;}
   settled_=at;std::uint64_t higher=0;
   std::vector<Accept>accepted;
   for(unsigned p=0;p<pending_.size();++p){
     auto&requests=pending_[p];if(requests.empty())continue;
     const auto mask=requests.front().mask;
     if(!(mask&higher)&&fired_[p]!=std::optional<Cycle>{at}){
       accepted.push_back(std::move(requests.front().accepted));requests.pop_front();fired_[p]=at;
     }
     higher|=mask; // valid blocked/noop requests also contribute bankSum
   }
   for(auto&fire:accepted)fire(at);
   for(const auto&p:pending_)if(!p.empty()){schedule(at+1);break;}
 }
 public:
 PostedBankedStore(Q&q,unsigned banks):q_(q),banks_(banks){if(!banks||banks>64)throw std::invalid_argument("bounded BankedStore geometry required");}
 void offer(Port port,std::uint64_t mask,Accept accepted,Cycle at){
   const auto p=unsigned(port);
   if(p>=pending_.size()||!mask||(banks_<64&&(mask>>banks_))||!accepted){q_.fail("invalid BankedStore request");return;}
   q_.post(at,{},[this,p,mask,accepted=std::move(accepted)](auto&,auto t)mutable{
     // A registered source must expose a newly enabled request on its real
     // next edge. Backdating it after arbitration is neither a priority
     // discount nor permission to erase an already committed SRAM request.
     if(settled_==std::optional<Cycle>{t}){q_.fail("late BankedStore request after settled edge, port="+std::to_string(p)+", mask="+std::to_string(mask));return;}
     if(pending_[p].size()>=16){q_.fail("BankedStore source custody bound");return;}
     pending_[p].push_back({mask,std::move(accepted)});schedule(t);
   },Q::Kind::source_arrival);
 }
 bool busy()const{for(const auto&p:pending_)if(!p.empty())return true;return bool(scheduled_);}
};
}
#endif
