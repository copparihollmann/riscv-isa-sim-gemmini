#include "frontend_values_fabric.hpp"
#include <iostream>
#include <stdexcept>
using Values=iris::frontend::ForwardedValues;
static unsigned checks=0,refusals=0;
static void check(bool value,const char*why){++checks;if(!value)throw std::runtime_error(why);}
template<class F>static void rejects(F f){try{f();}catch(const std::logic_error&){++refusals;return;}throw std::runtime_error("missing pending-load guard");}
static uint32_t addi(unsigned rd,unsigned rs,unsigned imm){return imm<<20|rs<<15|rd<<7|0x13;}
int main(){try{
  Values::Snapshot initial{};initial[1]=0;initial[2]=11;
  Values flow(initial,32);uint64_t tag=0;
  for(unsigned round=0;round<5000;++round){
    const auto first=tag++;flow.issue_external(first,5);auto load_source=flow.latch(5,0);flow.retire_pending_external(first);
    check(flow.retained_records()==0&&flow.pending_external_count()==1,"WB releases instruction record while retaining one physical destination");
    check(!flow.architectural()[5],"retired missing load data remains unknown");
    rejects([&]{flow.read(load_source);});rejects([&]{flow.future(5);});rejects([&]{flow.issue(tag,addi(5,0,1),0);});
    // Source whole-CPU witness has twelve independent retirements while a
    // load waits. Repeat them here without retaining their COM history.
    for(unsigned n=0;n<12;++n){const auto next=tag++;flow.issue(next,addi(1,1,1),0x80000000+4*n);auto result=flow.complete(next);flow.commit(next,result);}
    check(flow.retained_records()==0&&flow.architectural()[1]==Values::Value(uint64_t(round+1)*12),"independent ALUs retire while source load result pending");
    rejects([&]{flow.complete_retired_external(5,first+1,77);});
    flow.complete_retired_external(5,first,uint64_t(round)+77);
    check(flow.read(load_source)[0]==Values::Value(uint64_t(round)+77)&&flow.future(5)==Values::Value(uint64_t(round)+77),"actual late response completes original version and clears scoreboard");
    check(flow.pending_external_count()==0&&flow.live_cells()<=1,"retired history stays bounded");
  }
  Values parallel(initial,32);parallel.issue_external(1,8);parallel.retire_pending_external(1);parallel.issue_external(2,9);parallel.retire_pending_external(2);
  parallel.issue(3,addi(10,0,7),0);parallel.complete(3);parallel.discard_younger(2);
  check(parallel.pending_external_count()==2,"wrong-path younger cancellation preserves accepted older loads");
  rejects([&]{parallel.future(8);});rejects([&]{parallel.future(9);});parallel.complete_retired_external(9,2,92);parallel.complete_retired_external(8,1,81);
  check(parallel.future(8)==Values::Value(81)&&parallel.future(9)==Values::Value(92),"source late results can arrive out of architectural order");
  rejects([&]{parallel.complete_retired_external(8,1,81);});
  parallel.issue_external(4,0);rejects([&]{parallel.retire_pending_external(4);});parallel.complete_external(4,0);parallel.commit(4,0);
  Values replay(initial,32);replay.issue_external(1,5);replay.issue(2,addi(5,0,9),0);replay.complete(2);replay.retire_pending_external(1);
  replay.issue(3,addi(6,0,10),4);rejects([&]{replay.annul_replayed(2);});replay.discard_younger(2);replay.annul_replayed(2);
  rejects([&]{replay.future(5);});replay.complete_retired_external(5,1,123);
  check(replay.future(5)==Values::Value(123),"source WAW/load-use replay restores older pending-load version");
  check(flow.peak_records()==1&&flow.peak_cells()<=3,"65k-instruction stream has constant bounded active storage");
  std::cout<<"{\"status\":\"passed_bounded_early_retire_late_result\",\"retired_loads\":5000,\"independent_alu_retirements\":60000,\"checks\":"<<checks<<",\"guard_refusals\":"<<refusals<<",\"peak_cells\":"<<flow.peak_cells()<<"}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
