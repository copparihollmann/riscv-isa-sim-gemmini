#include "cache_hierarchy.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
using namespace iris::cache;
static unsigned checks=0;
static void expect(bool okay,const std::string&what){++checks;if(!okay)throw std::runtime_error(what);}
struct Bench {
 Model model;
 std::vector<Bits> in,out;
 // Semantic exploration is explicitly concrete; the default SDK policy refuses unknown control.
 explicit Bench(Component kind,unsigned seed,UnresetReplayPolicy policy=UnresetReplayPolicy::ExploreConcreteReset):model(kind,seed,policy),in(model.input_fields().size()),out(model.output_fields().size()){}
 unsigned index(std::span<const Field> fields,std::string_view name)const{
  for(unsigned i=0;i<fields.size();++i)if(fields[i].name==name)return i;
  throw std::invalid_argument("unknown physical field "+std::string(name));
 }
 void set(std::string_view name,std::uint64_t low){in[index(model.input_fields(),name)]=Bits(low);}
 void setwide(std::string_view name,Bits bits){in[index(model.input_fields(),name)]=bits;}
 std::uint64_t get(std::string_view name)const{return out[index(model.output_fields(),name)].limbs[0];}
 Bits wide(std::string_view name)const{return out[index(model.output_fields(),name)];}
 void eval(){model.evaluate(in);out=model.sample();}
 void tick(){eval();model.commit();}
 void reset(unsigned settle){set("reset",1);for(unsigned n=0;n<8;++n)tick();set("reset",0);for(unsigned n=0;n<settle;++n)tick();}
};
static std::uint64_t pattern(unsigned beat){return 0x1234000000000000ULL+beat;}
static void shuttle(unsigned seed){
 Bench b(Component::ShuttleL1D,seed);b.set("auto_out_a_ready",1);b.set("auto_out_c_ready",1);b.set("auto_out_e_ready",1);b.reset(160);
 expect(b.get("io_ordered"),"Shuttle cold cache must become ordered after actual reset sweep");
 auto issue=[&](unsigned cmd,unsigned tag,std::uint64_t data=0){
  b.set("io_req_bits_addr",0x80000008);b.set("io_s1_paddr",0x80000008);b.set("io_s1_data_data",data);
  b.set("io_req_bits_tag",tag);b.set("io_req_bits_cmd",cmd);b.set("io_req_bits_size",3);b.set("io_req_valid",1);
  unsigned wait=0;do{b.tick();expect(++wait<100,"Shuttle CPU request readiness bounded");}while(!b.get("io_req_ready"));
  b.set("io_req_valid",0);
 };
 b.set("auto_out_a_ready",0);issue(0,17);
 unsigned wait=0;while(!b.get("auto_out_a_valid")){b.tick();expect(++wait<40,"Shuttle cold read emits AcquireBlock");}
 expect(b.get("auto_out_a_bits_opcode")==6,"Shuttle cold load is AcquireBlock");
 expect(b.get("auto_out_a_bits_size")==6,"Shuttle cache refill is64B");
 expect(b.get("auto_out_a_bits_address")==0x80000000,"Shuttle cache refill address is line-aligned");
 auto source=b.get("auto_out_a_bits_source");
 for(unsigned n=0;n<9;++n){b.tick();expect(b.get("auto_out_a_valid"),"Shuttle blocked A stays valid");expect(b.get("auto_out_a_bits_source")==source,"Shuttle blocked A source remains stable");expect(!b.get("io_resp_valid"),"Shuttle no response without external service");}
 b.set("auto_out_a_ready",1);b.tick();
 for(unsigned n=0;n<30;++n){b.tick();expect(!b.get("io_resp_valid"),"Shuttle unknown service never gets a fabricated completion");}
 b.set("auto_out_d_valid",1);b.set("auto_out_d_bits_opcode",5);b.set("auto_out_d_bits_param",0);b.set("auto_out_d_bits_size",6);b.set("auto_out_d_bits_source",source);b.set("auto_out_d_bits_sink",0);
 unsigned acknowledgements=0;bool response=false;
 for(unsigned beat=0;beat<8;++beat){b.set("auto_out_d_bits_data",pattern(beat));unsigned retry=0;do{b.tick();if(b.get("auto_out_e_valid"))++acknowledgements;if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_tag")==17,"Shuttle refill response tag");expect(b.get("io_resp_bits_data")==pattern(1),"Shuttle refill load data independent memory oracle");}expect(++retry<60,"Shuttle D backpressure bounded");}while(!b.get("auto_out_d_ready"));}
 b.set("auto_out_d_valid",0);
 for(unsigned n=0;n<40;++n){b.tick();if(b.get("auto_out_e_valid"))++acknowledgements;if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_tag")==17,"Shuttle replay tag");expect(b.get("io_resp_bits_data")==pattern(1),"Shuttle replay data");}}
 expect(response,"Shuttle refill eventually replays load");expect(acknowledgements==1,"Shuttle refill emits one GrantAck");
 issue(0,18);auto accepted=b.model.edges()-1;response=false;
 for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(b.model.edges()-1==accepted+2,"Shuttle warm hit uses actual two-stage request pipeline");expect(b.get("io_resp_bits_data")==pattern(1),"Shuttle warm hit data");expect(b.get("io_s2_hit"),"Shuttle warm hit classified by actual RTL");}expect(!b.get("auto_out_a_valid"),"Shuttle warm hit has no external A request");}
 expect(response,"Shuttle warm read responds");
 std::uint64_t stored=0x55aa11ee22dd33ccULL;
 issue(1,19,stored);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(!b.get("io_resp_bits_has_data"),"Shuttle store response has no load data");}}
 expect(response,"Shuttle store hit completes");
 issue(0,20);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_data")==stored,"Shuttle store modifies subsequent load");}}
 expect(response,"Shuttle modified line remains readable");
 issue(8,22,3);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_data")==stored,"Shuttle AMOADD returns old data");}}expect(response,"Shuttle AMO hit completes");stored+=3;
 issue(6,23);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_data")==stored,"Shuttle LR returns AMO-updated data");}}expect(response,"Shuttle LR hit completes");
 issue(7,24,stored+1);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_data")==0,"Shuttle SC succeeds within source reservation window");}}expect(response,"Shuttle SC completes");++stored;
 issue(7,25,0x44);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_data")==1,"Shuttle consumed reservation causes second SC failure");}}expect(response,"Shuttle failed SC responds");
 issue(0,26);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_resp_valid")){response=true;expect(b.get("io_resp_bits_data")==stored,"failed Shuttle SC leaves data unchanged");}}expect(response,"Shuttle post-atomic load completes");
 b.set("auto_out_b_valid",1);b.set("auto_out_b_bits_param",2);b.set("auto_out_b_bits_size",6);b.set("auto_out_b_bits_source",0);b.set("auto_out_b_bits_address",0x80000000);
 wait=0;do{b.tick();expect(++wait<100,"Shuttle probe request readiness");}while(!b.get("auto_out_b_ready"));b.set("auto_out_b_valid",0);
 unsigned cbeats=0;
 for(unsigned n=0;n<100;++n){b.tick();if(b.get("auto_out_c_valid")){expect(b.get("auto_out_c_bits_opcode")==5,"dirty probe returns ProbeAckData");expect(b.get("auto_out_c_bits_address")==0x80000000,"dirty probe line address");expect(b.get("auto_out_c_bits_data")== (cbeats==1?stored:pattern(cbeats)),"dirty probe physical data beat matches memory/store oracle");++cbeats;}}
 expect(cbeats==8,"dirty probe transfers eight64bit data beats");
 b.set("auto_out_a_ready",0);issue(0,21);wait=0;while(!b.get("auto_out_a_valid")){b.tick();expect(++wait<40,"probe invalidation forces later read miss");}
 expect(b.get("auto_out_a_bits_opcode")==6,"invalidated line must acquire again");
}
static void rocket(unsigned seed){
 Bench b(Component::RocketL1D,seed);b.set("auto_out_a_ready",1);b.set("auto_out_c_ready",1);b.set("auto_out_e_ready",1);
 b.set("io_cpu_req_bits_dprv",3);b.set("io_cpu_req_bits_phys",0);b.reset(600);
 expect(b.get("io_cpu_ordered"),"Rocket cold cache becomes ordered after reset");
 auto issue=[&](unsigned cmd,unsigned tag,std::uint64_t data=0){
  b.set("io_cpu_req_bits_addr",0x80000008);b.set("io_cpu_req_bits_tag",tag);b.set("io_cpu_req_bits_cmd",cmd);b.set("io_cpu_req_bits_size",3);
  b.set("io_cpu_req_bits_mask",0xffffffff);b.set("io_cpu_s1_data_mask",0xffffffff);Bits store;store.limbs.fill(data);b.setwide("io_cpu_s1_data_data",store);b.set("io_cpu_req_valid",1);
  unsigned wait=0;do{b.tick();expect(++wait<100,"Rocket CPU request readiness bounded");}while(!b.get("io_cpu_req_ready"));b.set("io_cpu_req_valid",0);
 };
 b.set("auto_out_a_ready",0);issue(0,17);unsigned wait=0;
 while(!b.get("auto_out_a_valid")){b.tick();expect(++wait<60,"Rocket cold load emits AcquireBlock");}
 expect(b.get("auto_out_a_bits_opcode")==6,"Rocket cold load is AcquireBlock");expect(b.get("auto_out_a_bits_size")==6,"Rocket refill requests64B");
 expect(b.get("auto_out_a_bits_address")==0x80000000,"Rocket refill line address");auto source=b.get("auto_out_a_bits_source");
 expect(b.get("io_cpu_s2_nack"),"Rocket blocked cached miss nacks CPU instead of holding the CPU request");
 for(unsigned n=0;n<9;++n){b.tick();expect(!b.get("io_cpu_resp_valid"),"Rocket no premature data response");}
 b.set("auto_out_a_ready",1);issue(0,17);wait=0;while(!b.get("auto_out_a_valid")){b.tick();expect(++wait<60,"Rocket retried cold miss acquires when ready");}
 for(unsigned n=0;n<30;++n){b.tick();expect(!b.get("io_cpu_resp_valid"),"Rocket unknown service never fabricates completion");}
 b.set("auto_out_d_valid",1);b.set("auto_out_d_bits_opcode",5);b.set("auto_out_d_bits_param",0);b.set("auto_out_d_bits_size",6);b.set("auto_out_d_bits_source",source);b.set("auto_out_d_bits_sink",0);
 unsigned acknowledgements=0;bool response=false;unsigned nacks=0;
 for(unsigned beat=0;beat<2;++beat){Bits data;for(unsigned limb=0;limb<4;++limb)data.limbs[limb]=pattern(4*beat+limb);b.setwide("auto_out_d_bits_data",data);
  unsigned retry=0;do{b.tick();if(b.get("auto_out_e_valid"))++acknowledgements;expect(++retry<60,"Rocket D backpressure bounded");}while(!b.get("auto_out_d_ready"));}
 b.set("auto_out_d_valid",0);for(unsigned n=0;n<30;++n){b.tick();if(b.get("auto_out_e_valid"))++acknowledgements;}
 expect(acknowledgements==1,"Rocket64B refill emits one GrantAck after two256bit beats");
 // Rocket's blocking cache nacks a miss; the CPU must retry it after refill.
 issue(0,18);auto accepted=b.model.edges()-1;
 for(unsigned n=0;n<15;++n){b.tick();nacks+=b.get("io_cpu_s2_nack");if(b.get("io_cpu_resp_valid")){response=true;
  expect(b.model.edges()-1==accepted+2,"Rocket warm load follows source S1/S2 pipeline");expect(b.get("io_cpu_resp_bits_tag")==18,"Rocket warm hit tag");
  expect(b.get("io_cpu_resp_bits_data")==pattern(1),"Rocket shifted scalar data matches independent256bit beat oracle");}
  expect(!b.get("auto_out_a_valid"),"Rocket warm load emits no external request");}
 expect(response&&!nacks,"Rocket filled warm load responds without nack");
 std::uint64_t stored=0x55aa11ee22dd33ccULL;issue(1,19,stored);for(unsigned n=0;n<12;++n)b.tick();
 issue(0,20);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_cpu_resp_valid")){response=true;expect(b.get("io_cpu_resp_bits_data")==stored,"Rocket cached store changes scalar reload");}}
 expect(response,"Rocket cached reload completes");
 issue(8,22,3);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_cpu_resp_valid")){response=true;expect(b.get("io_cpu_resp_bits_data")==stored,"Rocket AMOADD returns old data");}}expect(response,"Rocket AMO hit completes");stored+=3;
 issue(6,23);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_cpu_resp_valid")){response=true;expect(b.get("io_cpu_resp_bits_data")==stored,"Rocket LR returns AMO-updated data");}}expect(response,"Rocket LR hit completes");
 issue(7,24,stored+1);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_cpu_resp_valid")){response=true;expect(b.get("io_cpu_resp_bits_data")==0,"Rocket SC succeeds within source reservation window");}}expect(response,"Rocket SC completes");++stored;
 issue(7,25,0x44);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_cpu_resp_valid")){response=true;expect(b.get("io_cpu_resp_bits_data")==1,"Rocket consumed reservation causes second SC failure");}}expect(response,"Rocket failed SC responds");
 issue(0,26);response=false;for(unsigned n=0;n<12;++n){b.tick();if(b.get("io_cpu_resp_valid")){response=true;expect(b.get("io_cpu_resp_bits_data")==stored,"failed Rocket SC leaves data unchanged");}}expect(response,"Rocket post-atomic load completes");
 b.set("auto_out_b_valid",1);b.set("auto_out_b_bits_param",2);b.set("auto_out_b_bits_size",6);b.set("auto_out_b_bits_source",0);b.set("auto_out_b_bits_address",0x80000000);
 wait=0;do{b.tick();expect(++wait<100,"Rocket probe readiness");}while(!b.get("auto_out_b_ready"));b.set("auto_out_b_valid",0);
 unsigned cbeats=0;for(unsigned n=0;n<100;++n){b.tick();if(b.get("auto_out_c_valid")){
  expect(b.get("auto_out_c_bits_opcode")==5,"Rocket dirty probe emits ProbeAckData");Bits actual=b.wide("auto_out_c_bits_data");
  for(unsigned limb=0;limb<4;++limb){unsigned word=4*cbeats+limb;expect(actual.limbs[limb]==(word==1?stored:pattern(word)),"Rocket dirty probe256bit payload oracle");}++cbeats;}}
 expect(cbeats==2,"Rocket dirty probe uses two physical256bit beats");
}
static void inclusive(unsigned seed){
 Bench b(Component::InclusiveL2,seed);
 for(unsigned bank=0;bank<4;++bank){auto outer="auto_out_"+std::to_string(bank),inner="auto_in_"+std::to_string(bank);
  b.set(outer+"_a_ready",0);b.set(outer+"_c_ready",1);b.set(outer+"_e_ready",1);b.set(inner+"_b_ready",1);b.set(inner+"_d_ready",1);}
 b.reset(600);
 for(unsigned bank=0;bank<4;++bank){auto inner="auto_in_"+std::to_string(bank);
  b.set(inner+"_a_valid",1);b.set(inner+"_a_bits_opcode",4);b.set(inner+"_a_bits_size",3);b.set(inner+"_a_bits_source",0);
  b.set(inner+"_a_bits_address",0x80000008+64*bank);b.set(inner+"_a_bits_mask",0xff);}
 unsigned accepted=0;unsigned waits=0;
 while(accepted!=15){b.tick();for(unsigned bank=0;bank<4;++bank){auto inner="auto_in_"+std::to_string(bank);
  if(b.get(inner+"_a_ready")&&!(accepted&(1<<bank))){accepted|=1<<bank;b.set(inner+"_a_valid",0);}}expect(++waits<100,"L2 all four bank requests accepted");}
 unsigned outer_valid=0;
 for(unsigned n=0;n<80;++n){b.tick();for(unsigned bank=0;bank<4;++bank){auto outer="auto_out_"+std::to_string(bank),inner="auto_in_"+std::to_string(bank);
  if(b.get(outer+"_a_valid")){outer_valid|=1<<bank;expect(b.get(outer+"_a_bits_opcode")==6,"L2 outer requests AcquireBlock before the external cork");expect(b.get(outer+"_a_bits_size")==6,"L2 miss refills64B");expect(b.get(outer+"_a_bits_address")==0x80000000+64*bank,"L2 bank retains physical address bits");}
  expect(!b.get(inner+"_d_valid"),"L2 cannot complete cold read without outer service");}}
 expect(outer_valid==15,"all four source L2 banks progress independently to outer request");
 std::array<std::uint64_t,4> sources{};
 for(unsigned bank=0;bank<4;++bank){auto outer="auto_out_"+std::to_string(bank);sources[bank]=b.get(outer+"_a_bits_source");b.set(outer+"_a_ready",1);}b.tick();
 for(unsigned n=0;n<20;++n){b.tick();for(unsigned bank=0;bank<4;++bank)expect(!b.get("auto_in_"+std::to_string(bank)+"_d_valid"),"L2 miss remains open without invented DRAM delay");}
 std::array<unsigned,4> beat{};std::array<unsigned,4> acknowledgements{};std::array<bool,4> responses{};
 auto collect=[&](){for(unsigned bank=0;bank<4;++bank){auto outer="auto_out_"+std::to_string(bank),inner="auto_in_"+std::to_string(bank);
  if(b.get(outer+"_e_valid"))++acknowledgements[bank];
  if(b.get(inner+"_d_valid")){responses[bank]=true;expect(b.get(inner+"_d_bits_opcode")==1,"L2 inner Get returns AccessAckData");expect(b.get(inner+"_d_bits_source")==0,"L2 preserves inner source ID");expect(b.get(inner+"_d_bits_data")==pattern(16*bank+1),"L2 critical-word response matches independent bank data oracle");}}};
 for(unsigned n=0;n<200&&*std::min_element(beat.begin(),beat.end())<8;++n){
  for(unsigned bank=0;bank<4;++bank){auto outer="auto_out_"+std::to_string(bank);b.set(outer+"_d_valid",beat[bank]<8);b.set(outer+"_d_bits_opcode",5);b.set(outer+"_d_bits_param",0);b.set(outer+"_d_bits_size",6);b.set(outer+"_d_bits_source",sources[bank]);b.set(outer+"_d_bits_sink",0);b.set(outer+"_d_bits_data",pattern(16*bank+beat[bank]));}
  b.tick();collect();for(unsigned bank=0;bank<4;++bank)if(beat[bank]<8&&b.get("auto_out_"+std::to_string(bank)+"_d_ready"))++beat[bank];
 }
 for(unsigned bank=0;bank<4;++bank){expect(beat[bank]==8,"L2 receives eight beats per bank");b.set("auto_out_"+std::to_string(bank)+"_d_valid",0);}
 for(unsigned n=0;n<80;++n){b.tick();collect();}
 for(unsigned bank=0;bank<4;++bank){expect(responses[bank],"L2 each bank returns requested word");expect(acknowledgements[bank]==1,"L2 each bank sends one outer GrantAck");}
 responses.fill(false);accepted=0;
 for(unsigned bank=0;bank<4;++bank)b.set("auto_in_"+std::to_string(bank)+"_a_valid",1);
 for(unsigned n=0;n<80;++n){b.tick();for(unsigned bank=0;bank<4;++bank){auto inner="auto_in_"+std::to_string(bank);
  if(b.get(inner+"_a_ready")&&!(accepted&(1<<bank))){accepted|=1<<bank;b.set(inner+"_a_valid",0);}expect(!b.get("auto_out_"+std::to_string(bank)+"_a_valid"),"warm L2 bank hit has no outer refill");}collect();}
 expect(accepted==15,"warm requests accepted on four banks");for(bool response:responses)expect(response,"warm L2 load matches filled data");
}
static void uncached_and_pma(unsigned seed){
 for(auto kind:{Component::ShuttleL1D,Component::RocketL1D}){
  bool shuttle=kind==Component::ShuttleL1D;Bench b(kind,seed);b.set("auto_out_a_ready",1);b.set("auto_out_c_ready",1);b.set("auto_out_e_ready",1);
  std::string req=shuttle?"io_req":"io_cpu_req",resp=shuttle?"io_resp":"io_cpu_resp";
  if(!shuttle)b.set("io_cpu_req_bits_dprv",3);b.reset(600);
  for(unsigned repeat=0;repeat<2;++repeat){
   b.set(req+"_bits_addr",0x70000000);b.set(req+"_bits_cmd",0);b.set(req+"_bits_size",3);b.set(req+"_bits_tag",5+repeat);b.set(req+"_valid",1);
   if(shuttle)b.set("io_s1_paddr",0x70000000);
   unsigned wait=0;do{b.tick();expect(++wait<100,"uncached CPU request readiness");}while(!b.get(req+"_ready"));b.set(req+"_valid",0);
   wait=0;while(!b.get("auto_out_a_valid")){b.tick();expect(++wait<100,"TCM load produces external Get");}
   expect(b.get("auto_out_a_bits_opcode")==4,"TCM uncached path uses Get not AcquireBlock");expect(b.get("auto_out_a_bits_size")==3,"uncached8B load is not expanded to64B refill");
   expect(b.get("auto_out_a_bits_address")==0x70000000,"uncached TCM address preserved");auto source=b.get("auto_out_a_bits_source");
   for(unsigned n=0;n<15;++n){b.tick();expect(!b.get(resp+"_valid"),"uncached load has no invented service");}
   b.set("auto_out_d_valid",1);b.set("auto_out_d_bits_opcode",1);b.set("auto_out_d_bits_size",3);b.set("auto_out_d_bits_source",source);b.set("auto_out_d_bits_data",pattern(55+repeat));
   wait=0;bool response=false;do{b.tick();if(b.get(resp+"_valid")){response=true;expect(b.get(resp+"_bits_data")==pattern(55+repeat),"uncached returned payload matches service oracle");}expect(++wait<100,"uncached D acceptance");}while(!b.get("auto_out_d_ready"));
   b.set("auto_out_d_valid",0);for(unsigned n=0;n<40;++n){b.tick();if(b.get(resp+"_valid")){response=true;expect(b.get(resp+"_bits_data")==pattern(55+repeat),"uncached load response data");}expect(!b.get("auto_out_e_valid"),"uncached AccessAckData never emits GrantAck");}
   expect(response,"uncached request returns to CPU");
  }
 }
 // A physical Hella request is the PTW/Saturn passthrough path, checked as S
 // privilege in TLB.scala415. It does not mean bypass PMP for a normal M CPU.
 for(unsigned test=0;test<4;++test){
  Bench b(Component::RocketL1D,seed);b.set("auto_out_a_ready",1);b.set("auto_out_c_ready",1);b.set("auto_out_e_ready",1);b.set("io_cpu_req_bits_dprv",3);b.reset(600);
  b.set("io_cpu_req_bits_addr",test==0?0x80000000:test==1?0x60000000:test==2?0x70000000:0x580000000ULL);
  b.set("io_cpu_req_bits_phys",test==0);b.set("io_cpu_req_bits_cmd",test<2?0:test==2?6:8);b.set("io_cpu_req_bits_size",3);b.set("io_cpu_req_valid",1);
  unsigned wait=0;do{b.tick();expect(++wait<100,"PMA negative request readiness");}while(!b.get("io_cpu_req_ready"));b.set("io_cpu_req_valid",0);
  bool fault=false;for(unsigned n=0;n<40;++n){b.tick();fault|=b.get(test==3?"io_cpu_s2_xcpt_ae_st":"io_cpu_s2_xcpt_ae_ld");expect(!b.get("auto_out_a_valid"),"PMP/PMA rejected request must not reach TL A");expect(!b.get("io_cpu_resp_valid"),"faulting request does not return fabricated data");}
  expect(fault,test==0?"physical passthrough still enforces supervisor PMP":test==1?"unmapped address raises access fault":test==2?"uncached TCM rejects LR":"scratchpad rejects AMO");
 }
}
static void coherence(unsigned seed){
 Bench b(Component::InclusiveL2,seed);for(unsigned bank=0;bank<4;++bank){auto outer="auto_out_"+std::to_string(bank),inner="auto_in_"+std::to_string(bank);b.set(outer+"_a_ready",1);b.set(outer+"_c_ready",1);b.set(outer+"_e_ready",1);b.set(inner+"_b_ready",1);b.set(inner+"_d_ready",1);}b.reset(600);
 auto acquire=[&](unsigned source){b.set("auto_in_0_a_valid",1);b.set("auto_in_0_a_bits_opcode",6);b.set("auto_in_0_a_bits_param",1);b.set("auto_in_0_a_bits_size",6);b.set("auto_in_0_a_bits_source",source);b.set("auto_in_0_a_bits_address",0x80000000);b.set("auto_in_0_a_bits_mask",0xff);unsigned wait=0;do{b.tick();expect(++wait<100,"coherent acquire readiness");}while(!b.get("auto_in_0_a_ready"));b.set("auto_in_0_a_valid",0);};
 unsigned beats=0,sink=0,current_source=0x2e0,base=0;
 auto collect=[&](){if(b.get("auto_in_0_d_valid")){expect(b.get("auto_in_0_d_bits_opcode")==5,"coherent acquire returns GrantData");expect(b.get("auto_in_0_d_bits_source")==current_source,"coherent Grant retains requester source");expect(b.get("auto_in_0_d_bits_param")==0,"write acquire receives trunk permission");expect(b.get("auto_in_0_d_bits_data")==pattern(base+beats),"coherent grant follows independent line payload oracle");expect(beats<8,"coherent grant is not duplicated");sink=b.get("auto_in_0_d_bits_sink");++beats;}};
 auto ack=[&](){expect(beats==8,"coherent acquire transfers all eight data beats");b.set("auto_in_0_e_valid",1);b.set("auto_in_0_e_bits_sink",sink);unsigned wait=0;do{b.tick();expect(++wait<100,"inner GrantAck readiness");}while(!b.get("auto_in_0_e_ready"));b.set("auto_in_0_e_valid",0);for(unsigned n=0;n<8;++n)b.tick();};
 acquire(current_source);unsigned wait=0;while(!b.get("auto_out_0_a_valid")){b.tick();expect(++wait<100,"cold coherent acquire requests outer line");}auto outer_source=b.get("auto_out_0_a_bits_source");
 b.set("auto_out_0_d_valid",1);b.set("auto_out_0_d_bits_opcode",5);b.set("auto_out_0_d_bits_param",0);b.set("auto_out_0_d_bits_size",6);b.set("auto_out_0_d_bits_source",outer_source);b.set("auto_out_0_d_bits_sink",0);
 for(unsigned beat=0;beat<8;++beat){b.set("auto_out_0_d_bits_data",pattern(beat));wait=0;do{b.tick();collect();expect(++wait<100,"coherent outer D readiness");}while(!b.get("auto_out_0_d_ready"));}
 b.set("auto_out_0_d_valid",0);for(unsigned n=0;n<100&&beats<8;++n){b.tick();collect();}ack();
 // Source ranges are compiled in MSHR.sv::req_clientBit and SourceB.sv:
 // 0x2e0..2e3 and0x2a0..2a3 are distinct coherent clients. The directory
 // must probe the first owner before granting the second write owner.
 current_source=0x2a0;base=100;beats=0;acquire(current_source);wait=0;
 while(!b.get("auto_in_0_b_valid")){b.tick();expect(++wait<100,"conflicting write acquire emits a coherence probe");expect(!b.get("auto_in_0_d_valid"),"new owner cannot receive data before old owner replies");}
 expect(b.get("auto_in_0_b_bits_opcode")==6,"coherence B is Probe");expect(b.get("auto_in_0_b_bits_source")==0x2e0,"probe targets exact previous client's configured source");expect(b.get("auto_in_0_b_bits_param")==2,"write ownership conflict probes old owner toN");expect(b.get("auto_in_0_b_bits_address")==0x80000000,"probe address matches coherent cache line");
 for(unsigned n=0;n<25;++n){b.tick();expect(!b.get("auto_in_0_d_valid"),"L2 waits for probe acknowledgement rather than guessing delay");expect(!b.get("auto_out_0_a_valid"),"coherent warm line does not refetch from DRAM");}
 b.set("auto_in_0_c_valid",1);b.set("auto_in_0_c_bits_opcode",5);b.set("auto_in_0_c_bits_param",1);b.set("auto_in_0_c_bits_size",6);b.set("auto_in_0_c_bits_source",0x2e0);b.set("auto_in_0_c_bits_address",0x80000000);
 for(unsigned beat=0;beat<8;++beat){b.set("auto_in_0_c_bits_data",pattern(base+beat));wait=0;do{b.tick();collect();expect(++wait<100,"coherent ProbeAckData C readiness");}while(!b.get("auto_in_0_c_ready"));}
 b.set("auto_in_0_c_valid",0);for(unsigned n=0;n<100&&beats<8;++n){b.tick();collect();}ack();
}
static void strict_control_policy(){
 for(unsigned seed:{0,1,7,31,113}){
  Bench b(Component::ShuttleL1D,seed,UnresetReplayPolicy::RefuseUse);b.set("auto_out_c_ready",1);b.set("auto_out_e_ready",1);b.reset(160);
  b.set("io_req_bits_addr",0x80000000);b.set("io_s1_paddr",0x80000000);b.set("io_req_bits_cmd",1);b.set("io_req_bits_size",3);b.set("io_req_valid",1);
  auto edge=b.model.edges();bool refused=false;try{b.tick();}catch(const std::runtime_error&e){refused=std::string(e.what()).find("IRIS_SHUTTLE_INVALID_REPLAY_COMMAND_UNDEFINED queue=3 slot=0")!=std::string::npos;}
  expect(refused,"default cache timing refuses unwritten invalid replay-head command");expect(b.model.edges()==edge,"undefined-control refusal does not advance a cache edge");expect(!b.model.concretized_unknown_replay_timing(),"refused unknown control never becomes a concrete timing result");
  bool stale=false;try{b.model.sample();}catch(const std::logic_error&){stale=true;}expect(stale,"undefined-control refusal invalidates output sampling");
  stale=false;try{b.model.commit();}catch(const std::logic_error&){stale=true;}expect(stale,"undefined-control refusal cannot be committed");
  b.set("io_req_valid",0);
  for(unsigned line=0;line<4;++line){
   b.set("io_req_bits_addr",0x80000000+64*line);b.set("io_s1_paddr",0x80000000+64*line);b.set("io_req_bits_cmd",0);b.set("io_req_bits_tag",line);b.set("io_req_valid",1);
   unsigned wait=0;do{b.tick();expect(++wait<100,"strict read-only queue initializer accepted");}while(!b.get("io_req_ready"));b.set("io_req_valid",0);for(unsigned n=0;n<8;++n)b.tick();
  }
  // These are real queued misses, not host state injection. Queue3 slot0 has
  // now received a defined load command even though its replay.valid isfalse.
  b.set("io_req_bits_addr",0x80000000);b.set("io_s1_paddr",0x80000000);b.set("io_req_bits_cmd",1);b.set("io_req_bits_tag",12);b.set("io_req_valid",1);b.tick();b.set("io_req_valid",0);
  expect(!b.model.concretized_unknown_replay_timing(),"accepted queue write permits the now-defined invalid head without concretization");
  b.set("auto_out_a_ready",1);unsigned accepted=0;
  for(unsigned n=0;n<60&&accepted!=15;++n){b.tick();if(b.get("auto_out_a_valid"))accepted|=1<<b.get("auto_out_a_bits_source");}
  expect(accepted==15,"all four actual acquire sources accepted before source3 refill");
  b.set("auto_out_d_valid",1);b.set("auto_out_d_bits_opcode",5);b.set("auto_out_d_bits_param",0);b.set("auto_out_d_bits_size",6);b.set("auto_out_d_bits_source",3);b.set("auto_out_d_bits_sink",0);
  for(unsigned beat=0;beat<8;++beat){b.set("auto_out_d_bits_data",pattern(beat));unsigned wait=0;do{b.tick();expect(++wait<100,"strict source3 grant accepted");}while(!b.get("auto_out_d_ready"));}
  b.set("auto_out_d_valid",0);bool ack=false;for(unsigned n=0;n<100;++n){b.tick();ack|=b.get("auto_out_e_valid");}expect(ack,"source3 refill and replay genuinely drain before next-head refusal");
  b.set("io_req_valid",1);edge=b.model.edges();refused=false;try{b.tick();}catch(const std::runtime_error&e){refused=std::string(e.what()).find("queue=3 slot=1")!=std::string::npos;}
  expect(refused,"head advancing to an unwritten slot restores undefined-control refusal");expect(b.model.edges()==edge,"next-slot refusal does not consume a clock edge");
 }
}
static void interface_guards(){
 for(auto kind:{Component::ShuttleL1D,Component::RocketL1D,Component::InclusiveL2}){
  Bench b(kind,1);bool refused=false;
  try{b.model.sample();}catch(const std::logic_error&){refused=true;}expect(refused,"sample before evaluation refused");
  refused=false;try{b.model.commit();}catch(const std::logic_error&){refused=true;}expect(refused,"commit before evaluation refused");
  refused=false;try{b.eval();}catch(const std::logic_error&){refused=true;}expect(refused,"active operation before explicit reset refused");
  b.set("reset",1);b.eval();auto a=b.out;b.eval();expect(a==b.out,"same-edge evaluation is idempotent");expect(b.model.edges()==0,"evaluate never advances cache clock");b.model.commit();expect(b.model.edges()==1,"commit advances one cache edge");
  refused=false;try{b.model.commit();}catch(const std::logic_error&){refused=true;}expect(refused,"stale repeated commit refused");
  b.set("reset",2);refused=false;try{b.eval();}catch(const std::invalid_argument&){refused=true;}expect(refused,"one-bit input width overflow refused");
  b.set("reset",1);b.in[0].limbs[3]=1;refused=false;try{b.eval();}catch(const std::invalid_argument&){refused=true;}expect(refused,"unused wide input limbs refused");
  refused=false;try{b.model.sample();}catch(const std::logic_error&){refused=true;}expect(refused,"failed input evaluation invalidates pending sample");
 }
}
int main(){try{interface_guards();strict_control_policy();for(unsigned seed:{1,7,31,113}){shuttle(seed);rocket(seed);inclusive(seed);uncached_and_pma(seed);coherence(seed);}std::cout<<"{\"status\":\"passed_cache_component_semantics\",\"checks\":"<<checks<<",\"reset_seeds\":4,\"concrete_reset_exploration_explicit\":true,\"default_unknown_control_refusal_tested\":true,\"source_identity\":\""<<Model::source_identity()<<"\",\"hardware_contacted\":false,\"timing_certified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<"CACHE_CHECK_FAILED after "<<checks<<": "<<e.what()<<'\n';return 1;}}
