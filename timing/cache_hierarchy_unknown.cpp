// Minimal full saved-cache witness. Private source state is read for this proof,
// never driven or copied from the whole-SoC reference.
#include "VCacheShuttle.h"
#include "VCacheShuttle___024root.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <vector>
struct QueueView{unsigned state,enq,deq;bool full,write;};
struct Frame{unsigned cycle,ready,cmd,valid,counter,selected,slot,known;};
struct Test{
 std::unique_ptr<VerilatedContext>ctx=std::make_unique<VerilatedContext>();
 std::unique_ptr<VCacheShuttle>cache;
 std::array<std::array<bool,16>,4>known{};
 unsigned cycle=0,writes=0,dequeues=0;
 explicit Test(unsigned seed){ctx->randReset(2);ctx->randSeed(seed);cache=std::make_unique<VCacheShuttle>(ctx.get());auto&m=*cache;
 #include "cache_hierarchy_zero_inputs.inc"
 m.clock=0;m.auto_out_c_ready=1;m.auto_out_e_ready=1;
 }
 std::array<QueueView,4>queues(){const auto&r=*cache->rootp;
 #include "cache_hierarchy_queue_views.inc"
 }
 Frame evaluate(){auto&m=*cache;m.eval();auto q=queues();unsigned selected=3;
  for(unsigned i=0;i<3;++i)if(q[i].state==8&&(q[i].full||q[i].enq!=q[i].deq)){selected=i;break;}
  auto&r=*m.rootp;return{cycle,unsigned(m.io_req_ready),unsigned(r.ShuttleDCache__DOT___mshrs_io_replay_bits_cmd),unsigned(r.ShuttleDCache__DOT___mshrs_io_replay_valid),unsigned(r.ShuttleDCache__DOT__stall_ctr),selected,q[selected].deq,known[selected][q[selected].deq]};
 }
 Frame tick(){auto f=evaluate();auto q=queues();auto&m=*cache;bool reset=m.reset;
  m.clock=1;m.eval();m.clock=0;m.eval();++cycle;
  if(!reset)for(unsigned i=0;i<4;++i)if(q[i].write){known[i][q[i].enq]=true;++writes;}
  auto next=queues();if(!reset)for(unsigned i=0;i<4;++i)if(next[i].deq!=q[i].deq)++dequeues;
  return f;
 }
 void reset(){cache->reset=1;for(unsigned n=0;n<8;++n)tick();cache->reset=0;for(unsigned n=0;n<160;++n)tick();}
 void load(unsigned line){auto&m=*cache;m.io_req_bits_cmd=0;m.io_req_bits_size=3;m.io_req_bits_tag=line;m.io_req_bits_addr=0x80000000ULL+line*64;m.io_s1_paddr=m.io_req_bits_addr;m.io_req_valid=1;
  unsigned count=0;while(!tick().ready)if(++count>100)throw std::runtime_error("queue initializer request blocked");m.io_req_valid=0;for(unsigned n=0;n<8;++n)tick();}
};
static void print(const Frame&f){std::cout<<"{\"cycle\":"<<f.cycle<<",\"ready\":"<<f.ready<<",\"replay_cmd\":"<<f.cmd<<",\"replay_valid\":"<<f.valid<<",\"stall_counter\":"<<f.counter<<",\"selected_queue\":"<<f.selected<<",\"head_slot\":"<<f.slot<<",\"head_defined_by_accepted_write\":"<<(f.known?"true":"false")<<'}';}
int main(){try{
 std::cout<<"{\"schema\":\"iris.shuttle_invalid_replay_control_witness.v1\",\"source_logic_modified\":false,\"internal_state_injected\":false,\"seeds\":[";
 bool comma=false;for(unsigned seed:{0,1,7,31,113,257,65537}){
  if(comma)std::cout<<',';comma=true;Test t(seed);t.reset();auto&m=*t.cache;m.io_req_valid=1;m.io_req_bits_cmd=1;m.io_req_bits_size=3;m.io_req_bits_addr=0x80000000;m.io_s1_paddr=0x80000000;m.io_s1_data_data=0x1234;
  std::cout<<"{\"seed\":"<<seed<<",\"same_external_store_burst\":[";
  unsigned accepted_stores=0,burst_cycles=0;
  while(accepted_stores<4){m.io_req_bits_tag=accepted_stores;if(burst_cycles)std::cout<<',';auto frame=t.tick();print(frame);accepted_stores+=frame.ready;if(++burst_cycles>32)throw std::runtime_error("four-store witness did not progress");}
  std::cout<<"],\"accepted_stores\":4,\"cycles_until_four_accepts\":"<<burst_cycles<<'}';
 }
 std::cout<<"],\"accepted_queue_write_bound\":[";comma=false;
 for(unsigned seed:{1,7,31,113}){
  if(comma)std::cout<<',';comma=true;Test t(seed);t.reset();auto&m=*t.cache;auto before=t.evaluate();
  for(unsigned line=0;line<4;++line)t.load(line);auto after=t.evaluate();
  if(!after.known||after.selected!=3||after.slot!=0||after.cmd!=0||t.writes<4)throw std::runtime_error("genuine accepted queue writes did not define queue3 head");
  m.auto_out_a_ready=1;unsigned accepted=0;for(unsigned n=0;n<50&&accepted!=15;++n){t.evaluate();if(m.auto_out_a_valid&&m.auto_out_a_ready)accepted|=1<<m.auto_out_a_bits_source;t.tick();}if(accepted!=15)throw std::runtime_error("all four source IDs must be genuinely accepted before the source3 grant");
  // Sample A handshake directly before commit, including the first available A.
  // All sources have already been accepted after this bounded drain; individual
  // source3 refill is independent and legal in TileLink's source-ID ordering.
  m.auto_out_d_valid=1;m.auto_out_d_bits_opcode=5;m.auto_out_d_bits_param=0;m.auto_out_d_bits_size=6;m.auto_out_d_bits_source=3;m.auto_out_d_bits_sink=0;
  for(unsigned beat=0;beat<8;++beat){m.auto_out_d_bits_data=0x12340000+beat;unsigned tries=0;do{t.evaluate();bool ready=m.auto_out_d_ready;t.tick();if(ready)break;if(++tries>100)throw std::runtime_error("source3 grant readiness");}while(true);}
  m.auto_out_d_valid=0;Frame advanced{};bool changed=false;
  for(unsigned n=0;n<100;++n){advanced=t.tick();if(advanced.selected==3&&advanced.slot==1){changed=true;break;}}
  if(!changed||advanced.known)throw std::runtime_error("unwritten next queue slot was incorrectly declared defined");
  std::cout<<"{\"seed\":"<<seed<<",\"before\":";print(before);std::cout<<",\"after_real_enqueues\":";print(after);std::cout<<",\"after_real_dequeue\":";print(advanced);std::cout<<",\"accepted_ram_writes\":"<<t.writes<<",\"dequeues\":"<<t.dequeues<<'}';
 }
 std::cout<<"],\"scope\":\"One source-proven undefined timing dependency; not a proof that all other reset control is defined\",\"hardware_contacted\":false,\"timing_certified\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<"CACHE_UNKNOWN_WITNESS_FAILED: "<<e.what()<<'\n';return 1;}}
