#include "rocket_dcache_arbiter.hpp"
#include "verilated.h"
#include <iostream>
#include <map>
#include <random>
#include <stdexcept>
#include <string>
using Peer=iris::frontend::SavedRocketDcacheArbiter;
static unsigned checks=0;
static void expect(bool value,const std::string&why){++checks;if(!value)throw std::runtime_error(why);}
static Peer::Bits known(unsigned width){Peer::Bits b;for(unsigned i=0;i<width;++i)b.limbs[i/64]|=uint64_t(1)<<(i%64);return b;}
int main(){try{
  VerilatedContext foreign;Verilated::threadContextp(&foreign);
  {
    Peer peer(17,16);expect(Verilated::threadContextp()==&foreign,"constructor caller context restoration");
    std::vector<Peer::Input> in(Peer::input_fields().size());std::map<std::string,unsigned> im,om;
    for(unsigned i=0;i<in.size();++i){im.emplace(Peer::input_fields()[i].name,i);in[i].known=known(Peer::input_fields()[i].width);}
    for(unsigned i=0;i<Peer::output_fields().size();++i)om.emplace(Peer::output_fields()[i].name,i);
    auto set=[&](const std::string&name,uint64_t value){in.at(im.at(name)).value=Peer::Bits(value);};
    auto wide=[&](const std::string&name,Peer::Bits value){in.at(im.at(name)).value=value;};
    auto evaluate=[&](){Verilated::threadContextp(&foreign);peer.evaluate(in);expect(Verilated::threadContextp()==&foreign,"evaluate caller context restoration");auto out=peer.sample();expect(Verilated::threadContextp()==&foreign,"sample caller context restoration");return out;};
    std::mt19937_64 rng(0x53ab);unsigned s1=2,s2=2;constexpr unsigned cycles=16384;
    for(unsigned i=0;i<cycles;++i){
      const unsigned valid=i&7,ready=(i>>3)&1,tag1=rng()&255,tag2=rng()&255,response_tag=i&255;
      const uint64_t addr0=rng()&((uint64_t(1)<<40)-1),addr1=rng()&((uint64_t(1)<<40)-1),addr2=rng()&((uint64_t(1)<<40)-1);
      const bool kill0=rng()&1,kill1=rng()&1,nack=rng()&1,response=rng()&1;Peer::Bits data1,data2,returned;
      for(unsigned n=0;n<4;++n){data1.limbs[n]=rng();data2.limbs[n]=rng();returned.limbs[n]=rng();}
      set("io_requestor_0_req_valid",bool(valid&1));set("io_requestor_1_req_valid",bool(valid&2));set("io_requestor_2_req_valid",bool(valid&4));set("io_mem_req_ready",ready);
      set("io_requestor_0_req_bits_addr",addr0);set("io_requestor_1_req_bits_addr",addr1);set("io_requestor_2_req_bits_addr",addr2);set("io_requestor_1_req_bits_tag",tag1);set("io_requestor_2_req_bits_tag",tag2);
      set("io_requestor_0_s1_kill",kill0);set("io_requestor_1_s1_kill",kill1);wide("io_requestor_1_s1_data_data",data1);wide("io_requestor_2_s1_data_data",data2);
      set("io_mem_s2_nack",nack);set("io_mem_resp_valid",response);set("io_mem_resp_bits_tag",response_tag);wide("io_mem_resp_bits_data",returned);
      const auto out=evaluate();auto get=[&](const std::string&name){return out.at(om.at(name)).limbs[0];};
      const unsigned selected=(valid&1)?0:(valid&2)?1:2;
      expect(get("io_mem_req_valid")==bool(valid),"request validity reduction");expect(get("io_mem_req_bits_addr")==((valid&1)?addr0:(valid&2)?addr1:addr2),"source request priority");
      expect(get("io_mem_req_bits_tag")==((valid&1)?0:((valid&2)?((tag1&63)<<2)|1:((tag2&63)<<2)|2)),"source tag append and exact eight-bit truncation");
      expect(get("io_requestor_0_req_ready")==ready,"PTW ready priority");expect(get("io_requestor_1_req_ready")==bool(ready&&!(valid&1)),"scalar ready priority");expect(get("io_requestor_2_req_ready")==bool(ready&&!(valid&3)),"vector ready priority");
      if(s1==1||s1==2)expect(out.at(om.at("io_mem_s1_data_data"))==(s1==1?data1:data2),"S1 owner follows source candidate even without fire");
      expect(get("io_mem_s1_kill")==bool(s1==0?kill0:s1==1?kill1:false),"S1 kill routed by source owner");
      for(unsigned client=0;client<3;++client){const auto prefix="io_requestor_"+std::to_string(client);
        expect(get(prefix+"_s2_nack")==bool(nack&&s2==client),"S2 nack has exact two-stage owner");
        expect(get(prefix+"_resp_valid")==bool(response&&(response_tag&3)==client),"response source tag demultiplex");
      }
      expect(get("io_requestor_1_resp_bits_tag")==response_tag>>2,"scalar response tag removed");expect(get("io_requestor_2_resp_bits_tag")==response_tag>>2,"vector response tag removed");
      expect(out.at(om.at("io_requestor_1_resp_bits_data"))==returned,"scalar full256b response transport");
      // A ready revision is combinational: it must not alter either ownership
      // register or any subsequent accepted physical transaction.
      set("io_mem_req_ready",!ready);evaluate();set("io_mem_req_ready",ready);expect(evaluate()==out,"same-edge revised-ready fixed-point stability");
      Verilated::threadContextp(&foreign);peer.commit();expect(Verilated::threadContextp()==&foreign,"commit caller context restoration");s2=s1;s1=selected;
    }
    unsigned refused=0;auto id=im.at("io_requestor_1_req_valid");evaluate();in[id].known.limbs[0]=0;
    try{peer.evaluate(in);}catch(const std::runtime_error&){++refused;}
    try{peer.commit();}catch(const std::logic_error&){++refused;}
    in[id].known=known(1);in[id].value=Peer::Bits(2);
    try{peer.evaluate(in);}catch(const std::invalid_argument&){++refused;}
    try{peer.sample();}catch(const std::logic_error&){++refused;}
    expect(refused==4,"unknown/width refusal invalidates stale phases");expect(Verilated::threadContextp()==&foreign,"error caller context restoration");
    std::cout<<"{\"status\":\"passed_source_Rocket_Dcache_arbiter\",\"cycles\":"<<cycles<<",\"checks\":"<<checks<<",\"input_fields\":"<<in.size()<<",\"output_fields\":"<<om.size()<<",\"phase_refusals\":"<<refused<<",\"source_state_injected\":false}\n";
  }
  expect(Verilated::threadContextp()==&foreign,"destructor caller context restoration");return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
