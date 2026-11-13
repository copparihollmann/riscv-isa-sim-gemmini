#include "axi_functional_fixture.hpp"
#include <iostream>
#include <map>
#include <stdexcept>
using Fixture=iris::frontend::AxiFunctionalFixture;
static unsigned checks=0,refusals=0;
static void check(bool yes,const char*why){++checks;if(!yes)throw std::runtime_error(why);}
template<class F>static void reject(F call){try{call();}catch(const std::runtime_error&){++refusals;return;}throw std::runtime_error("missing functional AXI guard");}
struct Memory {
  std::map<uint64_t,uint8_t>bytes;bool unknown=false;unsigned writes=0;
  Memory(){for(unsigned n=0;n<4096;++n)bytes[0x80000000+n]=uint8_t(n*73+19);}
  Fixture::Word read(uint64_t address,unsigned size){Fixture::Word result;for(unsigned i=0;i<size;++i){result.value|=uint64_t(bytes.at(address+i))<<(i*8);result.known|=uint64_t(255)<<(i*8);}if(unknown)result.known&=~uint64_t(1);return result;}
  void write(uint64_t address,unsigned size,uint64_t data,unsigned strobe){++writes;for(unsigned i=0;i<size;++i)if(strobe&(1u<<i))bytes.at(address+i)=data>>(i*8);}
  Fixture model(){return Fixture(16,16,[this](auto a,auto b){return read(a,b);},[this](auto a,auto b,auto c,auto d){write(a,b,c,d);});}
};
int main(){try{
  Memory memory;auto fixture=memory.model();const auto snapshot=memory.read(0x80000000,8).value;
  fixture.accept_ar({0x80000000,3,7,3});
  // The physical fixture snapshot must survive later host backing mutation;
  // release-time lookup would silently observe this new value.
  memory.write(0x80000000,8,0x1111222233334444ULL,255);
  reject([&]{fixture.accept_aw({0x80000000,4,7,3});});
  reject([&]{fixture.request_read_egress(4);});fixture.request_read_egress(3);
  check(fixture.read_payload()->data==snapshot,"read keeps AR-time snapshot rather than later mutable backing");
  for(unsigned beat=0;beat<8;++beat){auto value=fixture.read_payload();check(value&&value->id==3&&value->last==(beat==7),"read FIFO owns every R beat/last/ID");fixture.consume_r();}
  check(fixture.idle(),"read owner is released only at final R");reject([&]{fixture.consume_r();});
  fixture.accept_aw({0x80000040,7,1,3});fixture.accept_w(0x9988776655443322ULL,0x55,false);fixture.accept_w(0x1122334455667788ULL,0xaa,true);
  auto expected0=memory.read(0x80000040,8).value,expected1=memory.read(0x80000048,8).value;
  for(unsigned b=0;b<8;++b){if((0x55>>b)&1)check(((expected0>>(8*b))&255)==((0x9988776655443322ULL>>(8*b))&255),"first byte strobes preserved");if((0xaa>>b)&1)check(((expected1>>(8*b))&255)==((0x1122334455667788ULL>>(8*b))&255),"second byte strobes preserved");}
  reject([&]{fixture.accept_ar({0x80000040,2,1,3});});fixture.request_write_egress(7);check(fixture.write_payload()==7,"B ownership matches AW ID");fixture.consume_b();check(fixture.idle(),"write owner released only at B");
  // AXI channels are independent: complete W may precede AW. Data is
  // retained without a guessed address and cannot alter memory until owned.
  const auto before=memory.writes;fixture.accept_w(0xaabbccddeeff0011ULL,255,true);check(memory.writes==before,"unowned W cannot modify backing");reject([&]{fixture.accept_ar({0x80000080,1,0,3});});fixture.accept_aw({0x80000080,8,0,3});check(memory.read(0x80000080,8).value==0xaabbccddeeff0011ULL,"later AW binds buffered W burst");fixture.request_write_egress(8);fixture.consume_b();
  fixture.accept_ar({0x80000080,8,0,3});fixture.request_read_egress(8);check(fixture.read_payload()->data==0xaabbccddeeff0011ULL,"completed nonconflicting write is visible to later read");fixture.consume_r();
  fixture.accept_ar({0x80000100,1,0,3});fixture.accept_aw({0x80000200,2,0,3});fixture.accept_w(37,255,true);check(fixture.read_count()==1&&fixture.write_count()==1,"nonoverlapping read/write channels may overlap");fixture.request_write_egress(2);fixture.consume_b();fixture.request_read_egress(1);fixture.consume_r();
  memory.unknown=true;reject([&]{fixture.accept_ar({0x80000000,1,0,3});});check(fixture.read_count()==0,"undefined snapshot refuses without enqueuing read owner");memory.unknown=false;
  for(auto bad:{Fixture::Request{0x80000000,16,0,3},Fixture::Request{0x80000000,1,8,3},Fixture::Request{0x80000001,1,0,3},Fixture::Request{0x80000ff8,1,1,3}})reject([&]{fixture.accept_ar(bad);});
  reject([&]{fixture.accept_w(0,1,true,0);});
  for(unsigned iteration=0;iteration<10000;++iteration){const auto address=0x80000300+(iteration%128)*8;fixture.accept_ar({address,iteration%16,0,3});fixture.request_read_egress(iteration%16);check(fixture.read_payload()->data==memory.read(address,8).value,"bounded streaming snapshots preserve independent byte model");fixture.consume_r();}
  check(fixture.idle(),"streaming actor retains no retired owner history");
  std::cout<<"{\"status\":\"passed_owned_AR_snapshots_AW_W_and_conflict_guards\",\"checks\":"<<checks<<",\"guard_refusals\":"<<refusals<<",\"streaming_requests\":10000,\"timing_added\":false,\"full_FASED_functional_bridge\":false}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
