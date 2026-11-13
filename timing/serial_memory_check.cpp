#include "serial_memory.hpp"
#include "fased_service.hpp"
#include "verilated.h"
#include <array>
#include <deque>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
namespace S=iris::serial_memory;
namespace F=iris::fased;
namespace {
std::uint64_t checks=0;
bool corrupt_data=false,invalid_opcode=false,source_always=false;
void need(bool value,const std::string&text){++checks;if(!value)throw std::runtime_error(text);}
std::uint64_t mask(unsigned n){return n==64?~std::uint64_t(0):(std::uint64_t(1)<<n)-1;}
std::uint64_t initial(std::uint64_t address){return(address*0x9e3779b97f4a7c15ULL)^(address>>5)^0x41a39f7586bc20deULL;}
struct AXI {std::uint64_t address;unsigned id,len,size;};
struct WBeat {std::uint64_t data;unsigned strobe;};
struct Bridge {
  VerilatedContext foreign;
  S::Model serial;
  F::Model fased;
  std::map<std::string,unsigned> si,so,fi,fo;
  std::vector<S::Bits> sin;
  std::vector<F::Bits> fin;
  std::vector<std::uint64_t> sout,fout;
  std::uint64_t tick=0,ar_count=0,aw_count=0,r_count=0,w_count=0,settles=0;
  bool reset=true;
  std::deque<AXI> read_owners,write_owners,aw;
  std::deque<std::vector<WBeat>> completed_w;
  std::vector<WBeat> partial_w;
  std::optional<AXI> active_read,active_write;
  unsigned rbeat=0;
  std::map<std::uint64_t,std::uint64_t> memory;
  explicit Bridge(unsigned seed):serial(seed,{"serial-memory-check","+tilelink_timeout=0"},source_always?S::AssertionPolicy::SourceAlways:S::AssertionPolicy::SuppressOnlyWhileBothExternalResets),fased({30,30,16,16},seed+7,{"serial-memory-check"}){
    for(auto f:serial.input_fields()){si[f.name]=sin.size();sin.push_back({0,mask(f.width)});}for(auto f:serial.output_fields())so[f.name]=so.size();
    for(auto f:fased.input_fields()){fi[f.name]=fin.size();fin.push_back({0,mask(f.width)});}for(auto f:fased.output_fields())fo[f.name]=fo.size();
    for(unsigned i=0;i<220;++i){evaluate();commit();}reset=false;
  }
  void set(const std::string&name,std::uint64_t value){sin.at(si.at(name)).value=value;}
  void fs(const std::string&name,std::uint64_t value){fin.at(fi.at("tNasti_io_"+name)).value=value;}
  std::uint64_t get(const std::string&name)const{return sout.at(so.at(name));}
  std::uint64_t fg(const std::string&name)const{return fout.at(fo.at("tNasti_io_"+name));}
  std::uint64_t load(std::uint64_t a)const{auto found=memory.find(a);return found==memory.end()?initial(a):found->second;}
  void evaluate(){
    set("iris_reset",reset);set("bringup_reset",reset);set("iris_pad_reset_io",reset);
    fin[fi.at("reset")].value=reset;
    fs("egressResp_rBits_data",active_read?(load(active_read->address+(std::uint64_t(rbeat)<<active_read->size))^(corrupt_data?1:0)):0);
    fs("egressResp_rBits_last",active_read&&rbeat==active_read->len);fs("egressResp_rBits_id",active_read?active_read->id:0);fs("egressResp_bBits_id",active_write?active_write->id:0);
    for(unsigned iteration=0;iteration<32;++iteration){
      Verilated::threadContextp(&foreign);fased.evaluate(fin);need(Verilated::threadContextp()==&foreign,"FASED context not restored");auto next_f=fased.sample();
      auto old_s=sout;fout=std::move(next_f);
      for(auto p:std::array<std::pair<const char*,const char*>,9>{{{"aw_ready","tNasti_aw_ready"},{"w_ready","tNasti_w_ready"},{"ar_ready","tNasti_ar_ready"},{"b_valid","tNasti_b_valid"},{"b_bits_id","tNasti_b_bits_id"},{"r_valid","tNasti_r_valid"},{"r_bits_id","tNasti_r_bits_id"},{"r_bits_data","tNasti_r_bits_data"},{"r_bits_last","tNasti_r_bits_last"}}})set("fased_axi4_mem_0_bits_"+std::string(p.first),fg(p.second));
      serial.evaluate(sin);need(Verilated::threadContextp()==&foreign,"SerialTL context not restored");sout=serial.sample();
      bool changed=false;
      for(auto p:std::array<std::pair<const char*,const char*>,11>{{{"aw_valid","tNasti_aw_valid"},{"aw_bits_id","tNasti_aw_bits_id"},{"aw_bits_len","tNasti_aw_bits_len"},{"aw_bits_burst","tNasti_aw_bits_burst"},{"w_valid","tNasti_w_valid"},{"w_bits_last","tNasti_w_bits_last"},{"ar_valid","tNasti_ar_valid"},{"ar_bits_id","tNasti_ar_bits_id"},{"ar_bits_len","tNasti_ar_bits_len"},{"ar_bits_burst","tNasti_ar_bits_burst"},{"r_ready","tNasti_r_ready"}}}){
        auto name="tNasti_io_"+std::string(p.second);auto value=reset?0:get("fased_axi4_mem_0_bits_"+std::string(p.first));changed|=fin[fi.at(name)].value!=value;fin[fi.at(name)].value=value;
      }
      auto b=get("fased_axi4_mem_0_bits_b_ready");changed|=fin[fi.at("tNasti_io_tNasti_b_ready")].value!=b;fs("tNasti_b_ready",b);
      ++settles;
      if(!changed&&old_s==sout)return;
    }
    throw std::runtime_error("source combinational fixed point did not settle");
  }
  AXI request(const char*ch)const{std::string p="fased_axi4_mem_0_bits_"+std::string(ch)+"_bits_";return{get(p+"addr"),unsigned(get(p+"id")),unsigned(get(p+"len")),unsigned(get(p+"size"))};}
  void commit(){
    bool iris=tick%2==0,ser=tick%10==0;
    if(!reset){
      need(!get("iris_serial_auto_serdesser_client_out_a_valid"),"IRIS_SERIAL_MEMORY_EXTERNAL_REVERSE_CLIENT_REQUIRED");
      if(get("fased_axi4_mem_0_bits_ar_valid")&&fg("tNasti_ar_ready")){auto r=request("ar");need(r.len==7&&r.size==3,"unexpected source read shape");read_owners.push_back(r);++ar_count;}
      if(get("fased_axi4_mem_0_bits_aw_valid")&&fg("tNasti_aw_ready")){auto r=request("aw");need(r.len==7&&r.size==3,"unexpected source write shape");write_owners.push_back(r);aw.push_back(r);++aw_count;}
      if(get("fased_axi4_mem_0_bits_w_valid")&&fg("tNasti_w_ready")){
        partial_w.push_back({get("fased_axi4_mem_0_bits_w_bits_data"),unsigned(get("fased_axi4_mem_0_bits_w_bits_strb"))});++w_count;
        if(get("fased_axi4_mem_0_bits_w_bits_last")){completed_w.push_back(partial_w);partial_w.clear();}
      }
      while(!aw.empty()&&!completed_w.empty()){
        auto r=aw.front();aw.pop_front();auto data=completed_w.front();completed_w.pop_front();need(data.size()==r.len+1,"AXI write burst ownership/length mismatch");
        for(unsigned i=0;i<data.size();++i){auto address=r.address+(std::uint64_t(i)<<r.size);auto value=load(address);for(unsigned b=0;b<8;++b)if(data[i].strobe&(1U<<b)){auto m=std::uint64_t(255)<<(8*b);value=(value&~m)|(data[i].data&m);}memory[address]=value;}
      }
      need(bool(active_read)==bool(fg("tNasti_r_valid")),"functional read egress ownership disagrees with timing cut");need(bool(active_write)==bool(fg("tNasti_b_valid")),"functional write egress ownership disagrees with timing cut");
      if(active_read&&get("fased_axi4_mem_0_bits_r_ready")){++r_count;if(rbeat==active_read->len){active_read.reset();rbeat=0;}else ++rbeat;}
      if(active_write&&get("fased_axi4_mem_0_bits_b_ready"))active_write.reset();
      if(fg("egressReq_r_valid")){need(!read_owners.empty(),"unowned read egress request");need(read_owners.front().id==fg("egressReq_r_bits"),"read egress changed FIFO ID");active_read=read_owners.front();read_owners.pop_front();rbeat=0;}
      if(fg("egressReq_b_valid")){need(!write_owners.empty(),"unowned write egress request");need(write_owners.front().id==fg("egressReq_b_bits"),"write egress changed FIFO ID");active_write=write_owners.front();write_owners.pop_front();}
    }
    // Both components commit the same settled pre-edge inputs. The explicit
    // functional fixture ledger above supplies data only on the next phase.
    serial.commit({iris,true,ser});fased.commit();++tick;
  }
};
struct Packet {std::uint64_t address;unsigned source,beat=0;};
std::string bank(unsigned i){return"iris_mbus_auto_bus_xing_in_"+std::to_string(i)+"_";}
void batch(Bridge&b,bool write,unsigned per_bank,std::uint64_t round){
  std::array<std::deque<Packet>,4> pending;std::map<std::pair<unsigned,unsigned>,Packet> outstanding;unsigned done=0;
  for(unsigned k=0;k<4;++k)for(unsigned n=0;n<per_bank;++n)pending[k].push_back({0x80000000ULL+round*0x1000+k*64+n*256,n});
  auto begin=b.tick;
  for(unsigned cycle=0;cycle<30000;++cycle){
    for(unsigned k=0;k<4;++k){auto p=bank(k);bool valid=!pending[k].empty();b.set(p+"a_valid",valid);b.set(p+"d_ready",cycle>100&&cycle%7!=0);
      if(valid){auto&r=pending[k].front();b.set(p+"a_bits_opcode",invalid_opcode?7:(write?0:4));b.set(p+"a_bits_param",0);b.set(p+"a_bits_size",6);b.set(p+"a_bits_source",r.source);b.set(p+"a_bits_address",r.address);b.set(p+"a_bits_mask",255);b.set(p+"a_bits_data",write?(initial(r.address+r.beat*8)^0x123456789abcdef0ULL):0);b.set(p+"a_bits_corrupt",0);}
    }
    b.evaluate();
    if(b.tick%2==0)for(unsigned k=0;k<4;++k){auto p=bank(k);
      if(!pending[k].empty()&&b.get(p+"a_ready")){auto r=pending[k].front();if(!write||r.beat==0){need(!outstanding.count({k,r.source}),"producer reused live TL source");outstanding[{k,r.source}]=r;}if(!write||++pending[k].front().beat==8)pending[k].pop_front();}
      if(b.get(p+"d_valid")&&cycle>100&&cycle%7!=0){unsigned source=b.get(p+"d_bits_source");auto it=outstanding.find({k,source});need(it!=outstanding.end(),"unowned post-cork D response");auto&r=it->second;
        need(b.get(p+"d_bits_opcode")==unsigned(write?0:1),"TL response opcode mismatch");need(b.get(p+"d_bits_size")==6,"TL response size changed");need(!b.get(p+"d_bits_denied")&&!b.get(p+"d_bits_corrupt"),"unexpected TL error");
        if(!write){auto expected=initial(r.address+r.beat*8);if(round&1)expected^=0x123456789abcdef0ULL;need(b.get(p+"d_bits_data")==expected,"transport value or byte address changed");}
        if(write||++r.beat==8){outstanding.erase(it);++done;}
      }
    }
    b.commit();
    if(done==4*per_bank){for(unsigned k=0;k<4;++k)b.set(bank(k)+"a_valid",0);std::cout<<"{\"case\":\""<<(write?"write":"read")<<"\",\"round\":"<<round<<",\"transactions\":"<<done<<",\"source_virtual_ticks\":"<<(b.tick-begin)<<"}\n";return;}
  }
  throw std::runtime_error("transport did not complete; done="+std::to_string(done)+" AR="+std::to_string(b.ar_count)+" AW="+std::to_string(b.aw_count)+" R="+std::to_string(b.r_count)+" W="+std::to_string(b.w_count));
}
void typed_guards(){
  VerilatedContext foreign;Verilated::threadContextp(&foreign);
  S::Model model(7,{"typed-guards"},S::AssertionPolicy::SuppressOnlyWhileBothExternalResets);
  std::map<std::string,unsigned> index;std::vector<S::Bits> in;
  for(auto f:model.input_fields()){index[f.name]=in.size();in.push_back({0,mask(f.width)});}
  auto rejected=[&](auto fn,const char*message){bool caught=false;try{fn();}catch(const std::exception&){caught=true;}need(caught,message);need(Verilated::threadContextp()==&foreign,"exception leaked model context");};
  rejected([&]{model.evaluate(in);},"unreset active input accepted");rejected([&]{model.commit({true,true,true});},"commit without evaluation accepted");
  in[index.at("iris_reset")].value=in[index.at("bringup_reset")].value=1;
  model.evaluate(in);rejected([&]{model.commit({false,false,false});},"empty clock set accepted");model.commit({true,false,false});
  in[index.at("iris_reset")].value=in[index.at("bringup_reset")].value=0;
  rejected([&]{model.evaluate(in);},"missing Bringup/Serial reset edges accepted");
  in[index.at("iris_reset")].value=in[index.at("bringup_reset")].value=1;
  model.evaluate(in);model.commit({true,true,true});
  for(unsigned i=0;i<in.size();++i){auto bad=in;bad[i].known&=~std::uint64_t(1);rejected([&]{model.evaluate(bad);},"unknown external physical input accepted");}
  auto bad=in;bad[index.at("iris_mbus_auto_bus_xing_in_0_a_bits_address")].value=std::uint64_t(1)<<33;rejected([&]{model.evaluate(bad);},"physical address truncation accepted");
  rejected([&]{model.sample();},"failed evaluate left a current sample");rejected([&]{model.commit({true,true,true});},"failed evaluate left an eligible commit");
  model.evaluate(in);auto once=model.sample();model.evaluate(in);need(once==model.sample(),"repeat evaluate advanced source state");model.commit({true,true,true});rejected([&]{model.sample();},"stale sample accepted");
  std::cout<<"{\"status\":\"passed_typed_guards\",\"checks\":"<<checks<<",\"physical_inputs\":"<<in.size()<<"}\n";
}
}
int main(int argc,char**argv){try{
  if(argc==2){std::string arg(argv[1]);if(arg=="--typed-guards"){typed_guards();return 0;}corrupt_data=arg=="--wrong-data";invalid_opcode=arg=="--invalid-opcode";source_always=arg=="--source-always";}
  for(unsigned seed:{1U,17U}){Bridge b(seed);batch(b,false,1,0);batch(b,false,4,0);batch(b,true,4,1);batch(b,false,4,1);need(b.ar_count==36&&b.aw_count==16&&b.r_count==288&&b.w_count==128,"boundary request/beat conservation mismatch");std::cout<<"{\"seed\":"<<seed<<",\"virtual_ticks\":"<<b.tick<<",\"fixed_point_evaluations\":"<<b.settles<<",\"AR\":"<<b.ar_count<<",\"AW\":"<<b.aw_count<<",\"R\":"<<b.r_count<<",\"W\":"<<b.w_count<<"}\n";}
  std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"external_AXI_data_fixture\":true,\"FASED_parameters\":\"explicit synthetic30/30/16/16\",\"hardware_contacted\":false,\"calibration_usable\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
