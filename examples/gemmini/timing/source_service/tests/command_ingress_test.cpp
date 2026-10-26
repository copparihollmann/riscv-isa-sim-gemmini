#include "command_ingress.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
int main(){
 merlin_timing::PostedTimeline q({4096,4096,10000});std::vector<std::uint64_t>pc;std::vector<merlin_timing::Cycle>allocated;
 PostedCommandIngress ingress(q,{2,2,2,2},[](auto&,auto at){return at>=20;},[&](auto&r,auto at){pc.push_back(r.pc);allocated.push_back(at);});
 std::vector<merlin_timing::Cycle>cpu;
 for(unsigned i=0;i<9;++i){auto r=ingress.push({0x80001000+4*i,i,17+i,33+i,i});assert(r.issue);cpu.push_back(*r.issue);}
 assert(cpu.front()==0&&cpu.back()==24); //8 held raw/passthrough slots; ninth waits for REAL release
 assert(ingress.drain());assert(pc.size()==9);for(unsigned i=0;i<9;++i){assert(pc[i]==0x80001000+4*i);assert(allocated[i]>=20);}
 for(auto n:ingress.coverage().peak)assert(n<=2);
 // Unblocked traffic has FOUR registered boundaries, not zero-delay bypass.
 merlin_timing::PostedTimeline simple({32,32,128});std::optional<std::uint64_t>first;
 PostedCommandIngress pipeline(simple,{2,2,2,2},[](auto&,auto){return true;},[&](auto&r,auto at){assert(r.pc==0x80002000);first=at;});
 auto result=pipeline.push({0x80002000,0,0,0,0});assert(result.issue==0&&!first);assert(pipeline.drain());assert(first==4);
 // Selected RocketTile also owns an upstream RoCC command router Queue2.
 merlin_timing::PostedTimeline routed({4096,4096,10000});std::vector<std::uint64_t>identity;std::optional<std::uint64_t>arrival;
 PostedCommandIngress router(routed,{2,2,2,2},[](auto&,auto at){return at>=20;},[&](auto&r,auto at){assert(r.rs1==r.bits+17&&r.rs2==r.bits+33);identity.push_back(r.pc);if(!arrival)arrival=at;},true);
 cpu.clear();for(unsigned i=0;i<11;++i){auto r=router.push({0x80003000+4*i,i,17+i,33+i,i});assert(r.issue);cpu.push_back(*r.issue);}
 assert(cpu.front()==0&&cpu.back()==25&&router.coverage().peak.size()==5);assert(router.drain()&&identity.size()==11&&arrival==20);
 for(unsigned i=0;i<11;++i)assert(identity[i]==0x80003000+4*i);
 for(auto n:router.coverage().peak)assert(n<=2);
 merlin_timing::PostedTimeline five({32,32,128});arrival.reset();
 PostedCommandIngress five_stages(five,{2,2,2,2},[](auto&,auto){return true;},[&](auto&,auto at){arrival=at;},true);
 assert(five_stages.push({0x80004000,0,0,0,0}).issue==0&&five_stages.drain()&&arrival==5);
 std::cout<<"finite raw2/conv2/matmul2/unrolled2: source-ready vs RS-ready, registered boundaries, bounded pressure, original PC FIFO and full drain PASS\n";
}
