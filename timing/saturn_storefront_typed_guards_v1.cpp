#include "saturn_storefront_v1.hpp"
#include "verilated.h"
#include <iostream>
#include <functional>
namespace T=iris::saturn_storefront;
namespace {
unsigned checks=0,refusals=0;
void need(bool value,const char*s){++checks;if(!value)throw std::runtime_error(s);}
void refusal(const char*why,const std::function<void()>&fn){bool ok=false;try{fn();}catch(const std::exception&e){ok=std::string(e.what()).find(why)!=std::string::npos;}need(ok,why);++refusals;}
struct F {
  inline static unsigned next_fixture=0;unsigned fixture=++next_fixture;
  VerilatedContext foreign;std::unique_ptr<T::Model>m;
  std::vector<T::Input>in;std::optional<T::Owner>load,store;std::uint64_t tick=0;
  F(){Verilated::threadContextp(&foreign);m=std::make_unique<T::Model>(0,1,std::vector<std::string>{},T::Calendar{2,0},std::vector<T::Domain>{{0x80010000,0x10000}});need(Verilated::threadContextp()==&foreign,"ctor context");for(auto f:m->input_fields())in.push_back(T::concrete(f.width));need(!m->drained(),"unreset state considered drained");set("reset",1);clock();clock();set("reset",0);}
  ~F(){auto*p=Verilated::threadContextp();m.reset();if(Verilated::threadContextp()!=p)std::terminate();}
  void set(const char*n,std::uint64_t v){auto&x=in[m->input_index(n)];x.value.limbs[0]=v;}
  T::Input&field(const char*n){return in[m->input_index(n)];}
  T::Owner owner(unsigned tag=0,std::uint64_t gen=1)const{return {0,tag,m->reset_epoch(),1,gen,0x80001000,0x02056027};}
  void evaluate(){m->evaluate_control(in,load,store);need(Verilated::threadContextp()==&foreign,"evaluate/error context");}
  T::Outputs clock(){try{evaluate();auto out=m->sample();m->prepare(tick);m->commit();need(Verilated::threadContextp()==&foreign,"commit context");tick+=2;return out;}catch(const std::exception&e){throw std::runtime_error("fixture="+std::to_string(fixture)+" tick="+std::to_string(tick)+" "+e.what());}}
  void request(bool is_load=false,unsigned tag=0,std::uint64_t gen=1){auto meta=owner(tag,gen);if(is_load){meta.raw=0x02056007;load=meta;set("io_vec_load_req_valid",1);set("io_vec_load_req_bits_addr",0x80010000+tag*16);set("io_vec_load_req_bits_tag",tag);}else{store=meta;set("io_vec_store_req_valid",1);set("io_vec_store_req_bits_addr",0x80010000+tag*16);set("io_vec_store_req_bits_tag",tag);set("io_vec_store_req_bits_mask",65535);}set("auto_atl_out_a_ready",1);auto out=clock();need(out.words[m->output_index(is_load?"io_vec_load_req_ready":"io_vec_store_req_ready")].limbs[0],"empty source request did not fire");set(is_load?"io_vec_load_req_valid":"io_vec_store_req_valid",0);if(is_load)load.reset();else store.reset();}
  void A(){for(unsigned n=0;n<8;++n){clock();for(const auto&e:m->last_receipts())if(e.phase==T::Phase::TileA)return;}throw std::runtime_error("no physical A");}
  void D(bool is_load=false,unsigned tag=0){set("auto_atl_out_d_valid",1);set("auto_atl_out_d_bits_source",tag+(is_load?16:0));set("auto_atl_out_d_bits_size",4);set("auto_atl_out_d_bits_opcode",is_load?1:0);}
};
}
int main(){try{
  VerilatedContext foreign;Verilated::threadContextp(&foreign);
  refusal("COMPUTE_HART_ONLY",[&]{T::Model m(2,1,{},T::Calendar{2,0},{{0x80010000,64}});});need(Verilated::threadContextp()==&foreign,"bad ctor hart clobbered context");
  refusal("EXPLICIT_COMPUTE_CALENDAR",[&]{T::Model m(0,1,{},T::Calendar{1,0},{{0x80010000,64}});});
  refusal("DECLARED_DOMAIN_REQUIRED",[&]{T::Model m(0,1,{},T::Calendar{2,0},{});});
  refusal("INVALID_DOMAINS",[&]{T::Model m(0,1,{},T::Calendar{2,0},{{0x80010000,64},{0x80010020,64}});});
  refusal("SOURCE_PLUSARGS_ONLY",[&]{T::Model m(0,1,{"+verilator+seed+1"},T::Calendar{2,0},{{0x80010000,64}});});need(Verilated::threadContextp()==&foreign,"bad ctor clobbered context");
  {F f;refusal("STALE_SAMPLE",[&]{f.m->sample();});refusal("COMMIT_WITHOUT_SETTLED_PREPARE",[&]{f.m->commit();});f.evaluate();refusal("COMMIT_WITHOUT_SETTLED_PREPARE",[&]{f.m->commit();});}
  {F f;f.field("io_vec_store_req_valid").known.limbs[0]=0;refusal("UNKNOWN_REQUIRED_INPUT",[&]{f.evaluate();});need(Verilated::threadContextp()==&f.foreign,"unknown exception leaked context");refusal("STALE_SAMPLE",[&]{f.m->sample();});}
  {F f;f.field("io_vec_store_req_valid").value.limbs[0]=2;refusal("EXCESS_FIELD_WIDTH",[&]{f.evaluate();});}
  {F f;f.evaluate();refusal("STALE_OR_SKIPPED_SOURCE_EDGE",[&]{f.m->prepare(f.tick+2);});refusal("STALE_SAMPLE",[&]{f.m->sample();});}
  for(unsigned mode=0;mode<9;++mode){F f;f.store=f.owner();f.set("io_vec_store_req_valid",1);f.set("io_vec_store_req_bits_addr",0x80010000);f.set("io_vec_store_req_bits_mask",65535);
    const char*error="OWNER_IDENTITY";
    if(mode==0)f.store.reset();if(mode==0)error="REQUEST_WITHOUT_OWNER";
    if(mode==1)f.store->epoch++;
    if(mode==2)f.store->hart=1;
    if(mode==3)f.store->tag=1;
    if(mode==4){f.store->generation=0;}
    if(mode==5){f.set("io_vec_store_req_bits_addr",std::uint64_t(1)<<35);error="PHYSICAL16_ADDRESS";}
    if(mode==6){f.set("io_vec_store_req_bits_addr",0x80030000);error="UNMAPPED_REQUEST";}
    if(mode==7){f.field("io_vec_store_req_bits_addr").known.limbs[0]^=1;error="UNKNOWN_REQUIRED_INPUT";}
    if(mode==8){f.field("io_vec_store_req_bits_data").known.limbs[0]^=1;error="UNKNOWN_STROBED_BYTE";}
    refusal(error,[&]{f.clock();});need(f.m->owned_requests()==0,"refused request acquired owner");}
  {F f;f.request();f.A();f.store=f.owner(0,2);f.set("io_vec_store_req_valid",1);refusal("TAG_ALREADY_OWNED",[&]{f.clock();});}
  {F f;f.request();f.set("reset",1);refusal("RESET_WITH_OWNED_TRANSACTIONS",[&]{f.clock();});}
  {F f;f.D();refusal("D_WITHOUT_OWNER",[&]{f.clock();});}
  for(unsigned mode=0;mode<7;++mode){F f;f.request(mode==6);f.A();f.D(mode==6);const char*error="D_METADATA_OWNER";
    if(mode==0)f.set("auto_atl_out_d_bits_opcode",1);
    if(mode==1)f.set("auto_atl_out_d_bits_size",3);
    if(mode==2)f.set("auto_atl_out_d_bits_param",1);
    if(mode==3){f.set("auto_atl_out_d_bits_denied",1);error="D_FAULT_UNQUALIFIED";}
    if(mode==4){f.set("auto_atl_out_d_bits_corrupt",1);error="D_FAULT_UNQUALIFIED";}
    if(mode==5){f.set("auto_atl_out_d_bits_source",3);error="D_WITHOUT_OWNER";}
    if(mode==6){f.field("auto_atl_out_d_bits_data").known.limbs[0]^=1;error="UNKNOWN_RETURNED_BYTE";}
    refusal(error,[&]{f.clock();});need(f.m->owned_requests()==1,"refused D released owner");}
  {F f;f.request();f.A();f.D();f.clock();refusal("DUPLICATE_OR_EARLY_D",[&]{f.clock();});}
  {F f;f.request();f.A();f.D();f.clock();f.set("auto_atl_out_d_valid",0);f.clock();need(f.m->drained(),"completed source owner did not drain");f.store=f.owner();f.set("io_vec_store_req_valid",1);refusal("STALE_GENERATION",[&]{f.clock();});}
  {F f;for(unsigned n=0;n<16;++n){f.request(false,n);f.clock();}need(f.m->owned_requests()==16&&!f.m->drained(),"full16 source counter wrap released ownership");f.evaluate();need(!f.m->sample().words[f.m->output_index("io_mem_busy")].limbs[0],"source counter not wrapped in directed control");}
  {F f;f.clock();const auto epoch=f.m->reset_epoch();f.set("reset",1);f.clock();f.clock();need(f.m->reset_epoch()==epoch+1,"reset epoch advanced per edge instead of per assertion");}
  std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"typed_refusals\":"<<refusals<<",\"source_busy_wrap_guard\":true,\"lifecycle_context_guards\":true}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
