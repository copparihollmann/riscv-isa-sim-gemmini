// Reuse the frozen physical AXI value fixture, not its post-cork producers.
#define main isolated_serial_transport_main
#include "serial_memory_check.cpp"
#undef main
#include "memory_fabric.hpp"
namespace M=iris::fabric;
namespace {
bool corrupt_return_source=false;
M::Bits all_known(unsigned width){M::Bits b;for(unsigned k=0;k<width;++k)b.limbs[k/64]|=std::uint64_t(1)<<(k%64);return b;}
struct FabricPath {
  Bridge path;
  M::MemoryFabric fabric;
  std::vector<M::Input> in;
  std::vector<M::Bits> out;
  unsigned fabric_settles=0,outer_a=0,outer_d=0,cache_a=0,cache_d=0,cache_e=0,cache_b=0,cache_c=0;
  std::array<std::map<unsigned,unsigned>,4> owners;
  explicit FabricPath(unsigned seed):path(seed),fabric(seed+31),in(M::MemoryFabric::input_fields().size()){
    auto fields=M::MemoryFabric::input_fields();for(unsigned i=0;i<in.size();++i)in[i].known=all_known(fields[i].width);
  }
  void set(std::string_view c,std::string_view f,std::uint64_t v){in[M::MemoryFabric::external_input_index(c,f)].value=M::Bits(v);}
  void wide(std::string_view c,std::string_view f,M::Bits v){in[M::MemoryFabric::external_input_index(c,f)].value=v;}
  std::uint64_t get(std::string_view c,std::string_view f)const{return out[M::MemoryFabric::output_index(c,f)].limbs[0];}
  static std::string port(unsigned b){return "auto_coupler_to_bus_named_mbus_bus_xing_out_"+std::to_string(b);}
  void evaluate(){
    auto fs=M::MemoryFabric::input_fields();
    for(unsigned i=0;i<in.size();++i)if(fs[i].name.ends_with("_reset")||fs[i].name.ends_with("/reset"))in[i].value=M::Bits(path.reset);
    for(unsigned iteration=0;iteration<32;++iteration){
      Verilated::threadContextp(&path.foreign);fabric.evaluate(in);need(Verilated::threadContextp()==&path.foreign,"fabric did not restore source peer context");auto previous=out;out=fabric.sample();
      for(unsigned b=0;b<4;++b){auto mp=port(b),sp=bank(b);
        for(const auto*field:{"a_valid","a_bits_opcode","a_bits_param","a_bits_size","a_bits_source","a_bits_address","a_bits_mask","a_bits_data","a_bits_corrupt","d_ready"})path.set(sp+field,get("manager",mp+"_"+field));
      }
      path.evaluate();bool changed=false;
      for(unsigned b=0;b<4;++b){auto mp=port(b),sp=bank(b);
        for(const auto*field:{"a_ready","d_valid","d_bits_opcode","d_bits_param","d_bits_size","d_bits_source","d_bits_data","d_bits_denied","d_bits_corrupt"}){
          auto index=M::MemoryFabric::external_input_index("manager",mp+"_"+field);auto value=path.get(sp+field);if(corrupt_return_source&&std::string_view(field)=="d_bits_source")value^=1;changed|=in[index].value.limbs[0]!=value;in[index].value=M::Bits(value);
        }
      }
      ++fabric_settles;if(!changed&&previous==out)return;
    }
    throw std::runtime_error("cache/NoC/L2/Serial/Bringup/FASED fixed point did not settle");
  }
  void step(){
    evaluate();bool edge=path.tick%2==0;
    if(edge){
      if(!path.reset){
        for(unsigned b=0;b<4;++b){auto p=port(b);
          if(get("manager",p+"_a_valid")&&path.get(bank(b)+"a_ready")){need(get("manager",p+"_a_bits_opcode")==4&&get("manager",p+"_a_bits_size")==6,"initial coupled corpus expects source64BGet");unsigned source=get("manager",p+"_a_bits_source");need(!owners[b].count(source),"source manager reused an outstanding outer tag");owners[b][source]=8;++outer_a;}
          if(path.get(bank(b)+"d_valid")&&get("manager",p+"_d_ready")){auto index=M::MemoryFabric::external_input_index("manager",p+"_d_bits_source");unsigned source=in[index].value.limbs[0];need(owners[b].count(source),"IRIS_COUPLED_RETURN_SOURCE_NOT_OWNED");if(!--owners[b][source])owners[b].erase(source);++outer_d;}
        }
        cache_a+=get("rocket_cache","auto_out_a_valid")&&get("rocket_tile","_widget_auto_anon_in_a_ready");cache_d+=get("rocket_tile","_widget_auto_anon_in_d_valid")&&get("rocket_cache","auto_out_d_ready");cache_e+=get("rocket_cache","auto_out_e_valid")&&get("rocket_tile","_widget_auto_anon_in_e_ready");cache_b+=get("rocket_tile","_widget_auto_anon_in_b_valid")&&get("rocket_cache","auto_out_b_ready");cache_c+=get("rocket_cache","auto_out_c_valid")&&get("rocket_tile","_widget_auto_anon_in_c_ready");
      }
      fabric.commit({true,true});
    }
    path.commit();
  }
  void iris_step(){auto target=fabric.rocket_edges()+1;do{step();}while(fabric.rocket_edges()!=target);}
  void reset(){
    path.reset=true;set("rocket_cache","io_cpu_req_bits_dprv",3);
    for(unsigned i=0;i<100;++i)step();path.reset=false;
    for(unsigned i=0;i<600;++i)iris_step();
    need(get("rocket_cache","io_cpu_ordered"),"source cache reset/sweep failed");
  }
  void issue(unsigned command,unsigned tag,std::uint64_t address,std::uint64_t data=0){
    set("rocket_cache","io_cpu_req_bits_addr",address);set("rocket_cache","io_cpu_req_bits_tag",tag);set("rocket_cache","io_cpu_req_bits_cmd",command);set("rocket_cache","io_cpu_req_bits_size",3);set("rocket_cache","io_cpu_req_bits_mask",0xffffffff);set("rocket_cache","io_cpu_s1_data_mask",0xffffffff);M::Bits wide_data;wide_data.limbs.fill(data);wide("rocket_cache","io_cpu_s1_data_data",wide_data);set("rocket_cache","io_cpu_req_valid",1);
    unsigned wait=0;do{iris_step();need(++wait<100,"real cache request did not accept");}while(!get("rocket_cache","io_cpu_req_ready"));set("rocket_cache","io_cpu_req_valid",0);
  }
};
void case_cache_serial(unsigned seed){
  FabricPath t(seed);t.reset();auto begin=t.path.tick;t.issue(0,17,0x80000008);bool cold_return=false;
  for(unsigned n=0;n<12000;++n){t.iris_step();if(t.get("rocket_cache","io_cpu_resp_valid")){need(t.get("rocket_cache","io_cpu_resp_bits_tag")==17,"cold cache returned wrong tag");need(t.get("rocket_cache","io_cpu_resp_bits_data")==initial(0x80000008),"cold cache value differs from original address formula");cold_return=true;}if(t.path.r_count==8&&t.get("rocket_cache","io_cpu_ordered")&&t.cache_e)break;need(n<11999,"full sourced memory path did not refill");}
  need(t.path.ar_count==1&&t.path.r_count==8&&t.outer_a==1&&t.outer_d==8,"cold path request/beat conservation failed");need(t.cache_a==1&&t.cache_d==2&&t.cache_e==1,"source cache width/GrantAck sequence changed");auto refill=t.path.tick-begin;
  auto ar_before=t.path.ar_count;t.issue(0,18,0x80000008);bool warm=false;
  for(unsigned n=0;n<20;++n){t.iris_step();if(t.get("rocket_cache","io_cpu_resp_valid")){need(t.get("rocket_cache","io_cpu_resp_bits_tag")==18,"warm tag mismatch");need(t.get("rocket_cache","io_cpu_resp_bits_data")==initial(0x80000008),"warm cache data mismatch");warm=true;}}
  need(warm&&t.path.ar_count==ar_before,"warm cache hit invented external service");
  const std::uint64_t value=0x55aa11ee22dd33ccULL;t.issue(1,19,0x80000008,value);for(unsigned n=0;n<15;++n)t.iris_step();t.issue(0,20,0x80000008);warm=false;
  for(unsigned n=0;n<20;++n){t.iris_step();if(t.get("rocket_cache","io_cpu_resp_valid")){need(t.get("rocket_cache","io_cpu_resp_bits_data")==value,"cached store/load value changed");warm=true;}}need(warm,"cached store reload did not return");
  unsigned fetch_beats=0;auto old_b=t.cache_b,old_c=t.cache_c;
  auto capture=[&](){if(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid")){need(fetch_beats<8,"Icache duplicate data beat");need(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_bits_opcode")==1,"Icache response opcode changed");auto expected=fetch_beats==1?value:initial(0x80000000+8*fetch_beats);need(t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_bits_data")==expected,"dirty owner data/line address changed");++fetch_beats;}};
  t.set("rocket_tile","_frontend_auto_icache_master_out_a_valid",1);t.set("rocket_tile","_frontend_auto_icache_master_out_a_bits_address",0x80000000);unsigned wait=0;do{t.iris_step();capture();need(++wait<100,"source Icache request did not accept");}while(!t.get("rocket_tile","_tlMasterXbar_auto_anon_in_1_a_ready"));t.set("rocket_tile","_frontend_auto_icache_master_out_a_valid",0);for(unsigned n=0;n<300;++n){t.iris_step();capture();}
  need(fetch_beats==8&&t.cache_b==old_b+1&&t.cache_c==old_c+2,"source cache-to-Icache coherence ownership changed");need(t.path.ar_count==ar_before&&t.path.aw_count==0,"dirty owner transfer invented an external refill/writeback");
  std::cout<<"{\"seed\":"<<seed<<",\"cold_refill_inclusive_virtual_phases\":"<<refill<<",\"cold_cache_response_observed\":"<<(cold_return?"true":"false")<<",\"AXI_AR\":"<<t.path.ar_count<<",\"AXI_R\":"<<t.path.r_count<<",\"cache_A\":"<<t.cache_a<<",\"cache_D\":"<<t.cache_d<<",\"cache_E\":"<<t.cache_e<<",\"cache_B\":"<<t.cache_b<<",\"cache_C\":"<<t.cache_c<<",\"Icache_D\":"<<fetch_beats<<",\"source_virtual_phases\":"<<t.path.tick<<"}\n";
}
}
int main(int argc,char**argv){try{if(argc==2){std::string arg(argv[1]);corrupt_data=arg=="--wrong-data";corrupt_return_source=arg=="--wrong-return-source";}for(unsigned seed:{1U,17U})case_cache_serial(seed);std::cout<<"{\"status\":\"passed_source_cache_NoC_L2_serial_Bringup_FASED\",\"checks\":"<<checks<<",\"post_cork_synthetic_delay_removed\":true,\"external_AXI_value_fixture\":true,\"real_CPU_pipeline\":false,\"hardware_contacted\":false,\"calibration_usable\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<"coupled source path: "<<e.what()<<'\n';return 1;}}
