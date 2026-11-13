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
  bool record=false,idle_hart1=false;
  std::vector<std::uint64_t> idle_hart1_B,idle_hart1_C,idle_hart1_data;
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
      if(h==1&&idle_hart1){need(in[input_index(tile,"_core_io_dmem_req_valid")].value.limbs[0]==0,"inactive hart1 issued a scalar request");if(get(tile,"_widget_1_auto_anon_in_b_valid")&&get(cache,"auto_out_b_ready"))idle_hart1_B.push_back(core_edges);if(get(cache,"auto_out_c_valid")&&get(tile,"_widget_1_auto_anon_in_c_ready")){idle_hart1_C.push_back(core_edges);if(get(cache,"auto_out_c_bits_opcode")==5)idle_hart1_data.push_back(get(cache,"auto_out_c_bits_data"));}}
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

void run(unsigned seed){
 Fixture t(seed);t.startup();t.record=true;
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

 constexpr std::uint64_t address=0x80010008ULL,value=0x12345678aabbccddULL;
 auto old=t.responses[1].size();shuttle_issue(1,0,41,address);await_shuttle(1,old,41,pattern(address));
 shuttle_issue(1,1,42,address,value);for(unsigned i=0;i<128;++i)t.iris_step();
 const auto ar=t.ar;need(t.in[t.input_index("shuttle1_tile","_core_io_dmem_req_valid")].value.limbs[0]==0,"hart1 did not become inactive");t.idle_hart1=true;
 // The CPU is outside this cut. Holding its actual scalar request-valid low
 // models an inactive issuer, without injecting WFI/internal cache state.
 // Static source clock/CSR proofs connect this scope to WFI separately.
 old=t.responses[0].size();shuttle_issue(0,0,43,address);await_shuttle(0,old,43,value);
 need(!t.idle_hart1_B.empty(),"inactive dirty owner accepted no actual B probe");
 need(t.idle_hart1_C.size()>=8&&t.idle_hart1_data.size()==8,"inactive dirty owner did not return complete ProbeAckData");
 need(t.idle_hart1_data[1]==value,"dirty target word was not transported by C");
 for(unsigned i=0;i<8;++i)if(i!=1)need(t.idle_hart1_data[i]==pattern((address&~63ULL)+i*8),"untouched dirty line byte data changed");
 need(t.ar==ar,"peer load bypassed dirty owner and reread outer backing");
 need(t.idle_hart1_B.front()<t.idle_hart1_C.front(),"C data preceded accepted B ownership");
 std::cout<<"{\"seed\":"<<seed<<",\"inactive_hart\":1,\"B_probe_accept_edges\":[";
 for(unsigned i=0;i<t.idle_hart1_B.size();++i){if(i)std::cout<<',';std::cout<<t.idle_hart1_B[i];}
 std::cout<<"],\"C_ProbeAckData_beats\":"<<t.idle_hart1_data.size()<<",\"first_C_edge\":"<<t.idle_hart1_C.front()<<",\"last_C_edge\":"<<t.idle_hart1_C.back()<<",\"outer_reads_during_probe\":"<<t.ar-ar<<",\"peer_received_dirty_value\":true,\"CPU_WFI_instruction_executed_in_this_cut\":false,\"injected_internal_state_or_ready\":false}\n";
}
}
int main(){try{for(unsigned s:{1U,17U})run(s);std::cout<<"{\"pass\":true,\"checks\":"<<checks<<"}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
