#include "shuttle_memory_system.hpp"
#include "serial_memory_system.hpp"
#include "fased_backing_service_v2.hpp"
#include "verilated.h"
#include <iostream>
#include <map>
#include <string>
namespace P=iris::shuttle_system;
namespace O=iris::memory_system;
namespace B=iris::fased_backing;
namespace S=iris::serial_memory;
namespace {
std::uint64_t checks=0;
void need(bool value,const std::string&text){++checks;if(!value)throw std::runtime_error(text);}
P::Bits known(unsigned width){P::Bits b;for(unsigned n=0;n<width;++n)b.limbs[n/64]|=std::uint64_t(1)<<(n%64);return b;}
std::uint64_t pattern(std::uint64_t address){return 0x93ac4e1000000000ULL^address;}
struct Fixture {
  VerilatedContext foreign;
  P::System system;
  O::System catalog;
  B::ServiceV2 service;
  std::vector<P::Input>in;
  std::vector<P::Bits>out;
  B::Inputs bin;
  B::Outputs bout;
  std::uint64_t tick=0,core_edges=0,ar=0,aw=0,w=0,r=0,b=0;
  bool reset=true;
  std::uint64_t previous_address[2]{};
  std::vector<std::pair<unsigned,std::uint64_t>>responses[2];
  std::map<std::uint64_t,std::uint64_t>expected;
  struct Write {std::uint64_t address;unsigned id,len;std::vector<B::WBeat>beats;};
  std::deque<Write>accepted_aw,paired_writes;
  std::deque<std::vector<B::WBeat>>complete_w;
  std::vector<B::WBeat>partial_w;
  std::vector<std::uint64_t>published_write_lines;
  explicit Fixture(unsigned seed):system(seed,{"new-write-backing-check","+tilelink_timeout=0"},S::AssertionPolicy::SuppressOnlyWhileBothExternalResets),catalog(seed,{},S::AssertionPolicy::SourceAlways),
      service({30,30,16,16},seed+113,{"new-write-backing-check"},{{0x80000000,0x400000}},B::Visibility::ExternalFencedDisjoint),in(system.input_fields().size()){
    const auto fields=system.input_fields();for(unsigned i=0;i<in.size();++i)in[i].known=known(fields[i].width);
    auto initialize_line=[&](std::uint64_t address){std::vector<B::Byte>bytes;for(unsigned n=0;n<64;++n){const auto word=pattern((address+n)&~std::uint64_t(7));bytes.push_back({std::uint8_t(word>>(8*((address+n)&7))),255});}service.initialize(address,bytes);};
    for(unsigned h=0;h<2;++h){for(unsigned n=0;n<4;++n)initialize_line(0x80010000+h*4096+n*64);for(unsigned n=0;n<16;++n)initialize_line(0x80020000+h*4096+n*0x20000);}
  }
  unsigned ii(std::string_view c,std::string_view f)const{if(c.starts_with("shuttle"))return system.external_input_index(c,f);return system.external_input_index("system",catalog.input_fields()[catalog.external_input_index(c,f)].name);}
  unsigned oi(std::string_view c,std::string_view f)const{if(c.starts_with("shuttle"))return system.output_index(c,f);return system.output_index("system",catalog.output_fields()[catalog.output_index(c,f)].name);}
  void set(std::string_view c,std::string_view f,std::uint64_t value){in[ii(c,f)].value=P::Bits(value);}
  std::uint64_t get(std::string_view c,std::string_view f)const{return out[oi(c,f)].limbs[0];}
  std::uint64_t axi(const std::string&f)const{return get("path","fased_axi4_mem_0_bits_"+f);}
  B::Request request(const char*channel)const{const auto p=std::string(channel)+"_bits_";return B::Request::concrete(axi(p+"addr"),axi(p+"id"),axi(p+"len"),axi(p+"size"),axi(p+"burst"),axi(p+"lock"));}
  void evaluate(){
    auto fields=system.input_fields();for(unsigned i=0;i<in.size();++i)if(fields[i].name.ends_with("_reset")||fields[i].name.ends_with("/reset")||fields[i].name.ends_with("/iris_pad_reset_io"))in[i].value=P::Bits(reset);
    bin.reset=B::known(1,reset);
    for(unsigned iteration=0;iteration<64;++iteration){
      Verilated::threadContextp(&foreign);service.evaluate_control(bin);need(Verilated::threadContextp()==&foreign,"service evaluate context");bout=service.sample();
      for(auto [name,value]:std::initializer_list<std::pair<const char*,std::uint64_t>>{{"ar_ready",bout.ar_ready},{"aw_ready",bout.aw_ready},{"w_ready",bout.w_ready},{"r_valid",bout.r_valid},{"r_bits_data",bout.r_data},{"r_bits_id",bout.r_id},{"r_bits_last",bout.r_last},{"b_valid",bout.b_valid},{"b_bits_id",bout.b_id}})set("path","fased_axi4_mem_0_bits_"+std::string(name),value);
      auto previous=out;system.evaluate(in);need(Verilated::threadContextp()==&foreign,"System evaluate context");out=system.sample();
      B::Inputs next;next.reset=B::known(1,reset);
      next.ar_valid=B::known(1,!reset&&axi("ar_valid"));next.aw_valid=B::known(1,!reset&&axi("aw_valid"));next.w_valid=B::known(1,!reset&&axi("w_valid"));
      next.r_ready=B::known(1,!reset&&axi("r_ready"));next.b_ready=B::known(1,!reset&&axi("b_ready"));
      if(next.ar_valid.value)next.ar=request("ar");if(next.aw_valid.value)next.aw=request("aw");
      if(next.w_valid.value)next.w=B::WBeat::concrete(axi("w_bits_data"),axi("w_bits_strb"),axi("w_bits_last"));
      // Values/known masks are entirely explicit; no derived data or source
      // readiness is injected. Re-evaluate once more after any AXI change.
      bool same=next.ar_valid.value==bin.ar_valid.value&&next.aw_valid.value==bin.aw_valid.value&&next.w_valid.value==bin.w_valid.value&&next.r_ready.value==bin.r_ready.value&&next.b_ready.value==bin.b_ready.value;
      if(next.ar_valid.value)same&=next.ar.address.value==bin.ar.address.value&&next.ar.id.value==bin.ar.id.value&&next.ar.len.value==bin.ar.len.value&&next.ar.size.value==bin.ar.size.value&&next.ar.burst.value==bin.ar.burst.value&&next.ar.lock.value==bin.ar.lock.value;
      if(next.aw_valid.value)same&=next.aw.address.value==bin.aw.address.value&&next.aw.id.value==bin.aw.id.value&&next.aw.len.value==bin.aw.len.value&&next.aw.size.value==bin.aw.size.value&&next.aw.burst.value==bin.aw.burst.value&&next.aw.lock.value==bin.aw.lock.value;
      if(next.w_valid.value)same&=next.w.data.value==bin.w.data.value&&next.w.strobe.value==bin.w.strobe.value&&next.w.last.value==bin.w.last.value;
      bin=next;if(same&&previous==out){service.prepare();return;}
    }throw std::runtime_error("write-capable System/LP combinational fixed point");
  }
  void step(){
    for(unsigned h=0;h<2;++h)set("shuttle"+std::to_string(h)+"_tile","_core_io_dmem_s1_paddr",previous_address[h]);
    evaluate();const bool edge=tick%2==0;
    std::optional<Write>publication;
    if(!reset){if(edge)for(unsigned h=0;h<2;++h){const auto tile="shuttle"+std::to_string(h)+"_tile";if(in[ii(tile,"_core_io_dmem_req_valid")].value.limbs[0]&&get(tile,"_dcacheArb_io_requestor_1_req_ready"))previous_address[h]=in[ii(tile,"_core_io_dmem_req_bits_addr")].value.limbs[0];if(get(tile,"_dcacheArb_io_requestor_1_resp_valid")&&get(tile,"_dcacheArb_io_requestor_1_resp_bits_has_data"))responses[h].push_back({unsigned(get(tile,"_dcacheArb_io_requestor_1_resp_bits_tag")),get(tile,"_dcacheArb_io_requestor_1_resp_bits_data")});}
      if(bin.aw_valid.value&&bout.aw_ready){need(bin.aw.len.value==7&&bin.aw.size.value==3,"actual source AW full-line shape");accepted_aw.push_back({bin.aw.address.value,unsigned(bin.aw.id.value),unsigned(bin.aw.len.value),{}});std::cerr<<"AW tick="<<tick<<" address="<<bin.aw.address.value<<" id="<<bin.aw.id.value<<'\n';}
      if(bin.w_valid.value&&bout.w_ready){partial_w.push_back(bin.w);if(bin.w.last.value){complete_w.push_back(std::move(partial_w));partial_w.clear();}}
      while(!accepted_aw.empty()&&!complete_w.empty()){auto owner=accepted_aw.front();accepted_aw.pop_front();owner.beats=std::move(complete_w.front());complete_w.pop_front();need(owner.beats.size()==owner.len+1,"independent source AW/W ownership length");for(unsigned n=0;n<owner.beats.size();++n){const auto address=owner.address+8*n;const auto golden=expected.contains(address)?expected.at(address):pattern(address);need(owner.beats[n].strobe.value==255&&owner.beats[n].data.value==golden&&bool(owner.beats[n].last.value)==(n==owner.len),"independent accepted source write data/strobe/WLAST golden");}paired_writes.push_back(std::move(owner));}
      if(bout.b_valid&&bin.b_ready.value){need(!paired_writes.empty()&&paired_writes.front().id==bout.b_id,"independent actual B FIFO/ID ownership");publication=std::move(paired_writes.front());paired_writes.pop_front();std::cerr<<"B tick="<<tick<<" address="<<publication->address<<" id="<<bout.b_id<<'\n';}
      ar+=bin.ar_valid.value&&bout.ar_ready;aw+=bin.aw_valid.value&&bout.aw_ready;w+=bin.w_valid.value&&bout.w_ready;r+=bout.r_valid&&bin.r_ready.value;b+=bout.b_valid&&bin.b_ready.value;
    }
    system.commit({edge,edge,true,tick%10==0});service.commit();need(Verilated::threadContextp()==&foreign,"commit foreign context restoration");
    if(publication){published_write_lines.push_back(publication->address);for(unsigned n=0;n<64;++n){const auto address=publication->address+n,word_address=address&~std::uint64_t(7);const auto golden=expected.contains(word_address)?expected.at(word_address):pattern(word_address);const auto actual=service.ledger().inspect(address);need(actual.known==255&&actual.value==std::uint8_t(golden>>(8*(address&7))),"actual B-published byte oracle");}}
    if(edge)++core_edges;++tick;
  }
  void core_step(){const auto goal=core_edges+1;do{step();}while(core_edges!=goal);}
  void startup(){set("rocket_cache","io_cpu_req_bits_dprv",3);for(unsigned n=0;n<100;++n)step();reset=false;for(unsigned n=0;n<600;++n)core_step();}
  void warmup(){
    unsigned accepted[2]{};
    for(unsigned cycle=0;(accepted[0]<64||accepted[1]<64)&&cycle<3000;++cycle){for(unsigned h=0;h<2;++h){auto tile="shuttle"+std::to_string(h)+"_tile";auto n=accepted[h];set(tile,"_core_io_dmem_req_valid",n<64);set(tile,"_core_io_dmem_req_bits_addr",0x80010000ULL+h*4096+(n/16)*64+(n%8)*8);set(tile,"_core_io_dmem_req_bits_tag",n);set(tile,"_core_io_dmem_req_bits_cmd",0);set(tile,"_core_io_dmem_req_bits_size",3);}core_step();for(unsigned h=0;h<2;++h)if(accepted[h]<64&&get("shuttle"+std::to_string(h)+"_tile","_dcacheArb_io_requestor_1_req_ready"))++accepted[h];}
    for(unsigned h=0;h<2;++h){need(accepted[h]==64,"explicit source warmup admission");set("shuttle"+std::to_string(h)+"_tile","_core_io_dmem_req_valid",0);}
    for(unsigned n=0;n<20000&&(responses[0].size()!=64||responses[1].size()!=64);++n)core_step();
    for(unsigned h=0;h<2;++h){need(responses[h].size()==64,"explicit source warmup response count");bool seen[64]{};for(auto[tag,value]:responses[h]){need(tag<64&&!seen[tag],"warmup duplicate/lost response");seen[tag]=true;need(value==pattern(0x80010000ULL+h*4096+(tag/16)*64+(tag%8)*8),"warmup independent byte golden");}}
    need(!system.concretized_unknown_replay_timing(),"unknown RPQ timing was concretized");
  }
  void issue(unsigned h,unsigned cmd,unsigned tag,std::uint64_t address,std::uint64_t data=0){auto tile="shuttle"+std::to_string(h)+"_tile";set(tile,"_core_io_dmem_req_valid",1);set(tile,"_core_io_dmem_req_bits_addr",address);set(tile,"_core_io_dmem_req_bits_cmd",cmd);set(tile,"_core_io_dmem_req_bits_tag",tag);set(tile,"_core_io_dmem_req_bits_size",3);set(tile,"_core_io_dmem_s1_data_data",data);unsigned n=0;do{core_step();need(++n<300,"source scalar request admission bound");}while(!get(tile,"_dcacheArb_io_requestor_1_req_ready"));set(tile,"_core_io_dmem_req_valid",0);}
  void load(unsigned h,unsigned tag,std::uint64_t address,std::uint64_t expected){const auto before=responses[h].size();issue(h,0,tag,address);for(unsigned n=0;n<20000&&responses[h].size()==before;++n)core_step();need(responses[h].size()==before+1,"scalar load response count");need(responses[h].back()==std::pair<unsigned,std::uint64_t>{tag,expected},"scalar load byte oracle h="+std::to_string(h)+" tag="+std::to_string(tag)+" actualtag="+std::to_string(responses[h].back().first)+" address="+std::to_string(address)+" expected="+std::to_string(expected)+" actual="+std::to_string(responses[h].back().second));}
};
void run(unsigned seed){
  Fixture f(seed);f.startup();f.warmup();
  for(unsigned n=0;n<16;++n)for(unsigned h=0;h<2;++h){const auto address=0x80020000ULL+h*4096+n*0x20000;const auto value=0x1367aaff00000000ULL^(std::uint64_t(h)<<32)^n;f.load(h,16+n,address,pattern(address));f.issue(h,1,40+n,address,value);f.expected.emplace(address,value);for(unsigned k=0;k<10;++k)f.core_step();}
  for(unsigned n=0;n<4000;++n)f.core_step();need(f.aw>0&&f.b==f.aw&&f.w==8*f.aw,"actual source dirty eviction AW/W/B ownership");need(f.service.ledger().idle(),"source backing not drained at external checkpoint");f.service.acknowledge_external_fence();
  unsigned written=0;for(const auto&[address,value]:f.expected)if(std::find(f.published_write_lines.begin(),f.published_write_lines.end(),address)!=f.published_write_lines.end()){++written;for(unsigned n=0;n<8;++n){auto actual=f.service.ledger().inspect(address+n);need(actual.known==255&&actual.value==std::uint8_t(value>>(8*n)),"actual accepted writeback all-byte golden");}}
  need(written>0,"no expected physical writeback data reached backing");need(!f.system.concretized_unknown_replay_timing(),"unknown RPQ timing after writes");
  std::cout<<"{\"seed\":"<<seed<<",\"actual_AXI_AR\":"<<f.ar<<",\"AW\":"<<f.aw<<",\"W\":"<<f.w<<",\"R\":"<<f.r<<",\"B\":"<<f.b<<",\"independently_matched_evicted_lines\":"<<written<<",\"master_ticks\":"<<f.tick<<",\"normal_native_CPU_execution\":false}\n";
}
}
int main(){try{for(unsigned seed:{1u,17u})run(seed);std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"source_physical_fixture_only\":true,\"full_FASED_host_bridge\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
