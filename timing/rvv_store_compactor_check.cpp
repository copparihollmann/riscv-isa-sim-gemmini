#include "rvv_store_compactor_control.hpp"
#include "VComputeCompactor.h"
#include "VRocketCompactor.h"
#include "verilated.h"
#include <iostream>
#include <random>
using iris::rvv_store::CompactorControl;
static void need(bool b,const char*why){if(!b)throw std::runtime_error(why);}
template<class M>void run(unsigned width,unsigned seed){VerilatedContext c;c.threads(1);c.randReset(2);c.randSeed(seed);const char*a[]={"configured-compactor-check"};c.commandArgs(1,a);Verilated::threadContextp(&c);M m(&c);CompactorControl q(width);std::mt19937_64 rng(seed);uint64_t push=0,pop=0,blocked=0,forward=0;unsigned pending_push=0,pending_pop=0;
 for(unsigned edge=0;edge<100000;++edge){if(!pending_push&&rng()%4)pending_push=1+rng()%width;if(!pending_pop&&rng()%3)pending_pop=1+rng()%width;CompactorControl::Inputs in{edge<2,bool(pending_push),pending_push?pending_push:width,bool(pending_pop),pending_pop?pending_pop:width,true};m.clock=0;m.reset=in.reset;m.push_valid=in.push_valid;m.pop_valid=in.pop_valid;m.push_bytes=in.push_bytes;m.pop_bytes=in.pop_bytes;Verilated::threadContextp(&c);m.eval();q.evaluate(in);auto o=q.sample();if(o.qualified){need(o.push_ready==bool(m.push_ready),"pushready");need(o.pop_ready==bool(m.pop_ready),"popready");need(o.push_fire==bool(m.push_ready&&m.push_valid),"pushfire");need(o.pop_fire==bool(m.pop_ready&&m.pop_valid),"popfire");push+=o.push_fire;pop+=o.pop_fire;blocked+=in.push_valid&&!o.push_ready;forward+=o.push_fire&&o.pop_fire;}
 m.clock=1;m.eval();m.clock=0;m.eval();q.commit();if(o.push_fire)pending_push=0;if(o.pop_fire)pending_pop=0;}
 need(push>100&&pop>100&&blocked>100&&forward>100,"activecoverage");std::cout<<"CASE {\"width\":"<<width<<",\"seed\":"<<seed<<",\"edges\":100000,\"qualified_fields\":399996,\"pushes\":"<<push<<",\"pops\":"<<pop<<",\"blocked\":"<<blocked<<",\"simultaneous\":"<<forward<<"}\n";}
int main(){try{for(unsigned s:{1u,17u,31u}){run<VComputeCompactor>(16,s);run<VRocketCompactor>(32,s);}std::cout<<"DONE passed\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
