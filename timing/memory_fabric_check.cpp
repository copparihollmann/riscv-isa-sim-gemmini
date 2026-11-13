#include "memory_fabric.hpp"
#include <algorithm>
#include <array>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <string>
using namespace iris::fabric;
static unsigned checks=0;
static void expect(bool yes,const std::string&why){++checks;if(!yes)throw std::runtime_error(why);}
static Bits known(unsigned width){Bits b;for(unsigned bit=0;bit<width;++bit)b.limbs[bit/64]|=std::uint64_t(1)<<(bit%64);return b;}
static std::uint64_t pattern(std::uint64_t address){return 0x93ac4e1000000000ULL^address;}
struct Request{std::uint64_t source,address,size,opcode,beat=0,accepted;};
struct Test {
 MemoryFabric model;
 std::vector<Input>in;
 std::vector<Bits>out;
 std::array<std::deque<Request>,4>requests;
 std::array<bool,4>serving{};
 bool service=false;
 unsigned cycle=0,outer_requests=0,outer_beats=0,cache_a=0,cache_d=0,cache_e=0,cache_b=0,cache_c=0,source_a=0,source_d=0,manager_a=0,manager_d=0;
 explicit Test(unsigned seed):model(seed),in(MemoryFabric::input_fields().size()),out(MemoryFabric::output_fields().size()){
  auto f=MemoryFabric::input_fields();for(unsigned i=0;i<in.size();++i)in[i].known=known(f[i].width);
 }
 unsigned input(std::string_view comp,std::string_view field){return MemoryFabric::external_input_index(comp,field);}
 unsigned output(std::string_view comp,std::string_view field){return MemoryFabric::output_index(comp,field);}
 void set(std::string_view comp,std::string_view field,std::uint64_t value){in[input(comp,field)].value=Bits(value);}
 void setwide(std::string_view comp,std::string_view field,Bits value){in[input(comp,field)].value=value;}
 std::uint64_t get(std::string_view comp,std::string_view field)const{return out[MemoryFabric::output_index(comp,field)].limbs[0];}
 static std::string port(unsigned bank){return "auto_coupler_to_bus_named_mbus_bus_xing_out_"+std::to_string(bank);}
 void eval(){model.evaluate(in);out=model.sample();}
 void tick(ClockEdges edges={true,true}){
  for(unsigned b=0;b<4;++b){auto p=port(b);set("manager",p+"_a_ready",service);set("manager",p+"_d_valid",0);serving[b]=false;
   if(service&&!requests[b].empty()&&cycle>=requests[b].front().accepted+3){const auto&q=requests[b].front();serving[b]=true;set("manager",p+"_d_valid",1);set("manager",p+"_d_bits_opcode",1);set("manager",p+"_d_bits_param",0);set("manager",p+"_d_bits_size",q.size);set("manager",p+"_d_bits_source",q.source);set("manager",p+"_d_bits_data",pattern(q.address+8*q.beat));set("manager",p+"_d_bits_denied",0);set("manager",p+"_d_bits_corrupt",0);}
  }
  eval();
  if(edges.uncore){for(unsigned b=0;b<4;++b){auto p=port(b);
    if(serving[b]&&get("manager",p+"_d_ready")){auto&q=requests[b].front();++outer_beats;if(++q.beat==(std::uint64_t(1)<<q.size)/8)requests[b].pop_front();}
    if(service&&get("manager",p+"_a_valid")){auto opcode=get("manager",p+"_a_bits_opcode");expect(opcode==4,"explicit synthetic service expects source-cork Get");requests[b].push_back({get("manager",p+"_a_bits_source"),get("manager",p+"_a_bits_address"),get("manager",p+"_a_bits_size"),opcode,0,cycle});++outer_requests;}
  }}
  if(edges.rocket){cache_b+=get("rocket_tile","_widget_auto_anon_in_b_valid")&&get("rocket_cache","auto_out_b_ready");cache_c+=get("rocket_cache","auto_out_c_valid")&&get("rocket_tile","_widget_auto_anon_in_c_ready");cache_a+=get("rocket_cache","auto_out_a_valid")&&get("rocket_tile","_widget_auto_anon_in_a_ready");cache_d+=get("rocket_tile","_widget_auto_anon_in_d_valid")&&get("rocket_cache","auto_out_d_ready");cache_e+=get("rocket_cache","auto_out_e_valid")&&get("rocket_tile","_widget_auto_anon_in_e_ready");}
  model.commit(edges);++cycle;
 }
 void reset(){
  for(unsigned i=0;i<in.size();++i){auto n=MemoryFabric::input_fields()[i].name;if(n.ends_with("_reset")||n.ends_with("/reset"))in[i].value=Bits(1);}
  set("rocket_cache","io_cpu_req_bits_dprv",3);
  for(unsigned n=0;n<8;++n)tick();
  for(unsigned i=0;i<in.size();++i){auto n=MemoryFabric::input_fields()[i].name;if(n.ends_with("_reset")||n.ends_with("/reset"))in[i].value=Bits(0);}
  for(unsigned n=0;n<600;++n)tick();expect(get("rocket_cache","io_cpu_ordered"),"source reset/sweep completes Rocket cache");
 }
 void issue(unsigned cmd,unsigned tag,std::uint64_t address,std::uint64_t data=0){
  set("rocket_cache","io_cpu_req_bits_addr",address);set("rocket_cache","io_cpu_req_bits_tag",tag);set("rocket_cache","io_cpu_req_bits_cmd",cmd);set("rocket_cache","io_cpu_req_bits_size",3);set("rocket_cache","io_cpu_req_bits_mask",0xffffffff);set("rocket_cache","io_cpu_s1_data_mask",0xffffffff);Bits d;d.limbs.fill(data);setwide("rocket_cache","io_cpu_s1_data_data",d);set("rocket_cache","io_cpu_req_valid",1);
  unsigned wait=0;do{tick();expect(++wait<100,"source CPU request accepted without readiness replay");}while(!get("rocket_cache","io_cpu_req_ready"));set("rocket_cache","io_cpu_req_valid",0);
 }
};
static void lifecycle(){
 Test t(1);bool refused=false;try{t.model.sample();}catch(const std::logic_error&){refused=true;}expect(refused,"no sample before coupled evaluation");
 refused=false;try{t.model.commit({true,true});}catch(const std::logic_error&){refused=true;}expect(refused,"no commit before evaluation");
 refused=false;try{t.model.evaluate(t.in);}catch(const std::logic_error&){refused=true;}expect(refused,"coupled source models require an actual committed reset");expect(t.model.rocket_edges()==0&&t.model.uncore_edges()==0,"pre-reset refusal no clock edge");
 t.reset();auto re=t.model.rocket_edges(),ue=t.model.uncore_edges();auto q=t.input("rocket_cache","io_cpu_req_bits_addr");t.in[q].known.limbs[0]&=~std::uint64_t(1);refused=false;try{t.eval();}catch(const std::runtime_error&e){refused=std::string(e.what()).find("IRIS_MEMORY_FABRIC_UNKNOWN_EXTERNAL_INPUT")!=std::string::npos;}expect(refused,"unknown external data/control bit refuses before evaluation");expect(t.model.rocket_edges()==re&&t.model.uncore_edges()==ue,"unknown input no clock advance");
 refused=false;try{t.model.commit({true,true});}catch(const std::logic_error&){refused=true;}expect(refused,"unknown input invalidates pending commit");t.in[q].known=known(MemoryFabric::input_fields()[q].width);
 refused=false;try{t.input("rocket_cache","auto_out_a_ready");}catch(const std::invalid_argument&){refused=true;}expect(refused,"cannot inject joined cache Aready");
 refused=false;try{t.input("l2","auto_in_0_a_valid");}catch(const std::invalid_argument&){refused=true;}expect(refused,"cannot inject joined L2 Avalid");
 t.eval();auto first=t.out;for(unsigned n=0;n<7;++n){t.eval();expect(t.out==first,"repeated same-edge global settling is idempotent");}t.model.commit({true,false});expect(t.model.rocket_edges()==re+1&&t.model.uncore_edges()==ue,"explicit Rocket-only edge preserves source domains");t.eval();t.model.commit({false,true});expect(t.model.rocket_edges()==re+1&&t.model.uncore_edges()==ue+1,"explicit uncore-only edge preserves source domains");
 t.eval();refused=false;try{t.model.commit({false,false});}catch(const std::invalid_argument&){refused=true;}expect(refused,"empty clock event refuses");refused=false;try{t.model.sample();}catch(const std::logic_error&){refused=true;}expect(refused,"empty clock refusal invalidates phase");
}
static void load_path(unsigned seed){
 Test t(seed);t.reset();t.issue(0,17,0x80000008);bool outer=false;
 for(unsigned n=0;n<400;++n){t.tick();for(unsigned b=0;b<4;++b)outer|=t.get("manager",Test::port(b)+"_a_valid");expect(!t.get("rocket_cache","io_cpu_resp_valid"),"cold load cannot complete without external memory service");}
 expect(outer,"cold load traverses actual tile/CDC/NoC/L2/cork to an outer request");expect(t.outer_requests==0&&t.outer_beats==0,"blocked explicit service accepts no request or beat");
 t.service=true;for(unsigned n=0;n<400;++n)t.tick();expect(t.outer_requests==1,"one cold64B refill at actual outer boundary");expect(t.outer_beats==8,"outer service returns eight physical64bit beats");expect(t.cache_a==1&&t.cache_d==2&&t.cache_e==1,"cache256b and fabric64b widths retain1Acquire/2GrantData/1GrantAck");
 auto warm_outer=t.outer_requests;t.issue(0,18,0x80000008);bool response=false;for(unsigned n=0;n<20;++n){t.tick();if(t.get("rocket_cache","io_cpu_resp_valid")){response=true;expect(t.get("rocket_cache","io_cpu_resp_bits_tag")==18,"coupled warm load tag");expect(t.get("rocket_cache","io_cpu_resp_bits_data")==pattern(0x80000008),"whole coupled load value matches independent memory formula");}}
 expect(response,"CPU retry after actual miss/refill returns data");expect(t.outer_requests==warm_outer,"warm hit does not create a guessed external request");
 const auto stored=0x55aa11ee22dd33ccULL;t.issue(1,19,0x80000008,stored);for(unsigned n=0;n<15;++n)t.tick();t.issue(0,20,0x80000008);response=false;for(unsigned n=0;n<20;++n){t.tick();if(t.get("rocket_cache","io_cpu_resp_valid")){response=true;expect(t.get("rocket_cache","io_cpu_resp_bits_data")==stored,"coupled warm store/load value survives real cache pipeline");}}expect(response,"coupled stored data reload completes");
 // A real source-specialized Icache Get actor enters the actual Rocket
 // tile arbiter. Its sourceID is assigned by the source xbar, not this test.
 // Reading the dirty Dcache line must produce actual B/C coherence traffic.
 unsigned fetch_beats=0;auto old_b=t.cache_b,old_c=t.cache_c;auto capture_fetch=[&](){if(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid")){expect(fetch_beats<8,"Icache fetch has no duplicated data beat");expect(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_bits_opcode")==1,"Icache Get returns AccessAckData");auto expected=fetch_beats==1?stored:pattern(0x80000000+8*fetch_beats);expect(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_bits_data")==expected,"Icache sees actual dirty-owner data through coupled B/C/D");++fetch_beats;}};
 t.set("rocket_tile","_frontend_auto_icache_master_out_a_valid",1);t.set("rocket_tile","_frontend_auto_icache_master_out_a_bits_address",0x80000000);unsigned wait=0;do{t.tick();capture_fetch();expect(++wait<100,"Icache source A accepted by actual xbar");}while(!t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_a_ready"));t.set("rocket_tile","_frontend_auto_icache_master_out_a_valid",0);
 for(unsigned n=0;n<300;++n){t.tick();capture_fetch();}
 expect(fetch_beats==8,"Icache full64B fetch returns all eight actual64bit beats");expect(t.cache_b==old_b+1,"L2 probes actual Rocket dirty owner");expect(t.cache_c==old_c+2,"dirty owner responds with two actual256bit C beats");expect(t.outer_requests==warm_outer,"dirty-owner handoff does not fabricate a DRAM refill");
 std::cout<<"{\"seed\":"<<seed<<",\"outer_requests\":"<<t.outer_requests<<",\"outer_beats\":"<<t.outer_beats<<",\"cache_A\":"<<t.cache_a<<",\"cache_D\":"<<t.cache_d<<",\"cache_E\":"<<t.cache_e<<",\"rocket_edges\":"<<t.model.rocket_edges()<<",\"uncore_edges\":"<<t.model.uncore_edges()<<"}\n";
}
int main(){try{lifecycle();for(unsigned seed:{1,7,31,113})load_path(seed);std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"source_identity\":\""<<MemoryFabric::source_identity()<<"\",\"service\":\"explicit synthetic test fixture, not Iris timing\",\"hardware_contacted\":false,\"timing_certified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<"memory fabric failure after "<<checks<<" checks: "<<e.what()<<"\n";return 1;}}
