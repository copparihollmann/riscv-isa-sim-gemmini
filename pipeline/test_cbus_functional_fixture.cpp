#include "cbus_functional_fixture.hpp"
#include <iostream>
#include <map>
using namespace iris::frontend;
int main(){try{
  using Bits=iris::fabric::Bits;using Input=iris::fabric::Input;
  std::map<std::string,unsigned>in,out;
  auto index=[](auto&map,const std::string&component,const std::string&name){const auto key=component+":"+name;auto it=map.find(key);if(it==map.end())it=map.emplace(key,map.size()).first;return it->second;};
  unsigned reads=0,writes=0,checks=0;uint64_t value=0,mask=0;
  CbusFunctionalFixture actor([&](auto c,auto n){return index(in,c,n);},[&](auto c,auto n){return index(out,c,n);},3,2,[&](uint64_t a,unsigned b){++reads;if(b!=8)throw std::runtime_error("read width");return a^0x5555000000000000ULL;},[&](uint64_t a,unsigned b,uint64_t d,uint64_t m){if(a!=0x10020000||b!=8)throw std::runtime_error("write ownership");++writes;value=d;mask=m;});
  std::vector<Input>inputs(in.size());std::vector<Bits>outputs(out.size());
  auto oi=[&](const std::string&n){return out.at("noc:_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_"+n);};auto ii=[&](const std::string&n){return in.at("noc:_cbus_auto_bus_xing_in_"+n);};
  auto need=[&](bool test){++checks;if(!test)throw std::runtime_error("CBUS fixture assertion");};
  outputs[oi("a_valid")]=Bits(1);outputs[oi("a_bits_opcode")]=Bits(4);outputs[oi("a_bits_size")]=Bits(6);outputs[oi("a_bits_source")]=Bits(7);outputs[oi("a_bits_address")]=Bits(0x10000);outputs[oi("d_ready")]=Bits(1);
  for(unsigned edge=0;edge<20;++edge){actor.drive(inputs,edge);actor.drive(inputs,edge);if(edge<3)need(!inputs[ii("d_valid")].value.limbs[0]);if(edge>=3&&edge<=17&&edge%2==1){need(inputs[ii("d_valid")].value.limbs[0]==1);need(inputs[ii("d_bits_source")].value.limbs[0]==7);need(inputs[ii("d_bits_data")].value.limbs[0]==((0x10000ULL+8*((edge-3)/2))^0x5555000000000000ULL));}actor.observe(outputs,edge);outputs[oi("a_valid")]=Bits(0);}
  need(reads==8&&actor.transactions().size()==1&&actor.transactions()[0].finished==17);
  // Backpressure holds the response and its ownership without repeating IO.
  outputs[oi("a_valid")]=Bits(1);outputs[oi("a_bits_opcode")]=Bits(1);outputs[oi("a_bits_size")]=Bits(0);outputs[oi("a_bits_source")]=Bits(9);outputs[oi("a_bits_address")]=Bits(0x10020000);outputs[oi("a_bits_data")]=Bits(0x72);outputs[oi("a_bits_mask")]=Bits(1);outputs[oi("d_ready")]=Bits(0);
  for(unsigned edge=20;edge<30;++edge){actor.drive(inputs,edge);if(edge>=23)need(inputs[ii("d_valid")].value.limbs[0]==1&&inputs[ii("d_bits_source")].value.limbs[0]==9);actor.observe(outputs,edge);outputs[oi("a_valid")]=Bits(0);}need(writes==1&&value==0x72&&mask==1&&!actor.transactions()[1].finished);
  outputs[oi("d_ready")]=Bits(1);actor.drive(inputs,30);actor.observe(outputs,30);need(actor.transactions()[1].finished==30&&actor.completed_on_last_edge()==std::vector<size_t>{1});
  unsigned refused=0;try{actor.observe(outputs,30);}catch(const std::logic_error&){++refused;}actor.drive(inputs,31);try{actor.drive(inputs,32);}catch(const std::logic_error&){++refused;}need(refused==2);
  std::cout<<"{\"status\":\"passed_explicit_CBUS_snapshot_beats_and_backpressure\",\"checks\":"<<checks<<",\"refusals\":"<<refused<<"}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
