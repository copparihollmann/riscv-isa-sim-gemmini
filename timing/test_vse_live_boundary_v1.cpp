#include "vse_live_boundary_v1.hpp"
#include <algorithm>
#include <iostream>
#include <map>
#include <random>
#include <vector>
using namespace iris::vse_boundary;
int main(){
 uint64_t checks=0,refusals=0;auto check=[&](bool b){++checks;if(!b)throw std::runtime_error("independent VSE ledger assertion");};
 auto refused=[&](auto fn){try{fn();}catch(const std::logic_error&){++refusals;return;}throw std::runtime_error("missing refusal");};
 for(unsigned seed:{1u,17u,31u}){
  OrderedStores q;std::mt19937 rng(seed);std::map<std::pair<unsigned,uint64_t>,Request>live;std::vector<Token>unacked;std::deque<Request>order;uint64_t submitted=0,released=0;
  auto request=[&](uint64_t id){Request r;r.owner={unsigned(seed&1),7,id+1,0x80000400,uint32_t(0x02056027)};r.first_word=id*4;r.words=(id%4)+1;r.address=0x80010000+16*id;r.last=true;r.mask=uint16_t((uint32_t(1)<<(4*r.words))-1);for(unsigned b=0;b<16;++b){r.data[b]=uint8_t(id+b);r.known[b]=uint8_t((b%3)?255:15);}return r;};
  for(unsigned edge=0;released<4096&&edge<200000;++edge){
   if(submitted<4096&&q.reserve_ready()&&(rng()%3)){
    auto r=q.reserve(request(submitted++));check(r.token.tag==(submitted-1)%16);live[{r.token.tag,r.token.generation}]=r;
   }
   if(auto r=q.request();r&&(rng()%3)){q.accepted(r->token);unacked.push_back(r->token);order.push_back(*r);}
   if(!unacked.empty()&&(rng()%3)){
    auto i=rng()%unacked.size();auto t=unacked[i];unacked.erase(unacked.begin()+i);auto r=q.acknowledge(t);check(r.data==live.at({t.tag,t.generation}).data&&r.known==live.at({t.tag,t.generation}).known);live.erase({t.tag,t.generation});
   }
   while(auto r=q.release()){
    check(!order.empty()&&r->token==order.front().token);check(!live.count({r->token.tag,r->token.generation}));check(r->owner==order.front().owner);order.pop_front();++released;
   }
   check(q.live()<=16&&q.request_count()<=2&&q.sifq_count()<=16);
  }
  check(submitted==4096&&released==4096&&q.empty()&&order.empty()&&unacked.empty());
  refused([&]{q.acknowledge({0,1});});
 }
 OrderedStores q;auto make=[](unsigned id){Request r;r.owner={0,1,id,0x80000400,0x02056027};r.words=4;r.address=0x80010000+16*id;r.mask=65535;return r;};
 auto a=q.reserve(make(1)),b=q.reserve(make(2));refused([&]{q.reserve(make(3));});refused([&]{q.accepted(b.token);});refused([&]{q.acknowledge(a.token);});
 q.accepted(a.token);q.accepted(b.token);q.acknowledge(b.token);check(!q.release());refused([&]{q.acknowledge(b.token);});q.acknowledge(a.token);check(q.release()->token==a.token);check(q.release()->token==b.token);refused([&]{q.acknowledge(a.token);});
 for(unsigned i=3;i<=16;++i){auto r=q.reserve(make(i));q.accepted(r.token);q.acknowledge(r.token);check(q.release()->owner.command==i);}
 auto again=q.reserve(make(17));check(again.token.tag==a.token.tag&&again.token.generation>a.token.generation);q.accepted(again.token);refused([&]{q.acknowledge(a.token);});check(q.live()==1);q.acknowledge(again.token);check(q.release()->owner.command==17);
 auto bad=make(18);bad.owner.epoch=0;refused([&]{q.reserve(bad);});bad=make(18);bad.mask=3;refused([&]{q.reserve(bad);});check(q.empty());
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"guard_refusals\":"<<refusals<<",\"source_timing_qualified\":false}\n";
}
