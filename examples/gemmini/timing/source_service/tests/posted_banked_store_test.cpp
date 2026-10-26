#include "posted_banked_store.hpp"
#include <cassert>
using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;using P=PostedBankedStore::Port;
int main(){
 Q q({128,128,1000});PostedBankedStore bank(q,8);std::vector<std::pair<unsigned,unsigned>>accepted;
 // Deliberately offer in reverse priority order. The two-bank blocked
 // SourceC request prevents a lower request cutting into its unused bank.
 bank.offer(P::source_d_write,2,[&](auto t){accepted.emplace_back(3,t);},0);
 bank.offer(P::source_c,3,[&](auto t){accepted.emplace_back(1,t);},0);
 bank.offer(P::sink_c,1,[&](auto t){accepted.emplace_back(0,t);},0);
 bank.offer(P::sink_d,4,[&](auto t){accepted.emplace_back(2,t);},0);
 while(q.step(true)){}assert(!q.progress().failed&&!bank.busy());
 assert((accepted==std::vector<std::pair<unsigned,unsigned>>{{0,0},{2,0},{1,1},{3,2}}));
 // A genuinely late same-edge hardware offer is refused, never silently
 // assigned a next-edge delay or allowed to preempt a committed request.
 Q late({32,32,64});PostedBankedStore latebank(late,8);
 latebank.offer(P::source_d_write,1,[&](auto t){latebank.offer(P::sink_c,1,[](auto){},t);},0);
 while(late.step(true)){}assert(late.progress().failed&&late.reason().find("late BankedStore request after settled edge")==0);
}
