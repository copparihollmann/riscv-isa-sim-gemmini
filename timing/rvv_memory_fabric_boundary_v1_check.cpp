#include "rvv_memory_fabric_boundary_v1.hpp"
#include "VStoreRob.h"
#include "verilated.h"
#include <algorithm>
#include <iostream>
#include <memory>
#include <random>
#include <string>
#include <vector>
using namespace iris::rvv_memory_boundary_v1;
namespace {
std::uint64_t checks=0,edges=0,full_edges=0,forwarded=0,out_of_order=0,simultaneous=0,wraps=0;
std::string mutant;
void need(bool ok,const char*why){++checks;if(!ok)throw std::runtime_error(why);}
template<class F>void refuse(F f){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}need(rejected,"required sidecar/phase refusal missing");}
struct Fixture {
 VerilatedContext context;
 std::unique_ptr<VStoreRob> rtl;
 ComputeStoreRob model;
 std::vector<unsigned>owned;
 std::array<bool,16>acked{};
 unsigned head=0,last_tag=15;
 explicit Fixture(unsigned seed){const char*args[]={"store-ROB-source-check"};context.commandArgs(1,args);context.threads(1);context.randSeed(seed);context.randReset(2);rtl=std::make_unique<VStoreRob>(&context);step({true,false,false,0,false,true});}
 void step(RobInput input){
  model.evaluate(input);auto a=model.sample();
  rtl->clock=0;rtl->reset=input.reset;rtl->io_reserve_ready=input.reserve_ready;
  rtl->io_push_valid=input.push_valid;rtl->io_push_bits_tag=input.push_tag;rtl->io_deq_ready=input.deq_ready;rtl->eval();
  if(a.qualified){
   if(mutant=="full-admit"&&!a.reserve_valid)a.reserve_valid=true;
   if(mutant=="no-head-forward"&&input.push_valid&&input.push_tag==head&&!acked[head])a.deq_valid=false;
   need(a.reserve_valid==bool(rtl->io_reserve_valid),"source ROB reserve-valid mismatch");
   need(a.reserve_tag==rtl->io_reserve_bits,"source ROB circular tag mismatch");
   need(a.deq_valid==bool(rtl->io_deq_valid),"source ROB completion/forwarding mismatch");
  }
  if(!input.reset){
   need(a.busy==!owned.empty(),"source pointer occupancy differs from independent owner ledger");
   full_edges+=!a.reserve_valid;
   forwarded+=a.deq_fire&&input.push_valid&&input.push_tag==head&&!acked[head];
   if(input.push_valid){need(std::find(owned.begin(),owned.end(),input.push_tag)!=owned.end(),"driver ACK not reserved");out_of_order+=input.push_tag!=head;acked[input.push_tag]=true;}
   simultaneous+=a.reserve_fire&&a.deq_fire;
   if(a.deq_fire){need(!owned.empty()&&owned.front()==head&&acked[head],"driver source-ordered retirement mismatch");owned.erase(owned.begin());acked[head]=false;head=(head+1)&15;}
   if(a.reserve_fire){need(std::find(owned.begin(),owned.end(),a.reserve_tag)==owned.end(),"driver premature tag reuse");wraps+=a.reserve_tag==0&&last_tag==15;last_tag=a.reserve_tag;owned.push_back(a.reserve_tag);}
  }else{owned.clear();acked.fill(false);head=0;}
  rtl->clock=1;rtl->eval();model.commit();rtl->clock=0;rtl->eval();++edges;
 }
 void run(unsigned seed){
  // Fill all sixteen entries, acknowledge nonheads first, hold/release head.
  for(unsigned i=0;i<16;++i)step({false,true,false,0,false,true});
  step({false,true,false,0,false,true});
  for(unsigned i=15;i>0;--i)step({false,true,true,i,true,true});
  step({false,true,true,0,true,true});
  for(unsigned i=0;i<20;++i)step({false,true,false,0,true,true});
  std::mt19937 rng(seed);
  for(unsigned i=0;i<100000;++i){
   std::vector<unsigned>eligible;for(auto t:owned)if(!acked[t])eligible.push_back(t);
   bool push=!eligible.empty()&&(rng()%4!=0);unsigned tag=push?eligible[rng()%eligible.size()]:0;
   step({false,bool(rng()&1),push,tag,bool(rng()%4),true});
  }
  unsigned bound=0;
  while(!owned.empty()){
   need(++bound<100,"ROB did not drain");unsigned tag=owned.front();
   step({false,false,!acked[tag],tag,true,true});
  }
 }
};
void sidecars(){
 SourceClocks clocks(1000000000,500000000,{2,2,1,10},{0,0,0,0});
 unsigned uncore=0,bringup=0,serial=0;
 for(unsigned t=0;t<1000;++t){auto e=clocks.edges(t);auto s=clocks.stamp(t);
  if(mutant=="drop-half")s.native_half=false;
  need(s.master_tick==2*s.native_whole+unsigned(s.native_half),"lost half-native-cycle event");
  need(e.rocket==e.uncore,"qualified equal-period domains differ");uncore+=e.uncore;bringup+=e.bringup;serial+=e.serial;
 }
 need(uncore==500&&bringup==1000&&serial==100,"master/native clock unit mismatch");
 refuse([]{SourceClocks x(500000000,500000000,{2,2,1,10},{0,0,0,0});});
 refuse([]{SourceClocks x(1000000000,500000000,{2,2,1,10},{2,0,0,0});});
 ComputeStoreRob rob;
 refuse([&]{rob.evaluate({false,false,false,0,false,true});});
 refuse([&]{rob.evaluate({true,false,false,0,false,false});});
 refuse([&]{rob.sample();});
 refuse([&]{rob.commit();});
 rob.evaluate({true,false,false,0,false,true});rob.commit();
 refuse([&]{rob.evaluate({false,false,true,16,false,true});});
 StoreOwners h0(0),h1(1);
 refuse([]{StoreOwners h2(2);});
 for(unsigned n=0;n<16;++n){auto a=h0.reserve(n,100+n,16),b=h1.reserve(n,200+n,16);h0.accept_A(n,a.generation);h1.accept_A(n,b.generation);need(a.hart!=b.hart&&a.tag==b.tag,"hart ownership collision");}
 refuse([&]{h0.reserve(0,999,16);});
 h0.ack(15,false,false,true);
 refuse([&]{h0.retire(15);});
 refuse([&]{h0.reserve(0,999,16);});
 refuse([&]{h0.ack(15,false,false,true);});
 refuse([&]{h0.ack(16,false,false,true);});
 refuse([&]{h0.ack(0,true,false,true);});
 refuse([&]{h0.ack(0,false,true,true);});
 refuse([&]{h0.ack(0,false,false,false);});
 for(unsigned n=0;n<16;++n){if(n!=15)h0.ack(n,false,false,true);h0.retire(n);h1.ack(n,false,false,true);h1.retire(n);}
 need(!h0.pending()&&!h1.pending(),"owner ledger failed to drain");
 auto reused=h0.reserve(0,999,4);
 refuse([&]{h0.accept_A(0,1);});
 refuse([&]{h0.ack(0,false,false,true);});
 h0.accept_A(0,reused.generation);auto a=h0.ack(0,false,false,true);
 need(a.command==999&&a.generation==reused.generation&&a.bytes==4,"tag reuse attributed to old command");h0.retire(0);
 refuse([&]{h0.ack(0,false,false,true);});
 for(unsigned t=0;t<16;++t){auto source=StoreOwners::physical_store_source(t);if(mutant=="writer-high-bit")source|=16;need(source==t&&source<16,"writer mapped into reader source range");}
 refuse([]{StoreOwners::physical_store_source(16);});
}
}
int main(int argc,char**argv){try{
 if(argc==3&&std::string(argv[1])=="--mutant")mutant=argv[2];else if(argc!=1)throw std::invalid_argument("unknown arguments");
 for(unsigned seed:{1U,17U,31U}){Fixture f(seed);f.run(seed);}
 sidecars();
 need(full_edges&&forwarded&&out_of_order&&simultaneous&&wraps>100,"missing source transition coverage");
 std::cout<<"{\"pass\":true,\"RTL_edges\":"<<edges<<",\"checks\":"<<checks<<",\"full_edges\":"<<full_edges<<",\"head_ACK_forwarding\":"<<forwarded<<",\"out_of_order_ACKs\":"<<out_of_order<<",\"simultaneous_reserve_dequeue\":"<<simultaneous<<",\"tag_wraps\":"<<wraps<<"}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
