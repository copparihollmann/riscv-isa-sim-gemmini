#include "fast_rocket_packets.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
using Flow=iris::frontend::FastRocketPackets;
static unsigned checks=0,refusals=0;
static void require(bool b){if(!b)throw std::runtime_error("packet flow guard assertion");++checks;}
template<class F>static void rejects(const char*message,F f){try{f();}catch(const std::exception&e){if(std::string(e.what()).find(message)==std::string::npos)throw;++checks;++refusals;return;}throw std::runtime_error(std::string("missing refusal: ")+message);}
int main(){
 const auto read=[](uint64_t){return Flow::Word{0x00010001,0xffffffffu};};
 const auto seq=[](uint64_t pc,uint32_t,unsigned n){return pc+n;};
 rejects("CLOCK_RESET",[]{Flow f(0,0x1000);});
 rejects("CLOCK_RESET",[]{Flow f(1,0x1001);});
 rejects("CLOCK_RESET",[]{Flow f(1,1ull<<40);});
 rejects("WITHOUT_READY",[]{Flow f(1,0x1000);f.consume(0);});
 rejects("REQUEST_SCOPE",[&]{Flow f(2,0x1000);f.prepare(1,0x1000,1,2,read,seq);});
 rejects("REQUEST_SCOPE",[&]{Flow f(1,0x1000);f.prepare(0,0x1001,1,2,read,seq);});
 rejects("REQUEST_SCOPE",[&]{Flow f(1,0x1000);f.prepare(0,0x1000,1,6,read,seq);});
 rejects("REQUEST_SCOPE",[&]{Flow f(1,0x1000);f.prepare(0,0x1000,1,2,{},seq);});
 rejects("UNKNOWN_FETCH",[&]{Flow f(1,0x1000);f.prepare(0,0x1000,1,2,[](uint64_t){return Flow::Word{1,0xffff};},seq);});
 rejects("HEAD_MISMATCH",[&]{Flow f(1,0x1000);f.prepare(0,0x1000,5,2,read,seq);});
 rejects("SOURCE_REQUIRED",[]{Flow f(1,0x1000);f.redirect(0,0x1000,"");});
 rejects("SOURCE_REQUIRED",[]{Flow f(1,0x1000);f.redirect(0,0x1001,"test-redirect");});
 rejects("WRONG_EDGE",[&]{Flow f(1,0x1000);f.prepare(0,0x1000,1,2,read,seq);f.finish(1);});
 rejects("UNCOMMITTED_EDGE",[&]{Flow f(1,0x1000);f.prepare(0,0x1000,1,2,read,seq);f.prepare(1,0x1000,1,2,read,seq);});
 rejects("MULTIPLE_HEADS",[&]{Flow f(1,0x1000);f.prepare(0,0x1000,1,2,read,seq);f.prepare(0,0x1002,1,2,read,seq);});
 {
  unsigned reads=0,predictions=0;Flow f(1,0x1000);
  auto r=[&](uint64_t a){++reads;require(a==0x1000||a==0x1004);return read(a);};
  auto p=[&](uint64_t a,uint32_t x,unsigned n){++predictions;return seq(a,x,n);};
  for(unsigned i=0;i<20;++i)require(f.prepare(0,0x1000,1,2,r,p));
  require(reads==1&&predictions==2);f.consume(0);
  rejects("WITHOUT_READY",[&]{f.consume(0);});
  require(!f.prepare(0,0x1000,1,2,r,p));auto e=f.finish(0);
  require(e&&e->word&&e->word->id==1&&e->instruction&&e->instruction->words==std::vector<uint64_t>{1});
  require(!f.finish(0));require(!f.prepare(0,0x1002,1,2,r,p));
  require(f.prepare(1,0x1002,1,2,r,p));f.consume(1);e=f.finish(1);
  require(e&&!e->word&&e->instruction&&e->instruction->words==std::vector<uint64_t>{1});require(reads==1);
  require(f.prepare(2,0x1004,1,2,r,p));f.consume(2);e=f.finish(2);
  require(e&&e->word&&e->word->id==2&&e->instruction);require(reads==2);
  rejects("CLOCK_REVERSED",[&]{f.prepare(1,0x1006,1,2,r,p);});
 }
 {
  Flow f(1,0x1002);const auto r=[](uint64_t a){return Flow::Word{a==0x1000?0x80930001u:0x00010010u,0xffffffffu};};
  require(!f.prepare(0,0x1002,0x00108093,4,r,seq));auto e=f.finish(0);
  require(e&&e->word&&e->partial&&!e->instruction&&e->word->id==1);
  require(f.next_edge()==1);require(f.prepare(1,0x1002,0x00108093,4,r,seq));f.consume(1);e=f.finish(1);
  require(e&&e->word&&e->instruction&&e->instruction->words==std::vector<uint64_t>({1,2}));
  require(e->instruction->raw==0x00108093&&e->instruction->bytes==4);
 }
 {
  Flow f(1,0x1002);auto r=[](uint64_t a){return Flow::Word{a==0x1000?0x80930001u:0x00010001u,0xffffffffu};};
  require(!f.prepare(0,0x1002,0x00108093,4,r,seq));auto e=f.finish(0);require(e&&e->word);
  f.redirect(1,0x2000,"actual-MEM-redirect",2);require(!f.prepare(1,0x1002,0x00108093,4,r,seq));e=f.finish(1);
  require(e&&e->kill&&!e->word&&!e->instruction&&e->reason=="actual-MEM-redirect");
  require(f.prepare(2,0x2000,1,2,r,seq));f.consume(2);e=f.finish(2);
  require(e&&e->instruction&&e->instruction->pc==0x2000&&e->instruction->words==std::vector<uint64_t>{2});
 }
 {
  Flow f(1,0x1000);f.redirect(0,0x2000,"higher-priority",3);f.redirect(0,0x3000,"lower-priority",1);auto e=f.finish(0);
  require(e&&e->reason=="higher-priority");require(f.prepare(1,0x2000,1,2,read,seq));f.consume(1);e=f.finish(1);require(e&&e->instruction&&e->instruction->pc==0x2000);
 }
 std::cout<<"PASS checks="<<checks<<" refusals="<<refusals<<'\n';
}
