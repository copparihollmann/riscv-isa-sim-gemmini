#include "serial_memory_system.hpp"
#include "fased_service.hpp"
#include "verilated.h"
#include <deque>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
namespace P=iris::memory_system;
namespace L=iris::fased;
namespace S=iris::serial_memory;
namespace {
std::uint64_t checks=0;
bool bad_data=false;
void need(bool ok,const std::string&why){++checks;if(!ok)throw std::runtime_error(why);}
P::Bits known(unsigned width){P::Bits bits;for(unsigned b=0;b<width;++b)bits.limbs[b/64]|=std::uint64_t(1)<<(b%64);return bits;}
std::uint64_t pattern(std::uint64_t address){return 0x93ac4e1000000000ULL^address;}
void lifecycle(){
  VerilatedContext foreign;Verilated::threadContextp(&foreign);
  auto model=std::make_unique<P::System>(99,std::vector<std::string>{"system-lifecycle"},S::AssertionPolicy::SuppressOnlyWhileBothExternalResets);
  need(Verilated::threadContextp()==&foreign,"System constructor leaked caller context");
  auto reject=[&](auto f,const char*why){bool caught=false;try{f();}catch(const std::exception&){caught=true;}need(caught,why);need(Verilated::threadContextp()==&foreign,"System lifecycle error leaked caller context");};
  reject([&]{model->sample();},"sample before evaluation admitted");reject([&]{model->commit({true,true,true,true});},"commit before evaluation admitted");
  std::vector<P::Input>in(model->input_fields().size());for(unsigned i=0;i<in.size();++i){auto f=model->input_fields()[i];in[i].known=known(f.width);if(f.name.ends_with("_reset")||f.name.ends_with("/reset")||f.name=="path/iris_pad_reset_io")in[i].value=P::Bits(1);}
  for(unsigned i=0;i<in.size();++i){auto bad=in;bad[i].known.limbs[0]&=~std::uint64_t(1);reject([&]{model->evaluate(bad);},"unknown remaining external field admitted");}
  need(model->committed_phases()==0,"unknown input advanced constructor-only model");model.reset();need(Verilated::threadContextp()==&foreign,"System destructor leaked caller context");
}
struct Read {std::uint64_t address;unsigned id,len,size;};
struct Fixture {
  VerilatedContext foreign;
  P::System system;
  L::Model latency;
  std::vector<P::Input>in;
  std::vector<P::Bits>out;
  std::vector<L::Bits>lin;
  std::vector<std::uint64_t>lout;
  std::map<std::string,unsigned>li,lo;
  std::deque<Read>owners;
  std::optional<Read>active;
  unsigned beat=0;
  std::uint64_t tick=0,ar=0,r=0,core_edges=0,a=0,d=0,e=0,b=0,c=0;
  bool reset=true;
  explicit Fixture(unsigned seed):system(seed,{"source-system-check","+tilelink_timeout=0"},S::AssertionPolicy::SuppressOnlyWhileBothExternalResets),latency({30,30,16,16},seed+113,{"source-system-check"}),in(system.input_fields().size()){
    auto fields=system.input_fields();for(unsigned i=0;i<in.size();++i)in[i].known=known(fields[i].width);
    for(auto f:latency.input_fields()){li[f.name]=lin.size();lin.push_back({0,f.width==64?~std::uint64_t(0):(std::uint64_t(1)<<f.width)-1});}for(auto f:latency.output_fields())lo[f.name]=lo.size();
  }
  void set(std::string_view component,std::string_view field,std::uint64_t value){in[system.external_input_index(component,field)].value=P::Bits(value);}
  std::uint64_t get(std::string_view component,std::string_view field)const{return out[system.output_index(component,field)].limbs[0];}
  void ls(const std::string&field,std::uint64_t value){lin[li.at("tNasti_io_"+field)].value=value;}
  std::uint64_t lg(const std::string&field)const{return lout[lo.at("tNasti_io_"+field)];}
  std::uint64_t axi(const std::string&field)const{return get("path","fased_axi4_mem_0_bits_"+field);}
  void evaluate(){
    auto fields=system.input_fields();for(unsigned i=0;i<in.size();++i)if(fields[i].name.ends_with("_reset")||fields[i].name.ends_with("/reset")||fields[i].name=="path/iris_pad_reset_io")in[i].value=P::Bits(reset);
    lin[li.at("reset")].value=reset;
    ls("egressResp_rBits_data",active?(pattern(active->address+(std::uint64_t(beat)<<active->size))^(bad_data?1:0)):0);ls("egressResp_rBits_last",active&&beat==active->len);ls("egressResp_rBits_id",active?active->id:0);
    for(unsigned iteration=0;iteration<32;++iteration){
      Verilated::threadContextp(&foreign);latency.evaluate(lin);need(Verilated::threadContextp()==&foreign,"LP context restoration");lout=latency.sample();
      for(auto pair:std::initializer_list<std::pair<const char*,const char*>>{{"aw_ready","tNasti_aw_ready"},{"w_ready","tNasti_w_ready"},{"ar_ready","tNasti_ar_ready"},{"b_valid","tNasti_b_valid"},{"b_bits_id","tNasti_b_bits_id"},{"r_valid","tNasti_r_valid"},{"r_bits_id","tNasti_r_bits_id"},{"r_bits_last","tNasti_r_bits_last"},{"r_bits_data","tNasti_r_bits_data"}})set("path","fased_axi4_mem_0_bits_"+std::string(pair.first),lg(pair.second));
      auto previous=out;system.evaluate(in);need(Verilated::threadContextp()==&foreign,"System context restoration");out=system.sample();bool changed=false;
      for(auto pair:std::initializer_list<std::pair<const char*,const char*>>{{"ar_valid","tNasti_ar_valid"},{"ar_bits_id","tNasti_ar_bits_id"},{"ar_bits_len","tNasti_ar_bits_len"},{"ar_bits_burst","tNasti_ar_bits_burst"},{"r_ready","tNasti_r_ready"},{"b_ready","tNasti_b_ready"}}){auto value=reset?0:axi(pair.first);auto index=li.at("tNasti_io_"+std::string(pair.second));changed|=lin[index].value!=value;lin[index].value=value;}
      if(!changed&&previous==out)return;
    }
    throw std::runtime_error("System/LP external fixed point failed");
  }
  void step(){
    evaluate();bool edge=tick%2==0;
    if(!reset){
      need(!axi("aw_valid")&&!axi("w_valid"),"read-only test actor cannot supply an unexpected outer write");
      if(axi("ar_valid")&&lg("tNasti_ar_ready")){Read q{axi("ar_bits_addr"),unsigned(axi("ar_bits_id")),unsigned(axi("ar_bits_len")),unsigned(axi("ar_bits_size"))};need(q.len==7&&q.size==3,"source read shape changed");owners.push_back(q);++ar;}
      need(bool(active)==bool(lg("tNasti_r_valid")),"source response has no functional owner");
      if(active&&axi("r_ready")){++r;if(beat==active->len){active.reset();beat=0;}else++beat;}
      if(lg("egressReq_r_valid")){need(!owners.empty()&&owners.front().id==lg("egressReq_r_bits"),"source read request/response ID changed");active=owners.front();owners.pop_front();beat=0;}
      if(edge){a+=get("rocket_cache","auto_out_a_valid")&&get("rocket_tile","_widget_auto_anon_in_a_ready");d+=get("rocket_tile","_widget_auto_anon_in_d_valid")&&get("rocket_cache","auto_out_d_ready");e+=get("rocket_cache","auto_out_e_valid")&&get("rocket_tile","_widget_auto_anon_in_e_ready");b+=get("rocket_tile","_widget_auto_anon_in_b_valid")&&get("rocket_cache","auto_out_b_ready");c+=get("rocket_cache","auto_out_c_valid")&&get("rocket_tile","_widget_auto_anon_in_c_ready");}
    }
    system.commit({edge,edge,true,tick%10==0});latency.commit();if(edge)++core_edges;++tick;
  }
  void iris_step(){auto goal=core_edges+1;do{step();}while(core_edges!=goal);}
  void startup(){set("rocket_cache","io_cpu_req_bits_dprv",3);for(unsigned i=0;i<100;++i)step();reset=false;for(unsigned i=0;i<600;++i)iris_step();need(get("rocket_cache","io_cpu_ordered"),"source cache sweep did not complete");}
  void issue(unsigned cmd,unsigned tag,std::uint64_t address,std::uint64_t data=0){
    set("rocket_cache","io_cpu_req_bits_addr",address);set("rocket_cache","io_cpu_req_bits_tag",tag);set("rocket_cache","io_cpu_req_bits_cmd",cmd);set("rocket_cache","io_cpu_req_bits_size",3);set("rocket_cache","io_cpu_req_bits_mask",0xffffffff);set("rocket_cache","io_cpu_s1_data_mask",0xffffffff);P::Bits wide;wide.limbs.fill(data);in[system.external_input_index("rocket_cache","io_cpu_s1_data_data")].value=wide;set("rocket_cache","io_cpu_req_valid",1);
    unsigned wait=0;do{iris_step();need(++wait<100,"source Hella request not accepted");}while(!get("rocket_cache","io_cpu_req_ready"));set("rocket_cache","io_cpu_req_valid",0);
  }
};
void run(unsigned seed){
  Fixture t(seed);t.startup();auto begin=t.tick;t.issue(0,17,0x80000008);for(unsigned i=0;i<12000;++i){t.iris_step();if(t.r==8&&t.get("rocket_cache","io_cpu_ordered")&&t.e)break;need(i<11999,"cold source path did not refill");}need(t.ar==1&&t.r==8&&t.a==1&&t.d==2&&t.e==1,"source cold refill handshake counts differ");auto refill=t.tick-begin;
  t.issue(0,18,0x80000008);bool response=false;for(unsigned i=0;i<20;++i){t.iris_step();if(t.get("rocket_cache","io_cpu_resp_valid")){need(t.get("rocket_cache","io_cpu_resp_bits_tag")==18&&t.get("rocket_cache","io_cpu_resp_bits_data")==pattern(0x80000008),"warm source data mismatch");response=true;}}need(response&&t.ar==1,"warm source hit changed external ownership");
  constexpr std::uint64_t stored=0x55aa11ee22dd33ccULL;t.issue(1,19,0x80000008,stored);for(unsigned i=0;i<15;++i)t.iris_step();t.issue(0,20,0x80000008);response=false;for(unsigned i=0;i<20;++i){t.iris_step();if(t.get("rocket_cache","io_cpu_resp_valid")){need(t.get("rocket_cache","io_cpu_resp_bits_data")==stored,"cached store value mismatch");response=true;}}need(response,"cached store response missing");
  unsigned beats=0;auto capture=[&](){if(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid")){need(beats<8,"duplicate Icache response");auto expected=beats==1?stored:pattern(0x80000000+8*beats);need(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_bits_data")==expected,"dirty-owner byte/line mismatch");++beats;}};
  t.set("rocket_tile","_frontend_auto_icache_master_out_a_valid",1);t.set("rocket_tile","_frontend_auto_icache_master_out_a_bits_address",0x80000000);unsigned wait=0;do{t.iris_step();capture();need(++wait<100,"Icache source request not accepted");}while(!t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_a_ready"));t.set("rocket_tile","_frontend_auto_icache_master_out_a_valid",0);for(unsigned i=0;i<300;++i){t.iris_step();capture();}
  need(beats==8&&t.b==1&&t.c==2&&t.ar==1,"dirty-owner coherence changed outer service");
  // Two independently wired low-level component compositions at the same
  // source phase independently gave1230; this is an equality test, never a
  // delay supplied to either model or an FPGA-calibrated parameter.
  need(refill==1230,"composed SDK inserted or lost a source clock phase");
  std::cout<<"{\"seed\":"<<seed<<",\"cold_refill_inclusive_virtual_phases\":"<<refill<<",\"AXI_AR\":"<<t.ar<<",\"AXI_R\":"<<t.r<<",\"cache_B\":"<<t.b<<",\"cache_C\":"<<t.c<<",\"Icache_D\":"<<beats<<",\"phases\":"<<t.system.committed_phases()<<"}\n";
  auto reject=[&](auto f,const char*why){bool caught=false;try{f();}catch(const std::exception&){caught=true;}need(caught,why);need(Verilated::threadContextp()==&t.foreign,"failed System phase leaked caller context");};
  reject([&]{t.system.external_input_index("manager","auto_coupler_to_bus_named_mbus_bus_xing_out_0_a_ready");},"joined manager Aready exposed as an input");reject([&]{t.system.external_input_index("path","iris_mbus_auto_bus_xing_in_0_a_valid");},"joined path Avalid exposed as an input");
  auto phases=t.system.committed_phases();auto bad=t.in;bad[t.system.external_input_index("rocket_cache","io_cpu_req_bits_addr")].known.limbs[0]&=~std::uint64_t(1);reject([&]{t.system.evaluate(bad);},"unknown external input admitted");need(t.system.committed_phases()==phases,"unknown input advanced a phase");reject([&]{t.system.commit({true,true,true,true});},"failed evaluate left commit eligible");
  t.evaluate();auto first=t.system.sample();t.system.evaluate(t.in);need(first==t.system.sample(),"repeated sameedge evaluation advanced state");reject([&]{t.system.commit({false,false,false,false});},"empty source phase admitted");reject([&]{t.system.sample();},"empty phase did not invalidate observation");
}
}
int main(int argc,char**argv){try{
  if(argc==2&&std::string(argv[1])=="--schema"){
    P::System model(1,{"source-schema"});std::cout<<"{\"schema\":\"iris.source_memory_physical_ports.v1\",\"source_identity\":\""<<P::System::source_identity()<<"\",\"clock_edges\":[\"rocket\",\"uncore\",\"bringup\",\"serial\"]";
    for(auto group:{std::pair<const char*,std::span<const P::Field>>{"inputs",model.input_fields()},{"outputs",model.output_fields()}}){std::cout<<",\""<<group.first<<"\":[";unsigned index=0;for(auto field:group.second){if(index)std::cout<<',';std::cout<<"{\"index\":"<<index++<<",\"name\":\""<<field.name<<"\",\"width\":"<<field.width<<'}';}std::cout<<']';}
    std::cout<<"}\n";return 0;
  }
  bad_data=argc==2&&std::string(argv[1])=="--wrong-data";lifecycle();for(unsigned seed:{1U,17U})run(seed);std::cout<<"{\"status\":\"passed_public_source_memory_system\",\"checks\":"<<checks<<",\"default_external_service\":false,\"real_CPU_pipeline\":false,\"calibration_usable\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
