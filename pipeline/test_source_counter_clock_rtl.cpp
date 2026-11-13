#include "VWfiPair.h"
#include "source_counter_clock.hpp"
#include <cstdint>
#include <iostream>
#include <stdexcept>

struct Probe {
  VWfiPair d;unsigned edges=0,checks=0;uint64_t mie=0;
  iris::frontend::SourceCounterClock shuttle{1},rocket{1};
  void edge(bool pipeline=true) {
    d.clock=d.ungated_clock=0;d.eval();d.clock=pipeline;d.ungated_clock=1;d.eval();d.clock=d.ungated_clock=0;d.eval();++edges;
  }
  void reset() {
    d.clock=d.ungated_clock=0;d.reset=1;d.address=d.instruction=d.cmd=d.write_data=d.retire=d.msip=d.mtip=d.exception=0;
    edge();edge();d.reset=0;d.eval();
  }
  uint64_t read(bool rocket=false) {d.address=0xc00;d.cmd=2;d.eval();return rocket?d.rocket_data:d.shuttle_data;}
  void operation(const char* name,unsigned address,unsigned cmd,uint64_t data,unsigned retire,bool pipeline,bool msip=false,bool mtip=false,bool hold=false,bool exception=false) {
    const auto before_s=read(),before_r=read(true);const bool stalled_s=d.shuttle_stall,stalled_r=d.rocket_stall;
    d.address=address;d.cmd=cmd;d.write_data=data;d.retire=retire;d.msip=msip;d.mtip=mtip;d.exception=exception;d.instruction=address<<20|0x73;d.eval();
    const bool pending=(msip&&(mie&8)) || (mtip&&(mie&128));
    const auto se=shuttle.sample(checks+1,{pending,{}}),re=rocket.sample(checks+1,{pending,{}});
    if(se.stall_before!=stalled_s || re.stall_before!=stalled_r)throw std::runtime_error("source counter state disagrees before edge");
    edge(pipeline);
    if(address==0x105 && cmd==4){shuttle.retire_wfi(checks+1);rocket.retire_wfi(checks+1);}
    if(address==0x305 && cmd==4){shuttle.retire_cease(checks+1);rocket.retire_cease(checks+1);}
    if(exception){shuttle.exception(checks+1);rocket.exception(checks+1);}
    if(address==0x304 && cmd==5)mie=data;
    const auto after_s=read(),after_r=read(true);
    if(shuttle.stalled()!=bool(d.shuttle_stall) || rocket.stalled()!=bool(d.rocket_stall))throw std::runtime_error("source counter state disagrees after edge");
    if(shuttle.blocks_rrd(checks+1)!=(se.stall_before||shuttle.stalled()) || rocket.blocks_rrd(checks+1)!=(re.stall_before||rocket.stalled()))throw std::runtime_error("source counter wake-edge RRD guard differs");
    // Fixed source rule: ungated edge, pre-edge csr_stall and old CY inhibit.
    // A B00 RW has source write priority over that increment.
    const auto expected_s=address==0xb00 && cmd==5?data:before_s+(!hold&&se.count_enable);
    const auto expected_r=address==0xb00 && cmd==5?data:before_r+(!hold&&re.count_enable);
    if(after_s!=expected_s || after_r!=expected_r)throw std::runtime_error(std::string("source WFI/counter edge differs: ")+name);
    ++checks;
    std::cout<<"{\"tag\":\""<<name<<"\",\"edge\":"<<edges<<",\"pipeline_clock_edge\":"<<pipeline<<",\"ungated_clock_edge\":true,\"msip\":"<<msip<<",\"mtip\":"<<mtip
      <<",\"source_cycle\":"<<checks<<",\"address\":"<<address<<",\"cmd\":"<<cmd<<",\"data\":"<<data<<",\"exception\":"<<exception<<",\"source_count_enable\":"<<se.count_enable<<",\"shuttle_before\":"<<before_s<<",\"shuttle_after\":"<<after_s<<",\"rocket_before\":"<<before_r<<",\"rocket_after\":"<<after_r
      <<",\"shuttle_stall_before\":"<<stalled_s<<",\"shuttle_stall_after\":"<<unsigned(d.shuttle_stall)<<",\"rocket_stall_before\":"<<stalled_r<<",\"rocket_stall_after\":"<<unsigned(d.rocket_stall)<<"}\n";
  }
};
int main() {
  Probe p;p.reset();
  p.operation("enable-local-msip",0x304,5,8,0,true);
  p.operation("initialize-cycle",0xb00,5,100,0,true);
  p.d.address=0x300;p.d.cmd=2;p.d.eval();
  if((p.d.shuttle_data|p.d.rocket_data)&8)throw std::runtime_error("global MIE is not zero in this source control");
  p.operation("enter-wfi",0x105,4,0,1,true);
  if(!p.d.shuttle_stall || !p.d.rocket_stall)throw std::runtime_error("source WFI did not stall");
  for(unsigned i=0;i<8;++i)p.operation("parked-running-clock",0,0,0,0,true);
  for(unsigned i=0;i<8;++i)p.operation("parked-gated-pipeline",0,0,0,0,false);
  p.operation("wake-msip-global-MIE-zero",0,0,0,0,false,true);
  if(p.d.shuttle_stall || p.d.rocket_stall)throw std::runtime_error("source locally enabled MSIP failed to clear WFI independently of gated pipeline");
  for(unsigned i=0;i<4;++i)p.operation("awake-gated-pipeline-ungated-counter",0,0,0,0,false);
  p.operation("resume-pipeline",0,0,0,0,true);
  p.operation("set-CY-inhibit",0x320,5,1,0,true);
  for(unsigned i=0;i<4;++i)p.operation("CY-inhibited-running-clock",0,0,0,0,true,false,false,true);
  p.operation("enter-wfi-with-CY-inhibited",0x105,4,0,1,true,false,false,true);
  for(unsigned i=0;i<4;++i)p.operation("parked-CY-inhibited",0,0,0,0,false,false,false,true);
  p.operation("wake-CY-inhibited",0,0,0,0,false,true,false,true);
  if(p.d.shuttle_stall || p.d.rocket_stall)throw std::runtime_error("source CY inhibit blocked WFI wake");
  p.operation("clear-CY-inhibit-old-value-wins",0x320,5,0,0,true,false,false,true);
  p.operation("resume-CY-counter",0,0,0,0,true);
  p.operation("enter-sticky-cease-CSR-component",0x305,4,0,1,true);
  for(unsigned i=0;i<4;++i)p.operation("cease-holds-despite-enabled-msip",0,0,0,0,false,true);
  p.operation("exception-does-not-clear-cease",0,0,0,0,true,false,false,false,true);
  if(!p.shuttle.ceased() || !p.rocket.ceased())throw std::runtime_error("CEASE lost sticky source state");
  if(p.checks!=44)throw std::runtime_error("incomplete WFI clock corpus");
}
