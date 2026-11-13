#include "overlap_completion_command_queues_v2.hpp"
#include <iostream>
#include <random>
using namespace iris::opu_entry;
int main(){try{
 std::mt19937_64 rng(11);CommandQueues plain;CommandQueuesPhased late,early;unsigned checks=0,accepts=0,full=0,micro=0;std::optional<Command>pending;uint64_t id=0;
 for(uint64_t edge=0;edge<100000;++edge){
  if(!pending&&(rng()%4))pending=Command{++id,unsigned(rng()%4),unsigned(8U<<(rng()%3)),unsigned(8U<<(rng()%3)),bool(rng()&1)};
  auto a=plain.step(edge,pending);auto b=late.advance(edge);if(pending)b=late.commit_input(edge,*pending);
  // The early CPU callback settles first, commits its input, then the later
  // queue driver observes last_edge==edge and performs no second transition.
  auto c=early.step(edge,pending);if(early.last_edge()!=edge)throw std::runtime_error("driver must skip completed same edge");
  if(!CommandQueuesPhased::same_old_state_events(a,b)||!CommandQueuesPhased::same_old_state_events(a,c)||a.input_fire!=b.input_fire||a.input_fire!=c.input_fire||plain.buffered()!=late.buffered()||plain.buffered()!=early.buffered())throw std::runtime_error("phase ordering differs");
  checks+=7;full+=!a.input_ready;micro+=bool(a.issue);if(a.input_fire){++accepts;pending.reset();}
 }
 unsigned rejects=0;auto reject=[&](auto f){try{f();}catch(const std::logic_error&){++rejects;return;}throw std::runtime_error("invalid phase accepted");};
 reject([&]{late.advance(99999);});reject([&]{late.commit_input(99998,Command{1,0,16,16,true});});
 CommandQueuesPhased q;reject([&]{q.commit_input(0,Command{1,0,16,16,true});});q.advance(0);q.commit_input(0,Command{1,0,16,16,true});reject([&]{q.commit_input(0,Command{2,0,16,16,true});});
 if(!full||!micro||!accepts||rejects!=4)throw std::runtime_error("insufficient coverage");
 std::cout<<"{\"pass\":true,\"edges\":100000,\"checks\":"<<checks<<",\"accepted\":"<<accepts<<",\"full_edges\":"<<full<<",\"microissues\":"<<micro<<",\"phase_refusals\":"<<rejects<<"}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
