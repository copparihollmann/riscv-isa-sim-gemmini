#include "fased_backing_ledger_v1.hpp"
#include <functional>
#include <iostream>
#include <random>
#include <string>
using namespace iris::fased_backing;
namespace {
unsigned long checks=0,refusals=0;
void need(bool v,const char*m){++checks;if(!v)throw std::runtime_error(m);}
void reject(const std::function<void()>&f,const char*match){try{f();}catch(const std::exception&e){need(std::string(e.what()).find(match)!=std::string::npos,"wrong typed refusal");++refusals;return;}throw std::runtime_error(std::string("accepted corruption: ")+match);}
constexpr std::uint64_t base=0x80010000;
Ledger fresh(){return Ledger({{base,16384}},16,16,Visibility::ExternalFencedDisjoint);}
void step(Ledger&l,Step s={}){l.advance(l.committed_edges(),s);}
void full_bytes(){
  auto l=fresh();std::vector<Byte>initial(16384);for(unsigned i=0;i<initial.size();++i)initial[i]={std::uint8_t((i*13+7)^0x95),255};l.initialize(base,initial);auto expected=initial;
  std::mt19937 rng(17);
  for(unsigned n=0;n<1000;++n){
    const auto address=base+64*(rng()%256);const unsigned len=rng()%8,id=rng()%16;std::vector<WBeat>w;
    for(unsigned b=0;b<=len;++b){const auto data=std::uint64_t(rng())|(std::uint64_t(rng())<<32);const unsigned strobe=rng()%256;w.push_back(WBeat::concrete(data,strobe,b==len));
      for(unsigned j=0;j<8;++j)if(strobe&(1u<<j))expected[address-base+8*b+j]={std::uint8_t(data>>(8*j)),255};}
    if(n%2){for(auto b:w)step(l,Step{.w=b});step(l,Step{.aw=Request::concrete(address,id,len)});}
    else {step(l,Step{.aw=Request::concrete(address,id,len)});for(auto b:w)step(l,Step{.w=b});}
    step(l,Step{.write_egress=known(4,id)});need(l.write_payload()==id,"B owner ID");
    const auto before=l.inspect(address);for(unsigned b=0;b<3;++b){step(l);need(l.write_payload()==id,"B backpressure owner changed");need(l.inspect(address).value==before.value,"write visible before B acceptance");}
    step(l,Step{.b_fire=true});need(l.idle(),"write owner not released");
    reject([&]{step(l,Step{.ar=Request::concrete(address,id,len)});},"EXTERNAL_FENCE_REQUIRED");l.acknowledge_external_fence();
    step(l,Step{.ar=Request::concrete(address,id,len)});step(l,Step{.read_egress=known(4,id)});
    for(unsigned b=0;b<=len;++b){auto p=l.read_payload();need(p&&p->id==id&&p->known==~std::uint64_t(0)&&p->last==(b==len),"R owner/last");std::uint64_t word=0;for(unsigned j=0;j<8;++j)word|=std::uint64_t(expected[address-base+b*8+j].value)<<(8*j);need(p->data==word,"independent full-word memory value");
      step(l);need(l.read_payload()->data==word,"R payload changed under backpressure");step(l,Step{.r_fire=true});}
    need(l.idle(),"read owner not released");
  }
  for(unsigned i=0;i<initial.size();++i){const auto b=l.inspect(base+i);need(b.value==expected[i].value&&b.known==expected[i].known,"all independent backing bytes");}
}
void guards(){
  reject([]{Ledger l({},16,16,Visibility::ExternalFencedDisjoint);},"EXPLICIT_DOMAIN_REQUIRED");
  reject([]{Ledger l({{base,8},{base+4,8}},16,16,Visibility::ExternalFencedDisjoint);},"INVALID_OR_OVERLAPPING_DOMAINS");
  reject([]{Ledger l({{base,64}},0,16,Visibility::ExternalFencedDisjoint);},"EXPLICIT_CAPACITY_ENVELOPE");
  {auto l=fresh();reject([&]{step(l,Step{.ar=Request::concrete(base,0,0)});},"UNDEFINED_READ_BYTES");need(l.idle()&&l.committed_edges()==0,"failed read mutated ownership");}
  {auto l=fresh();for(auto r:std::vector<Request>{Request::concrete(base,16,0),Request::concrete(std::uint64_t(1)<<33,0,0)})reject([&]{step(l,Step{.aw=r});},"EXCESS_FIELD_WIDTH");}
  {auto l=fresh();for(auto r:std::vector<Request>{Request::concrete(base,0,8),Request::concrete(base,0,0,2),Request::concrete(base,0,0,3,2),Request::concrete(base,0,0,3,1,true),Request::concrete(base+1,0,0)})reject([&]{step(l,Step{.aw=r});},"FULL64_INCR_SCOPE");}
  {auto l=fresh();reject([&]{step(l,Step{.aw=Request::concrete(base+16384,0,0)});},"UNMAPPED_BYTES");reject([&]{step(l,Step{.aw=Request::concrete(base+4096-8,0,1)});},"4K_CROSSING");}
  {auto l=fresh();auto r=Request::concrete(base,0,0);r.address.known^=1;reject([&]{step(l,Step{.aw=r});},"UNKNOWN_REQUIRED_FIELD");}
  {auto l=fresh();auto w=WBeat::concrete(0,1,true);w.data.known&=~255ull;reject([&]{step(l,Step{.w=w});},"UNKNOWN_STROBED_BYTE");need(l.idle(),"failed unknown data reserved W");w.strobe=known(8,0);step(l,Step{.w=w});need(!l.idle(),"legal unstrobed unknown byte rejected");}
  {auto l=fresh();step(l,Step{.aw=Request::concrete(base,0,1)});const auto edge=l.committed_edges();reject([&]{step(l,Step{.w=WBeat::concrete(1,255,true)});},"AWLEN_WLAST_MISMATCH");need(l.committed_edges()==edge&&l.write_count()==1,"bad WLAST mutated state");step(l,Step{.w=WBeat::concrete(2,255,false)});step(l,Step{.w=WBeat::concrete(3,255,true)});step(l,Step{.write_egress=known(4,0)});step(l,Step{.b_fire=true});}
  {auto l=fresh();for(unsigned i=0;i<7;++i)step(l,Step{.w=WBeat::concrete(i,255,false)});reject([&]{step(l,Step{.w=WBeat::concrete(7,255,false)});},"MISSING_WLAST");}
  {auto l=fresh();reject([&]{step(l,Step{.read_egress=known(4,0)});},"READ_EGRESS_OWNER");reject([&]{step(l,Step{.write_egress=known(4,0)});},"WRITE_EGRESS_OWNER");reject([&]{step(l,Step{.r_fire=true});},"UNOWNED_R_ACCEPTANCE");reject([&]{step(l,Step{.b_fire=true});},"UNOWNED_B_ACCEPTANCE");}
  {auto l=fresh();step(l,Step{.aw=Request::concrete(base,3,0),.w=WBeat::concrete(1,255,true)});reject([&]{step(l,Step{.write_egress=known(4,4)});},"WRITE_EGRESS_OWNER");reject([&]{step(l,Step{.ar=Request::concrete(base+8,0,0)});},"LIVE_READ_WRITE_LINE_CONFLICT");reject([&]{l.acknowledge_external_fence();},"FENCE_WITH_OWNED_TRANSACTIONS");reject([&]{l.reset(l.committed_edges());},"RESET_WITH_OWNED_TRANSACTIONS");}
  {auto l=fresh();step(l,Step{.w=WBeat::concrete(0,255,true)});reject([&]{step(l,Step{.ar=Request::concrete(base,0,0)});},"READ_WITH_UNOWNED_W_DATA");}
  {auto l=fresh();for(unsigned i=0;i<16;++i)step(l,Step{.aw=Request::concrete(base+64*i,i,0)});reject([&]{step(l,Step{.aw=Request::concrete(base+64*16,0,0)});},"AW_CAPACITY");}
  {auto l=fresh();for(unsigned i=0;i<16;++i)step(l,Step{.w=WBeat::concrete(i,255,true)});reject([&]{step(l,Step{.w=WBeat::concrete(0,255,true)});},"W_CAPACITY");}
  {auto l=fresh();reject([&]{l.advance(1,{});},"STALE_EDGE");step(l);reject([&]{l.advance(0,{});},"STALE_EDGE");}
  {auto l=fresh();step(l,Step{.aw=Request::concrete(base,0,0),.w=WBeat::concrete(0x1122334455667788,1,true),.write_egress=known(4,0)});step(l,Step{.b_fire=true});l.acknowledge_external_fence();need(l.inspect(base).known==255&&l.inspect(base+1).known==0,"partial strobe invented neighbor definedness");reject([&]{step(l,Step{.ar=Request::concrete(base,0,0)});},"UNDEFINED_READ_BYTES");}
}
void replacement(){
  auto l=fresh();std::vector<Byte>bytes(128,{7,255});l.initialize(base,bytes);
  step(l,Step{.ar=Request::concrete(base,2,0),.aw=Request::concrete(base+64,7,0),.w=WBeat::concrete(1,255,true),.read_egress=known(4,2),.write_egress=known(4,7)});
  step(l,Step{.ar=Request::concrete(base,2,0),.aw=Request::concrete(base+128,7,0),.w=WBeat::concrete(2,255,true),.r_fire=true,.b_fire=true,.read_egress=known(4,2),.write_egress=known(4,7)});
  need(l.read_payload()->id==2&&l.write_payload()==7,"sameedge repeatedID replacement");step(l,Step{.r_fire=true,.b_fire=true});need(l.idle(),"sameedge replacement did not drain");
}
}
int main(){try{full_bytes();guards();replacement();std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"typed_refusals\":"<<refusals<<",\"random_write_read_roundtrips\":1000,\"all_byte_golden_checks\":16384,\"functional_model_only\":true,\"timing_or_source_RTL_qualified\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
