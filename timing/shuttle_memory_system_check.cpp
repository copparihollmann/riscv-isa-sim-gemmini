#include "shuttle_memory_system.hpp"
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
namespace P=iris::shuttle_system;
namespace Original=iris::memory_system;
namespace L=iris::fased;
namespace S=iris::serial_memory;
namespace {
std::uint64_t checks=0;
bool bad_data=false;
void need(bool ok,const std::string&why){++checks;if(!ok)throw std::runtime_error(why);}
P::Bits known(unsigned width){P::Bits bits;for(unsigned b=0;b<width;++b)bits.limbs[b/64]|=std::uint64_t(1)<<(b%64);return bits;}
std::uint64_t pattern(std::uint64_t address){return 0x93ac4e1000000000ULL^address;}
struct Read {std::uint64_t address;unsigned id,len,size;};
struct Fixture {
  VerilatedContext foreign;
  P::System system;
  Original::System catalog;
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
  std::uint64_t previous_address[2]{};
  std::vector<std::pair<unsigned,std::uint64_t>>responses[2];
  bool record=false;
  std::uint64_t probes[2]{},releases[2]{},rocket_responses=0,last_rocket_value=0,last_rocket_tag=0,rocket_nacks=0;
  explicit Fixture(unsigned seed):system(seed,{"source-system-check","+tilelink_timeout=0"},S::AssertionPolicy::SuppressOnlyWhileBothExternalResets),catalog(seed,{},S::AssertionPolicy::SourceAlways),latency({30,30,16,16},seed+113,{"source-system-check"}),in(system.input_fields().size()){
    auto fields=system.input_fields();for(unsigned i=0;i<in.size();++i)in[i].known=known(fields[i].width);
    for(auto f:latency.input_fields()){li[f.name]=lin.size();lin.push_back({0,f.width==64?~std::uint64_t(0):(std::uint64_t(1)<<f.width)-1});}for(auto f:latency.output_fields())lo[f.name]=lo.size();
  }
  unsigned input_index(std::string_view c,std::string_view f)const{if(c.starts_with("shuttle"))return system.external_input_index(c,f);return system.external_input_index("system",catalog.input_fields()[catalog.external_input_index(c,f)].name);}
  unsigned output_index(std::string_view c,std::string_view f)const{if(c.starts_with("shuttle"))return system.output_index(c,f);return system.output_index("system",catalog.output_fields()[catalog.output_index(c,f)].name);}
  void set(std::string_view component,std::string_view field,std::uint64_t value){in[input_index(component,field)].value=P::Bits(value);}
  std::uint64_t get(std::string_view component,std::string_view field)const{return out[output_index(component,field)].limbs[0];}
  void ls(const std::string&field,std::uint64_t value){lin[li.at("tNasti_io_"+field)].value=value;}
  std::uint64_t lg(const std::string&field)const{return lout[lo.at("tNasti_io_"+field)];}
  std::uint64_t axi(const std::string&field)const{return get("path","fased_axi4_mem_0_bits_"+field);}
  void evaluate(){
    auto fields=system.input_fields();for(unsigned i=0;i<in.size();++i)if(fields[i].name.ends_with("_reset")||fields[i].name.ends_with("/reset")||fields[i].name.ends_with("/iris_pad_reset_io"))in[i].value=P::Bits(reset);
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
    for(unsigned h=0;h<2;++h)set("shuttle"+std::to_string(h)+"_tile","_core_io_dmem_s1_paddr",previous_address[h]);
    evaluate();bool edge=tick%2==0;
    if(edge&&!reset){for(unsigned h=0;h<2;++h){auto tile="shuttle"+std::to_string(h)+"_tile",cache="shuttle"+std::to_string(h)+"_cache";
      if(in[input_index(tile,"_core_io_dmem_req_valid")].value.limbs[0]&&get(tile,"_dcacheArb_io_requestor_1_req_ready"))previous_address[h]=in[input_index(tile,"_core_io_dmem_req_bits_addr")].value.limbs[0];
      probes[h]+=get(tile,"_widget_1_auto_anon_in_b_valid")&&get(cache,"auto_out_b_ready");releases[h]+=get(cache,"auto_out_c_valid")&&get(tile,"_widget_1_auto_anon_in_c_ready");
      if(record&&get(tile,"_dcacheArb_io_requestor_1_resp_valid")&&get(tile,"_dcacheArb_io_requestor_1_resp_bits_has_data"))responses[h].push_back({unsigned(get(tile,"_dcacheArb_io_requestor_1_resp_bits_tag")),get(tile,"_dcacheArb_io_requestor_1_resp_bits_data")});
    }}
    if(!reset){
      if(edge)rocket_nacks+=get("rocket_cache","io_cpu_s2_nack");
      if(edge&&get("rocket_cache","io_cpu_resp_valid")){++rocket_responses;last_rocket_value=get("rocket_cache","io_cpu_resp_bits_data");last_rocket_tag=get("rocket_cache","io_cpu_resp_bits_tag");}
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
    set("rocket_cache","io_cpu_req_bits_addr",address);set("rocket_cache","io_cpu_req_bits_tag",tag);set("rocket_cache","io_cpu_req_bits_cmd",cmd);set("rocket_cache","io_cpu_req_bits_size",3);set("rocket_cache","io_cpu_req_bits_mask",0xffffffff);set("rocket_cache","io_cpu_s1_data_mask",0xffffffff);P::Bits wide;wide.limbs.fill(data);in[input_index("rocket_cache","io_cpu_s1_data_data")].value=wide;set("rocket_cache","io_cpu_req_valid",1);
    unsigned wait=0;do{iris_step();need(++wait<100,"source Hella request not accepted");}while(!get("rocket_cache","io_cpu_req_ready"));set("rocket_cache","io_cpu_req_valid",0);
  }
};
bool cold_store=false;
void run(unsigned seed){
  Fixture t(seed);t.startup();t.record=true;
  if(cold_store){t.set("shuttle1_tile","_core_io_dmem_req_valid",1);t.set("shuttle1_tile","_core_io_dmem_req_bits_cmd",1);t.set("shuttle1_tile","_core_io_dmem_req_bits_size",3);t.set("shuttle1_tile","_core_io_dmem_req_bits_addr",0x80010008);for(unsigned i=0;i<10;++i)t.iris_step();throw std::runtime_error("cold store admitted");}
  unsigned accepted[2]{};
  for(unsigned cycle=0;(accepted[0]<64||accepted[1]<64)&&cycle<2000;++cycle){
    for(unsigned h=0;h<2;++h){auto tile="shuttle"+std::to_string(h)+"_tile";auto a=accepted[h];t.set(tile,"_core_io_dmem_req_valid",a<64);t.set(tile,"_core_io_dmem_req_bits_addr",0x80010000ULL+h*4096+(a/16)*64+(a%8)*8);t.set(tile,"_core_io_dmem_req_bits_tag",a);t.set(tile,"_core_io_dmem_req_bits_cmd",0);t.set(tile,"_core_io_dmem_req_bits_size",3);}
    t.iris_step();for(unsigned h=0;h<2;++h)if(accepted[h]<64&&t.get("shuttle"+std::to_string(h)+"_tile","_dcacheArb_io_requestor_1_req_ready"))++accepted[h];
  }
  for(unsigned h=0;h<2;++h){need(accepted[h]==64,"source Shuttle warmup not accepted");t.set("shuttle"+std::to_string(h)+"_tile","_core_io_dmem_req_valid",0);}
  for(unsigned cycle=0;cycle<20000&&(t.responses[0].size()!=64||t.responses[1].size()!=64);++cycle)t.iris_step();
  for(unsigned h=0;h<2;++h){need(t.responses[h].size()==64,"source Shuttle warmup response count");bool seen[64]{};for(auto[tag,value]:t.responses[h]){need(tag<64&&!seen[tag],"Shuttle warmup response ownership");seen[tag]=true;need(value==pattern(0x80010000ULL+h*4096+(tag/16)*64+(tag%8)*8),"Shuttle warmup data wrong");}}
  need(!t.system.concretized_unknown_replay_timing(),"source warmup concretized unknown RPQ");
  auto shuttle_issue=[&](unsigned h,unsigned cmd,unsigned tag,std::uint64_t address,std::uint64_t data=0){auto tile="shuttle"+std::to_string(h)+"_tile";
    t.set(tile,"_core_io_dmem_req_valid",1);t.set(tile,"_core_io_dmem_req_bits_addr",address);t.set(tile,"_core_io_dmem_req_bits_cmd",cmd);t.set(tile,"_core_io_dmem_req_bits_tag",tag);t.set(tile,"_core_io_dmem_req_bits_size",3);t.set(tile,"_core_io_dmem_s1_data_data",data);
    unsigned wait=0;do{t.iris_step();need(++wait<100,"Shuttle scalar request not accepted");}while(!t.get(tile,"_dcacheArb_io_requestor_1_req_ready"));t.set(tile,"_core_io_dmem_req_valid",0);
  };
  auto await_shuttle=[&](unsigned h,std::size_t before,unsigned tag,std::uint64_t value){for(unsigned wait=0;wait<12000&&t.responses[h].size()==before;++wait)t.iris_step();need(t.responses[h].size()==before+1,"Shuttle response missing or duplicated");need(t.responses[h].back()==std::pair<unsigned,std::uint64_t>{tag,value},"Shuttle coherent response value or tag wrong h="+std::to_string(h)+" expected_tag="+std::to_string(tag)+" actual_tag="+std::to_string(t.responses[h].back().first)+" expected_value="+std::to_string(value)+" actual_value="+std::to_string(t.responses[h].back().second));};
  constexpr auto address=0x80010008ULL;constexpr auto value_a=0x55aa11ee22dd33ccULL,value_b=0xfedcba9876543210ULL;auto initial_ar=t.ar;
  shuttle_issue(0,1,40,address,value_a);for(unsigned i=0;i<20;++i)t.iris_step();
  auto before=t.responses[1].size();shuttle_issue(1,0,41,address);await_shuttle(1,before,41,value_a);
  need(t.probes[0]>0&&t.releases[0]>=8,"Shuttle dirty owner was bypassed");
  auto rocket_operation=[&](unsigned cmd,unsigned tag,std::uint64_t data){auto responses=t.rocket_responses;
    for(unsigned attempt=0;attempt<8;++attempt){auto nacks=t.rocket_nacks;t.issue(cmd,tag,address,data);for(unsigned i=0;i<5;++i)t.iris_step();
      if(t.rocket_responses!=responses)return;
      if(t.rocket_nacks!=nacks){unsigned wait=0;do{t.iris_step();need(++wait<12000,"Rocket physical cache replay never became ordered");}while(!t.get("rocket_cache","io_cpu_ordered"));continue;}
      for(unsigned wait=0;wait<12000&&t.rocket_responses==responses;++wait)t.iris_step();if(t.rocket_responses!=responses)return;
      throw std::runtime_error("Rocket request lacked response/nack ownership");
    }throw std::runtime_error("Rocket source replay exceeded bounded attempts");
  };
  auto rocket_before=t.rocket_responses;rocket_operation(0,29,0);need(t.rocket_responses==rocket_before+1&&t.last_rocket_tag==29&&t.last_rocket_value==value_a,"Rocket did not receive Shuttle-owned value");
  rocket_operation(1,30,value_b);for(unsigned i=0;i<40;++i)t.iris_step();
  before=t.responses[0].size();shuttle_issue(0,0,42,address);await_shuttle(0,before,42,value_b);
  need(t.b>0&&t.c>0,"Rocket dirty-owner probe path was bypassed");need(t.probes[1]>0,"Rocket exclusive write did not probe the other Shuttle");need(t.ar==initial_ar,"shared-line transport silently reread external backing");
  need(!t.system.concretized_unknown_replay_timing(),"shared ownership concretized unknown RPQ");
  constexpr auto value_c=0x1020304050607080ULL;
  shuttle_issue(0,1,48,address,value_c);for(unsigned i=0;i<100;++i)t.iris_step();
  before=t.responses[0].size();shuttle_issue(0,6,49,address);await_shuttle(0,before,49,value_c);
  before=t.responses[0].size();shuttle_issue(0,7,50,address,value_c+1);await_shuttle(0,before,50,0);
  before=t.responses[0].size();shuttle_issue(0,7,51,address,value_c+2);await_shuttle(0,before,51,1);
  before=t.responses[1].size();shuttle_issue(1,8,52,address,1);await_shuttle(1,before,52,value_c+1);
  before=t.responses[0].size();shuttle_issue(0,0,53,address);await_shuttle(0,before,53,value_c+2);
  rocket_operation(8,32,1);need(t.last_rocket_tag==32&&t.last_rocket_value==value_c+2,"Rocket AMO old-value ownership wrong");
  before=t.responses[1].size();shuttle_issue(1,0,54,address);await_shuttle(1,before,54,value_c+3);
  for(unsigned h=0;h<2;++h){auto canonical=0x70000008ULL+h*0x20000;auto value=value_a^h;
    shuttle_issue(h,1,43,canonical,value);for(unsigned i=0;i<40;++i)t.iris_step();
    auto before=t.responses[h].size();shuttle_issue(h,0,44,canonical);await_shuttle(h,before,44,value);
    before=t.responses[h].size();shuttle_issue(h,0,45,0x70080008ULL);await_shuttle(h,before,45,value);
  }
  for(unsigned h=0;h<2;++h){auto before=t.responses[h].size();shuttle_issue(h,0,47,0x70000008ULL+(1-h)*0x20000);await_shuttle(h,before,47,value_a^(1-h));}
  for(unsigned h=0;h<2;++h)for(auto offset:{0x48ULL,0x1ffe8ULL}){auto canonical=0x70000000ULL+h*0x20000+offset;auto value=value_a^offset^h;shuttle_issue(h,1,55,canonical,value);for(unsigned i=0;i<40;++i)t.iris_step();auto prior=t.responses[h].size();shuttle_issue(h,0,56,0x70080000ULL+offset);await_shuttle(h,prior,56,value);prior=t.responses[1-h].size();shuttle_issue(1-h,0,57,canonical);await_shuttle(1-h,prior,57,value);}
  for(unsigned h=0;h<2;++h){auto prior=t.rocket_responses;t.issue(0,31,0x70000008ULL+h*0x20000);for(unsigned wait=0;wait<12000&&t.rocket_responses==prior;++wait)t.iris_step();need(t.rocket_responses==prior+1&&t.last_rocket_value==(value_a^h),"Rocket TCM physical slave route wrong");}
  need(t.ar==initial_ar,"TCM traffic escaped to outer DRAM");
  bool refused=false;try{auto before=t.responses[0].size();shuttle_issue(0,0,46,0x70000010ULL);for(unsigned i=0;i<100;++i)t.iris_step();}catch(const std::runtime_error&e){refused=std::string(e.what()).starts_with("IRIS_SHUTTLE_TCM_UNDEFINED_READ");}
  need(refused,"unwritten TCM SRAM bytes were admitted");
  bool stale=false;try{t.system.sample();}catch(const std::logic_error&){stale=true;}need(stale,"failed TCM commit remained sampleable");
  std::cout<<"{\"seed\":"<<seed<<",\"shuttle0_responses\":"<<t.responses[0].size()<<",\"shuttle1_responses\":"<<t.responses[1].size()<<",\"AXI_AR\":"<<t.ar<<",\"AXI_R\":"<<t.r<<",\"virtual_ticks\":"<<t.tick<<"}\n";
}
}
int main(int argc,char**argv){try{std::string mode=argc==2?argv[1]:"";bad_data=mode=="--wrong-data";cold_store=mode=="--cold-store";for(unsigned seed:{1U,17U})run(seed);std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<"}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
