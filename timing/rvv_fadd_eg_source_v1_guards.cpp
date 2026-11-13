#include "rvv_fadd_eg_source_v1.hpp"
#include <iostream>
using namespace iris::rvv_fadd_source;
static unsigned checks=0,refusals=0;
static void need(bool x,const char*s){++checks;if(!x)throw std::runtime_error(s);}
template<class F>void refuse(F f,const char*why){try{f();throw std::runtime_error("expected refusal missing");}catch(const std::invalid_argument&e){need(std::string(e.what())==why,"typed refusal changed");++refusals;}}
int main(){try{
 const Command good{1,0,8,16,24,32,1};
 for(unsigned sew:{8u,128u}){auto c=good;c.sew=sew;refuse([&]{Scheduler::validate(c);},"FADD_SOURCE_FINITE_GEOMETRY");}
 for(unsigned lm:{0u,3u,16u}){auto c=good;c.lmul=lm;refuse([&]{Scheduler::validate(c);},"FADD_SOURCE_FINITE_GEOMETRY");}
 for(unsigned which=0;which<6;++which){auto c=good;if(which==0)c.id=0;if(which==1)c.vat=32;if(which==2)c.vd=32;if(which==3){c.lmul=2;c.vd=31;}if(which==4){c.lmul=4;c.vs1=17;}if(which==5){c.lmul=8;c.vs2=25;}refuse([&]{Scheduler::validate(c);},"FADD_SOURCE_FINITE_GEOMETRY");}
 Scheduler m,baseline;m.step(0,good);baseline.step(0,good);
 refuse([&]{m.step(1,good);},"FADD_SOURCE_ID_REUSE");
 auto alias=good;alias.id=2;refuse([&]{m.step(1,alias);},"FADD_SOURCE_LIVE_VAT_REUSE");
 refuse([&]{m.step(2);},"FADD_SOURCE_EDGE_ORDER");
 auto a=m.step(1),b=baseline.step(1);need(a.vdq_before==b.vdq_before&&a.vdq_dequeue==b.vdq_dequeue,"failed input mutated queue");
 m.step(2);baseline.step(2);
 Ports war;war.older_reads=uint64_t(1)<<16;
 auto e=m.step(3,{},war);need(e.war&&!e.issue&&e.candidate&&e.candidate->index==0,"external WAR failed to hold exact EG");
 Ports unrelated;unrelated.older_reads=uint64_t(1)<<18;unrelated.older_writes=uint64_t(1)<<19;
 e=m.step(4,{},unrelated);need(e.issue&&e.issue->index==0&&!e.war&&!e.raw&&!e.waw,"unrelated EG caused whole-register stall");
 Ports port;port.source1_ready=false;e=m.step(5,{},port);need(!e.issue&&e.candidate->index==1,"real read port backpressure lost group");
 e=m.step(6);need(e.issue&&e.issue->tail&&e.issue->index==1,"tail handoff after port recovery");
 need(e.pending_writes==(uint64_t(1)<<17),"issued EG intent was not released");
 for(unsigned edge=7;edge<=10;++edge){e=m.step(edge);if(edge==8)need(e.write&&e.write->index==0,"first group physical write phase");if(edge==10)need(e.write&&e.write->index==1,"tail physical write phase");}
 need(m.empty(),"all group owners must drain");
 e=m.step(100);need(!e.issue&&!e.write,"quiescent edge should not invent work");
 refuse([&]{m.step(100);},"FADD_SOURCE_EDGE_ORDER");
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"typed_refusals\":"<<refusals<<"}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
